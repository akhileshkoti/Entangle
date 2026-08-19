import asyncio
import logging
import logging.handlers
import os
from pathlib import Path

from aiohttp import WSMsgType, web

import config
from scrcpy_common.device_session import DeviceSession
from scrcpy_common.protocol import SessionMeta

BACKEND_DIR = Path(__file__).resolve().parent
STATIC_DIR = BACKEND_DIR / "static"
LOG_DIR = BACKEND_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
PID_FILE = BACKEND_DIR / ".ws_server.pid"

logging.basicConfig(
    level=logging.INFO,
    handlers=[
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "ws_server.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
    ],
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ws_server")


class Hub:
    """Fans out one upstream video read to N connected WebSocket clients."""

    def __init__(self):
        self.clients: set[asyncio.Queue] = set()
        self.device_name = None
        self.session: DeviceSession | None = None
        # A new client joining mid-stream never sees the (usually one-time)
        # config packet or an already-broadcast keyframe -- without these
        # cached and replayed, its decoder never receives SPS/PPS and stays
        # permanently un-initialized despite otherwise-healthy frame flow.
        self.last_config_packet: bytes | None = None
        self.last_keyframe: bytes | None = None

    def note_packet(self, data: bytes, is_config: bool, is_key_frame: bool) -> None:
        if is_config:
            self.last_config_packet = data
        elif is_key_frame:
            self.last_keyframe = data

    def add_client(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.clients.add(queue)
        return queue

    def remove_client(self, queue: asyncio.Queue) -> None:
        self.clients.discard(queue)

    def broadcast(self, data: bytes) -> None:
        # Live view, not VOD: drop the oldest queued frame rather than
        # block or grow unbounded -- a lagging client just skips ahead,
        # and the next keyframe recovers correctness visually.
        for queue in list(self.clients):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                pass


hub = Hub()


async def run_session_forever() -> None:
    backoff = 1.0
    while True:
        session = None
        try:
            session = DeviceSession(video=True, audio=False, control=True)
            await session.start()
            hub.session = session
            hub.device_name = session.device_name
            hub.last_config_packet = None
            hub.last_keyframe = None
            log.info("device connected: %s", session.device_name)
            backoff = 1.0

            async for item in session.video_packets():
                if isinstance(item, SessionMeta):
                    log.info("session meta: %dx%d", item.width, item.height)
                    continue
                hub.note_packet(item.data, item.is_config, item.is_key_frame)
                hub.broadcast(item.data)
        except Exception:
            log.exception("device session failed, retrying in %.0fs", backoff)
        finally:
            hub.session = None
            if session is not None:
                await session.stop()

        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 10.0)


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    queue = hub.add_client()
    log.info("client connected (total=%d)", len(hub.clients))
    await ws.send_json({"device_name": hub.device_name})

    # Prime the new client's decoder: without these it never sees SPS/PPS
    # (or a keyframe to start from) until the next periodic keyframe, if
    # ever -- see Hub.note_packet.
    if hub.last_config_packet is not None:
        await ws.send_bytes(hub.last_config_packet)
    if hub.last_keyframe is not None:
        await ws.send_bytes(hub.last_keyframe)

    async def sender() -> None:
        while True:
            data = await queue.get()
            await ws.send_bytes(data)

    sender_task = asyncio.create_task(sender())
    try:
        async for msg in ws:
            if msg.type != WSMsgType.BINARY:
                continue
            session = hub.session
            if session is None:
                continue
            try:
                log.debug("control message: %d bytes, type=%d", len(msg.data), msg.data[0] if msg.data else -1)
                await session.send_control(msg.data)
            except Exception:
                log.exception("failed to forward control message")
    finally:
        sender_task.cancel()
        hub.remove_client(queue)
        log.info("client disconnected (total=%d)", len(hub.clients))

    return ws


async def on_startup(app: web.Application) -> None:
    app["session_task"] = asyncio.create_task(run_session_forever())


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/static/", STATIC_DIR)
    app.on_startup.append(on_startup)
    return app


if __name__ == "__main__":
    PID_FILE.write_text(str(os.getpid()))
    try:
        web.run_app(create_app(), host=config.WS_SERVER_HOST, port=config.WS_SERVER_PORT)
    finally:
        PID_FILE.unlink(missing_ok=True)
