import asyncio
import logging
import logging.handlers
import os
import socket
from pathlib import Path

from aiohttp import WSMsgType, web

import config
from device_manager import DeviceManager

ROOT_DIR = Path(__file__).resolve().parent
STATIC_DIR = ROOT_DIR / "static"
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
PID_FILE = ROOT_DIR / ".ws_server.pid"

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

device_manager = DeviceManager()


async def devices_page(request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC_DIR / "index.html")


async def api_devices(request: web.Request) -> web.Response:
    return web.json_response(device_manager.list_devices())


async def device_page(request: web.Request) -> web.StreamResponse:
    serial = request.match_info["serial"]
    if device_manager.get_hub(serial) is None:
        raise web.HTTPNotFound(text=f"Unknown device: {serial}")
    return web.FileResponse(STATIC_DIR / "device.html")


async def device_ws_handler(request: web.Request) -> web.WebSocketResponse:
    serial = request.match_info["serial"]
    hub = device_manager.get_hub(serial)
    if hub is None:
        raise web.HTTPNotFound(text=f"Unknown device: {serial}")

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    queue = hub.add_client()
    log.info("[%s] client connected (total=%d)", serial, len(hub.clients))
    await ws.send_json({"device_name": hub.model, "serial": serial})

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
            try:
                log.debug("[%s] control message: %d bytes, type=%d", serial, len(msg.data), msg.data[0] if msg.data else -1)
                await hub.send_control(msg.data)
            except Exception:
                log.exception("[%s] failed to forward control message", serial)
    finally:
        sender_task.cancel()
        hub.remove_client(queue)
        log.info("[%s] client disconnected (total=%d)", serial, len(hub.clients))

    return ws


async def on_startup(app: web.Application) -> None:
    app["discovery_task"] = asyncio.create_task(device_manager.poll_forever())


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", devices_page)
    app.router.add_get("/api/devices", api_devices)
    app.router.add_get("/d/{serial}/", device_page)
    app.router.add_get("/d/{serial}/ws", device_ws_handler)
    app.router.add_static("/static/", STATIC_DIR)
    app.on_startup.append(on_startup)
    return app


def _local_ips() -> list[str]:
    ips = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ips.add(s.getsockname()[0])
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            if not ip.startswith("127."):
                ips.add(ip)
    except OSError:
        pass
    return sorted(ips)


if __name__ == "__main__":
    PID_FILE.write_text(str(os.getpid()))
    if config.WS_SERVER_BIND_HOST == "0.0.0.0":
        for ip in _local_ips():
            log.info("reachable on the network at: http://%s:%d/", ip, config.WS_SERVER_PORT)
    try:
        web.run_app(create_app(), host=config.WS_SERVER_BIND_HOST, port=config.WS_SERVER_PORT)
    finally:
        PID_FILE.unlink(missing_ok=True)
