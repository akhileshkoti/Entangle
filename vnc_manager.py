import asyncio
import json
import logging
from pathlib import Path

log = logging.getLogger("vnc_manager")

REACHABILITY_POLL_SECONDS = 10.0
CONNECT_TIMEOUT_SECONDS = 3.0
DEFAULT_VNC_PORT = 5900


class VncHost:
    def __init__(self, name: str, host: str, port: int):
        self.name = name
        self.host = host
        self.port = port
        self.reachable = False
        self.viewers = 0


class VncManager:
    """Tracks the VNC servers listed in vnc_hosts.json. Only hosts listed
    there can be relayed to -- the WS relay never takes a host/port from
    the client, so Entangle can't be used as an open TCP proxy into the
    LAN. The file is re-read whenever it changes, no restart needed."""

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.hosts: dict[str, VncHost] = {}
        self._config_mtime: float | None = None

    def list_hosts(self) -> list[dict]:
        return [
            {
                "name": h.name,
                "host": h.host,
                "port": h.port,
                "reachable": h.reachable,
                "viewers": h.viewers,
            }
            for h in self.hosts.values()
        ]

    def get_host(self, name: str) -> VncHost | None:
        return self.hosts.get(name)

    def _reload_if_changed(self) -> None:
        try:
            mtime = self.config_path.stat().st_mtime
        except FileNotFoundError:
            if self.hosts:
                log.info("%s removed, clearing VNC hosts", self.config_path.name)
            self.hosts = {}
            self._config_mtime = None
            return
        if mtime == self._config_mtime:
            return
        self._config_mtime = mtime

        try:
            entries = json.loads(self.config_path.read_text(encoding="utf-8"))
            hosts = {}
            for entry in entries:
                name = str(entry["name"])
                hosts[name] = VncHost(name, str(entry["host"]), int(entry.get("port", DEFAULT_VNC_PORT)))
        except (OSError, ValueError, TypeError, KeyError):
            log.exception("failed to load %s, keeping previous VNC hosts", self.config_path.name)
            return

        # Keep live state (reachability, viewer counts) for hosts that survived the edit.
        for name, new in hosts.items():
            old = self.hosts.get(name)
            if old is not None and (old.host, old.port) == (new.host, new.port):
                hosts[name] = old
        self.hosts = hosts
        log.info("loaded %d VNC host(s) from %s", len(hosts), self.config_path.name)

    async def _probe(self, h: VncHost) -> None:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(h.host, h.port), CONNECT_TIMEOUT_SECONDS
            )
        except (OSError, asyncio.TimeoutError):
            reachable = False
        else:
            writer.close()
            reachable = True
        if reachable != h.reachable:
            log.info("VNC host %s (%s:%d) %s", h.name, h.host, h.port, "reachable" if reachable else "unreachable")
        h.reachable = reachable

    async def poll_forever(self) -> None:
        while True:
            try:
                self._reload_if_changed()
                # Skip probing hosts someone's already viewing: the open
                # session already proves reachability, and some VNC servers
                # log every bare connect.
                await asyncio.gather(*(self._probe(h) for h in self.hosts.values() if h.viewers == 0))
            except Exception:
                log.exception("VNC host poll failed")
            await asyncio.sleep(REACHABILITY_POLL_SECONDS)
