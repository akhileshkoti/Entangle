import asyncio
import logging
import logging.handlers
import os
import re
import socket
from pathlib import Path

from aiohttp import WSMsgType, web

import config
from device_manager import DeviceManager
from vnc_manager import CONNECT_TIMEOUT_SECONDS as VNC_CONNECT_TIMEOUT_SECONDS, DEFAULT_VNC_PORT, VncManager

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


class _RedactPasswords(logging.Filter):
    """VNC viewer URLs may carry ?password=... for auto-login; keep it out
    of the access log (request line and Referer alike)."""

    _PATTERN = re.compile(r"(password=)[^&\s\"]*", re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "password=" in record.msg.lower():
            record.msg = self._PATTERN.sub(r"\1***", record.msg)
        return True


logging.getLogger("aiohttp.access").addFilter(_RedactPasswords())

device_manager = DeviceManager()
vnc_manager = VncManager(config.VNC_HOSTS_FILE)


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


async def api_vnc(request: web.Request) -> web.Response:
    return web.json_response(vnc_manager.list_hosts())


async def vnc_page(request: web.Request) -> web.StreamResponse:
    name = request.match_info["name"]
    if vnc_manager.get_host(name) is None:
        raise web.HTTPNotFound(text=f"Unknown VNC host: {name}")
    return web.FileResponse(STATIC_DIR / "vnc.html")


def _direct_target(request: web.Request) -> tuple[str, int]:
    """host/port from the query string of a direct (not vnc_hosts.json)
    VNC request, validated."""
    if not config.VNC_ALLOW_DIRECT_HOSTS:
        raise web.HTTPForbidden(text="Direct VNC connections are disabled (config.VNC_ALLOW_DIRECT_HOSTS)")
    host = request.query.get("host", "").strip()
    if not host or len(host) > 253 or not re.fullmatch(r"[A-Za-z0-9.:\-\[\]%]+", host):
        raise web.HTTPBadRequest(text="Missing or invalid ?host=")
    try:
        port = int(request.query.get("port") or DEFAULT_VNC_PORT)
    except ValueError:
        raise web.HTTPBadRequest(text="Invalid ?port=")
    if not 1 <= port <= 65535:
        raise web.HTTPBadRequest(text="Invalid ?port=")
    return host.strip("[]"), port


async def vnc_direct_page(request: web.Request) -> web.StreamResponse:
    _direct_target(request)
    return web.FileResponse(STATIC_DIR / "vnc.html")


async def vnc_ws_handler(request: web.Request) -> web.WebSocketResponse:
    name = request.match_info["name"]
    host = vnc_manager.get_host(name)
    if host is None:
        raise web.HTTPNotFound(text=f"Unknown VNC host: {name}")

    def opened() -> None:
        host.viewers += 1
        host.reachable = True
        log.info("[vnc:%s] client connected (total=%d)", name, host.viewers)

    def closed() -> None:
        host.viewers -= 1
        log.info("[vnc:%s] client disconnected (total=%d)", name, host.viewers)

    return await _relay_vnc(request, name, host.host, host.port, opened, closed)


async def vnc_direct_ws_handler(request: web.Request) -> web.WebSocketResponse:
    host, port = _direct_target(request)
    label = f"{host}:{port}"
    return await _relay_vnc(
        request, label, host, port,
        lambda: log.info("[vnc:%s] direct client connected", label),
        lambda: log.info("[vnc:%s] direct client disconnected", label),
    )


async def _relay_vnc(request, label, host, port, opened, closed) -> web.WebSocketResponse:
    """Plain byte relay between noVNC (RFB over WebSocket) and the host's
    VNC server (RFB over TCP) -- what websockify does, minus the extra
    process. One TCP connection per browser client; nothing is parsed
    except the server's opening "RFB xxx.yyy" banner: nothing from the
    browser is forwarded until that's seen, so the relay is no use for
    reaching anything on the network that isn't a VNC server (matters for
    direct connections, where the browser picks the host)."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), VNC_CONNECT_TIMEOUT_SECONDS
        )
    except (OSError, asyncio.TimeoutError) as e:
        log.warning("[vnc:%s] connect to %s:%d failed: %s", label, host, port, e)
        await ws.close(code=1011, message=b"VNC server unreachable")
        return ws

    try:
        banner = await asyncio.wait_for(reader.readexactly(12), VNC_CONNECT_TIMEOUT_SECONDS)
    except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as e:
        banner = b""
        log.warning("[vnc:%s] no VNC banner from %s:%d: %r", label, host, port, e)
    if not banner.startswith(b"RFB "):
        if banner:
            log.warning("[vnc:%s] %s:%d is not a VNC server (got %r)", label, host, port, banner)
        writer.close()
        await ws.close(code=1011, message=b"Not a VNC server")
        return ws

    opened()

    async def tcp_to_ws() -> None:
        try:
            await ws.send_bytes(banner)
            while data := await reader.read(65536):
                await ws.send_bytes(data)
        except (ConnectionError, OSError) as e:
            log.info("[vnc:%s] VNC server connection lost: %s", label, e)
        # VNC server hung up (or failed): end the browser side too, which
        # also ends the receive loop below.
        await ws.close()

    pump_task = asyncio.create_task(tcp_to_ws())
    try:
        async for msg in ws:
            if msg.type == WSMsgType.BINARY:
                writer.write(msg.data)
                await writer.drain()
    except (ConnectionError, OSError) as e:
        log.info("[vnc:%s] VNC server connection lost: %s", label, e)
    finally:
        pump_task.cancel()
        writer.close()
        closed()

    return ws


async def on_startup(app: web.Application) -> None:
    app["discovery_task"] = asyncio.create_task(device_manager.poll_forever())
    app["vnc_poll_task"] = asyncio.create_task(vnc_manager.poll_forever())


def create_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/", devices_page)
    app.router.add_get("/api/devices", api_devices)
    app.router.add_get("/d/{serial}/", device_page)
    app.router.add_get("/d/{serial}/ws", device_ws_handler)
    app.router.add_get("/api/vnc", api_vnc)
    app.router.add_get("/vnc/", vnc_direct_page)
    app.router.add_get("/vnc/ws", vnc_direct_ws_handler)
    app.router.add_get("/vnc/{name}/", vnc_page)
    app.router.add_get("/vnc/{name}/ws", vnc_ws_handler)
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
