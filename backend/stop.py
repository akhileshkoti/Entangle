import os
import signal
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PID_FILE = BACKEND_DIR / ".ws_server.pid"


def main() -> None:
    if not PID_FILE.exists():
        print("No running server found (pid file missing).")
        return

    pid = int(PID_FILE.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"Stopped ws_server (pid {pid}).")
    except OSError as exc:
        print(f"Could not stop pid {pid}: {exc}")
    finally:
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
