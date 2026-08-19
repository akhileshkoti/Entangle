import shutil
import subprocess
from pathlib import Path

import config


def find_adb() -> str:
    found = shutil.which("adb")
    if found:
        return found

    for var in config.ADB_ENV_VARS:
        import os

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


def devices(adb: str) -> list[str]:
    result = run(adb, "devices")
    lines = result.stdout.strip().splitlines()[1:]
    return [line.split("\t")[0] for line in lines if line.strip() and "device" in line]


def push(adb: str, local_path: str, remote_path: str) -> None:
    run(adb, "push", local_path, remote_path)


def forward(adb: str, remote_target: str, local_port: int = 0) -> int:
    """adb forward tcp:<local_port> <remote_target>. local_port=0 asks adb to
    pick a free port; adb prints the assigned port number to stdout."""
    result = run(adb, "forward", f"tcp:{local_port}", remote_target)
    printed = result.stdout.strip()
    return int(printed) if printed else local_port


def forward_remove(adb: str, local_port: int) -> None:
    run(adb, "forward", "--remove", f"tcp:{local_port}", check=False)


def forward_remove_all(adb: str) -> None:
    run(adb, "forward", "--remove-all", check=False)


def shell_background(adb: str, remote_command: str) -> subprocess.Popen:
    """Runs `adb shell <remote_command>` as a long-lived background process
    (e.g. the scrcpy-server app_process invocation), streaming its
    stdout/stderr for diagnostics."""
    return subprocess.Popen(
        [adb, "shell", remote_command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def force_stop(adb: str, package: str) -> None:
    run(adb, "shell", "am", "force-stop", package, check=False)


def exec_out(adb: str, *args: str) -> bytes:
    """adb exec-out <args>, returning raw stdout bytes (e.g. for `screencap -p`)."""
    result = subprocess.run([adb, "exec-out", *args], capture_output=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError(f"adb exec-out {' '.join(args)} failed: {result.stderr.decode(errors='replace')}")
    return result.stdout
