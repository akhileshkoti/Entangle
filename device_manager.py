import asyncio
import logging

from scrcpy_common import adb
from scrcpy_common.device_session import DeviceSession
from scrcpy_common.protocol import SessionMeta

log = logging.getLogger("device_manager")

DISCOVERY_POLL_SECONDS = 2.0


class DeviceHub:
    """One connected device: lazily starts a DeviceSession (and the whole
    on-device capture pipeline) only once a viewer actually connects, and
    stops it once the last viewer leaves -- avoids draining battery/CPU on
    every attached phone whether anyone's watching it or not."""

    def __init__(self, serial: str, model: str):
        self.serial = serial
        self.model = model
        self.clients: set[asyncio.Queue] = set()
        self.session: DeviceSession | None = None
        self.last_config_packet: bytes | None = None
        self.last_keyframe: bytes | None = None
        self._run_task: asyncio.Task | None = None

    def add_client(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self.clients.add(queue)
        if self._run_task is None or self._run_task.done():
            self.last_config_packet = None
            self.last_keyframe = None
            self._run_task = asyncio.create_task(self._run())
        return queue

    def remove_client(self, queue: asyncio.Queue) -> None:
        self.clients.discard(queue)
        if not self.clients and self._run_task is not None:
            self._run_task.cancel()
            self._run_task = None

    def note_packet(self, data: bytes, is_config: bool, is_key_frame: bool) -> None:
        if is_config:
            self.last_config_packet = data
        elif is_key_frame:
            self.last_keyframe = data

    def broadcast(self, data: bytes) -> None:
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

    async def send_control(self, payload: bytes) -> None:
        session = self.session
        if session is not None:
            await session.send_control(payload)

    async def _run(self) -> None:
        backoff = 1.0
        while True:
            session = None
            try:
                session = DeviceSession(video=True, audio=False, control=True, serial=self.serial)
                await session.start()
                self.session = session
                self.model = session.device_name or self.model
                log.info("[%s] device connected: %s", self.serial, session.device_name)
                backoff = 1.0

                async for item in session.video_packets():
                    if isinstance(item, SessionMeta):
                        log.info("[%s] session meta: %dx%d", self.serial, item.width, item.height)
                        continue
                    self.note_packet(item.data, item.is_config, item.is_key_frame)
                    self.broadcast(item.data)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("[%s] device session failed, retrying in %.0fs", self.serial, backoff)
            finally:
                self.session = None
                if session is not None:
                    await session.stop()

            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 10.0)


class DeviceManager:
    """Polls `adb devices` to track what's attached, keeping one DeviceHub
    per serial ever seen (so a briefly-disconnected device's viewers don't
    get dropped from the device list, just marked disconnected)."""

    def __init__(self):
        self.adb_path = adb.find_adb()
        self.hubs: dict[str, DeviceHub] = {}
        self.connected: set[str] = set()

    def list_devices(self) -> list[dict]:
        return [
            {
                "serial": serial,
                "model": hub.model,
                "connected": serial in self.connected,
                "viewers": len(hub.clients),
            }
            for serial, hub in sorted(self.hubs.items())
        ]

    def get_hub(self, serial: str) -> DeviceHub | None:
        return self.hubs.get(serial)

    async def poll_forever(self) -> None:
        while True:
            try:
                current = await asyncio.to_thread(adb.devices, self.adb_path)
            except Exception:
                log.exception("adb devices poll failed")
                current = {}

            new_serials = set(current) - self.connected
            gone_serials = self.connected - set(current)
            self.connected = set(current)

            for serial in new_serials:
                model = current[serial]
                if serial in self.hubs:
                    self.hubs[serial].model = model
                else:
                    self.hubs[serial] = DeviceHub(serial, model)
                log.info("device attached: %s (%s)", serial, model)

            for serial in gone_serials:
                log.info("device detached: %s", serial)

            await asyncio.sleep(DISCOVERY_POLL_SECONDS)
