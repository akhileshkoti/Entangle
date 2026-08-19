import os
import re
import shutil
import subprocess
from pathlib import Path

import config


def find_adb() -> str:
    found = shutil.which("adb")
    if found:
        return found

    for var in config.ADB_ENV_VARS:
        root = os.environ.get(var)
        if root:
            candidate = Path(root) / "platform-tools" / "adb.exe"
            if candidate.exists():
                return str(candidate)

    for candidate in config.ADB_FALLBACK_PATHS:
        if candidate.exists():
            return str(candidate)

    raise FileNotFoundError(
        "adb not found on PATH, in ANDROID_SDK_ROOT/ANDROID_HOME, or at the known "
        "Android Studio SDK location. Set ANDROID_SDK_ROOT or install platform-tools."
    )


def _serial_args(serial: str | None) -> list[str]:
    return ["-s", serial] if serial else []


def run(adb: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        [adb, *args], capture_output=True, text=True, timeout=30
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"adb {' '.join(args)} failed (code {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )
    return result


def devices(adb: str) -> dict[str, str]:
    """Returns {serial: model} for every currently attached, authorized
    device (skips 'unauthorized'/'offline' entries)."""
    result = run(adb, "devices", "-l")
    out = {}
    for line in result.stdout.strip().splitlines()[1:]:
        line = line.strip()
        if not line or "\tdevice" not in line and " device " not in line:
            continue
        parts = line.split()
        if len(parts) < 2 or parts[1] != "device":
            continue
        serial = parts[0]
        match = re.search(r"model:(\S+)", line)
        out[serial] = match.group(1) if match else serial
    return out


def push(adb: str, local_path: str, remote_path: str, serial: str | None = None) -> None:
    run(adb, *_serial_args(serial), "push", local_path, remote_path)


def forward(adb: str, remote_target: str, local_port: int = 0, serial: str | None = None) -> int:
    """adb forward tcp:<local_port> <remote_target>. local_port=0 asks adb to
    pick a free port; adb prints the assigned port number to stdout."""
    result = run(adb, *_serial_args(serial), "forward", f"tcp:{local_port}", remote_target)
    printed = result.stdout.strip()
    return int(printed) if printed else local_port


def forward_remove(adb: str, local_port: int, serial: str | None = None) -> None:
    # Port-specific removal -- safe with multiple devices attached, unlike
    # `forward --remove-all`, which is global across ALL devices and would
    # tear down other devices' active sessions too.
    run(adb, *_serial_args(serial), "forward", "--remove", f"tcp:{local_port}", check=False)


def shell_background(adb: str, remote_command: str, serial: str | None = None) -> subprocess.Popen:
    """Runs `adb shell <remote_command>` as a long-lived background process
    (e.g. the scrcpy-server app_process invocation), streaming its
    stdout/stderr for diagnostics."""
    return subprocess.Popen(
        [adb, *_serial_args(serial), "shell", remote_command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def force_stop(adb: str, package: str, serial: str | None = None) -> None:
    run(adb, *_serial_args(serial), "shell", "am", "force-stop", package, check=False)


def exec_out(adb: str, *args: str, serial: str | None = None) -> bytes:
    """adb exec-out <args>, returning raw stdout bytes (e.g. for `screencap -p`)."""
    result = subprocess.run(
        [adb, *_serial_args(serial), "exec-out", *args], capture_output=True, timeout=15
    )
    if result.returncode != 0:
        raise RuntimeError(f"adb exec-out {' '.join(args)} failed: {result.stderr.decode(errors='replace')}")
    return result.stdout
