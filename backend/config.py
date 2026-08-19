import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent

SCRCPY_VERSION = "4.1"
SCRCPY_SERVER_JAR_LOCAL = BACKEND_DIR / "scrcpy_server" / "scrcpy-server-v4.1"
SCRCPY_SERVER_JAR_DEVICE = "/data/local/tmp/scrcpy-server.jar"

# Conservative defaults, chosen for later browser/MSE decode compatibility.
DEFAULT_MAX_SIZE = 1920
DEFAULT_VIDEO_BIT_RATE = 8_000_000

WS_SERVER_HOST = "127.0.0.1"
WS_SERVER_PORT = 8000

ADB_ENV_VARS = ("ANDROID_SDK_ROOT", "ANDROID_HOME")
ADB_FALLBACK_PATHS = (
    Path(os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")),
)
