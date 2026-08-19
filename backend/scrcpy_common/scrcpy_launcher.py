import random
import subprocess

import config
from scrcpy_common import adb


def generate_scid() -> str:
    # scid is parsed server-side via Integer.parseInt(scid, 16) (signed),
    # so it must fit in 0x00000000..0x7FFFFFFF or the server crashes.
    return f"{random.randint(0, 0x7FFFFFFF):08x}"


def push_server_jar(adb_path: str, serial: str | None = None) -> None:
    adb.push(adb_path, str(config.SCRCPY_SERVER_JAR_LOCAL), config.SCRCPY_SERVER_JAR_DEVICE, serial=serial)


def _format_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def build_server_command(scid: str, **opts) -> str:
    # tunnel_forward=true is required: the server otherwise defaults to
    # "reverse" mode (it dials out and expects `adb reverse` on our side).
    # We want it to listen so a plain `adb forward` + connect works.
    params = {
        "scid": scid,
        "tunnel_forward": True,
        "video": True,
        "audio": False,
        "control": False,
        "max_size": config.DEFAULT_MAX_SIZE,
        "video_bit_rate": config.DEFAULT_VIDEO_BIT_RATE,
        "log_level": "info",
    }
    params.update(opts)

    parts = [
        f"CLASSPATH={config.SCRCPY_SERVER_JAR_DEVICE}",
        "app_process",
        "/",
        "com.genymobile.scrcpy.Server",
        config.SCRCPY_VERSION,
    ]
    parts += [f"{k}={_format_value(v)}" for k, v in params.items()]
    return " ".join(parts)


def start_server(adb_path: str, scid: str, serial: str | None = None, **opts) -> subprocess.Popen:
    command = build_server_command(scid, **opts)
    return adb.shell_background(adb_path, command, serial=serial)
