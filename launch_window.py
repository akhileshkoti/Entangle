import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import config

ROOT_DIR = Path(__file__).resolve().parent
PROFILE_DIR = ROOT_DIR / ".browser-profile"

BROWSER_FALLBACKS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def find_pythonw() -> str:
    # Prefer the currently-running interpreter's own directory: `shutil.which`
    # can resolve to the WindowsApps App Execution Alias stub first, which
    # spawns a second, separate pythonw.exe alongside itself instead of
    # replacing it -- harmless (only one binds the port) but confusing.
    candidate = Path(sys.executable).with_name("pythonw.exe")
    if candidate.exists():
        return str(candidate)
    found = shutil.which("pythonw")
    if found:
        return found
    return sys.executable  # last resort: a console window will flash


def find_browser() -> str:
    for name in ("msedge", "chrome", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in BROWSER_FALLBACKS:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError("No Chromium-based browser (Edge/Chrome) found for app-mode window")


def ensure_server_running() -> None:
    if is_port_open(config.WS_SERVER_LOCAL_HOST, config.WS_SERVER_PORT):
        return

    pythonw = find_pythonw()
    subprocess.Popen(
        [pythonw, str(ROOT_DIR / "ws_server.py")],
        cwd=str(ROOT_DIR),
        creationflags=subprocess.CREATE_NO_WINDOW,
    )

    for _ in range(60):
        if is_port_open(config.WS_SERVER_LOCAL_HOST, config.WS_SERVER_PORT):
            return
        time.sleep(0.5)
    raise TimeoutError("ws_server did not start listening within 30s")


def main() -> None:
    ensure_server_running()
    browser = find_browser()
    PROFILE_DIR.mkdir(exist_ok=True)

    # Optional serial arg opens straight to that device's viewer; with none,
    # opens the device list to pick from.
    serial = sys.argv[1] if len(sys.argv) > 1 else None
    path = f"d/{serial}/" if serial else ""
    url = f"http://{config.WS_SERVER_LOCAL_HOST}:{config.WS_SERVER_PORT}/{path}"
    subprocess.Popen([browser, f"--app={url}", f"--user-data-dir={PROFILE_DIR}"])


if __name__ == "__main__":
    main()
