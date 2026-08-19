import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import config

ROOT_DIR = Path(__file__).resolve().parent
PROFILE_DIR = ROOT_DIR / ".browser-profile"

IS_WINDOWS = platform.system() == "Windows"

BROWSER_NAMES = (
    "msedge",
    "microsoft-edge",
    "microsoft-edge-stable",
    "chrome",
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
)

BROWSER_FALLBACKS_WINDOWS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)

BROWSER_FALLBACKS_MACOS = (
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


def is_port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def find_background_python() -> str:
    """The interpreter to launch ws_server.py with so it doesn't tie up a
    console. Windows has a real distinction (pythonw.exe has no console
    subsystem); on Linux/macOS a plain background process with its output
    redirected is already console-free, so the normal interpreter is fine."""
    if not IS_WINDOWS:
        return sys.executable

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
    for name in BROWSER_NAMES:
        found = shutil.which(name)
        if found:
            return found

    fallbacks = BROWSER_FALLBACKS_WINDOWS if IS_WINDOWS else BROWSER_FALLBACKS_MACOS
    for candidate in fallbacks:
        if Path(candidate).exists():
            return candidate

    raise FileNotFoundError(
        "No Chromium-based browser (Edge/Chrome/Chromium) found for app-mode window"
    )


def ensure_server_running() -> None:
    if is_port_open(config.WS_SERVER_LOCAL_HOST, config.WS_SERVER_PORT):
        return

    python = find_background_python()
    popen_kwargs = {"cwd": str(ROOT_DIR)}
    if IS_WINDOWS:
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        popen_kwargs["stdout"] = subprocess.DEVNULL
        popen_kwargs["stderr"] = subprocess.DEVNULL
        popen_kwargs["start_new_session"] = True  # detach from this process's session

    subprocess.Popen([python, str(ROOT_DIR / "ws_server.py")], **popen_kwargs)

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
