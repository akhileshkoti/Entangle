import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

SCRCPY_VERSION = "4.1"
SCRCPY_SERVER_JAR_LOCAL = ROOT_DIR / "scrcpy_server" / "scrcpy-server-v4.1"
SCRCPY_SERVER_JAR_DEVICE = "/data/local/tmp/scrcpy-server.jar"

# Conservative defaults, chosen for later browser/MSE decode compatibility.
DEFAULT_MAX_SIZE = 1920
DEFAULT_VIDEO_BIT_RATE = 8_000_000

# Bind address for the server itself: 0.0.0.0 means anyone who can reach
# this machine on the network can view/control any connected device --
# there is deliberately no authentication (see README.md).
WS_SERVER_BIND_HOST = "0.0.0.0"
WS_SERVER_PORT = 8000

# What local tools (launch_window.py, stop.py's port-check) use to talk to
# the server -- connecting to 0.0.0.0 as a *destination* isn't portable, so
# this stays loopback regardless of the bind host above.
WS_SERVER_LOCAL_HOST = "127.0.0.1"

# find_adb() checks PATH and ADB_ENV_VARS first (both already
# cross-platform); these are just last-resort fallbacks for the common
# default install locations per OS when neither of those is set.
ADB_ENV_VARS = ("ANDROID_SDK_ROOT", "ANDROID_HOME")
ADB_FALLBACK_PATHS = (
    Path(os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")),
    Path.home() / "Android" / "Sdk" / "platform-tools" / "adb",
    Path.home() / "Library" / "Android" / "sdk" / "platform-tools" / "adb",
)
