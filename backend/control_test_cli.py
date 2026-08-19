import asyncio
import sys

from scrcpy_common import adb
from scrcpy_common.control_protocol import (
    ACTION_DOWN,
    ACTION_MOVE,
    ACTION_UP,
    KEYCODE_HOME,
    encode_inject_keycode,
    encode_inject_touch,
)
from scrcpy_common.device_session import DeviceSession
from scrcpy_common.protocol import SessionMeta


async def main():
    serial = sys.argv[1] if len(sys.argv) > 1 else None
    session = DeviceSession(video=True, audio=False, control=True, serial=serial)
    await session.start()
    print(f"Connected: {session.device_name!r}", file=sys.stderr)

    resolution_ready = asyncio.Event()
    resolution = {}

    async def drain_video():
        try:
            async for item in session.video_packets():
                if isinstance(item, SessionMeta):
                    resolution["w"], resolution["h"] = item.width, item.height
                    resolution_ready.set()
        except asyncio.CancelledError:
            pass

    drain_task = asyncio.create_task(drain_video())
    await asyncio.wait_for(resolution_ready.wait(), timeout=5)
    w, h = resolution["w"], resolution["h"]
    print(f"Device resolution: {w}x{h}", file=sys.stderr)

    adb_path = session.adb_path

    # --- Test A: INJECT_KEYCODE (HOME), verified via screencap diff ---
    adb.run(adb_path, "shell", "am", "start", "-a", "android.settings.SETTINGS", check=False, serial=serial)
    await asyncio.sleep(2)

    before_home_png = adb.exec_out(adb_path, "screencap", "-p", serial=serial)

    await session.send_control(encode_inject_keycode(ACTION_DOWN, KEYCODE_HOME))
    await session.send_control(encode_inject_keycode(ACTION_UP, KEYCODE_HOME))
    await asyncio.sleep(1)

    after_home_png = adb.exec_out(adb_path, "screencap", "-p", serial=serial)

    keycode_ok = before_home_png != after_home_png
    print(
        f"KEYCODE test: {'PASS' if keycode_ok else 'FAIL'} "
        f"(before={len(before_home_png)}B after={len(after_home_png)}B)"
    )

    # --- Test B: INJECT_TOUCH_EVENT (scroll drag), verified via screencap diff ---
    adb.run(adb_path, "shell", "am", "start", "-a", "android.settings.SETTINGS", check=False, serial=serial)
    await asyncio.sleep(1.5)

    before_png = adb.exec_out(adb_path, "screencap", "-p", serial=serial)

    x = w // 2
    y_start = int(h * 0.8)
    y_end = int(h * 0.3)
    await session.send_control(encode_inject_touch(ACTION_DOWN, x, y_start, w, h))
    steps = 10
    for i in range(1, steps + 1):
        y = y_start + (y_end - y_start) * i // steps
        await session.send_control(encode_inject_touch(ACTION_MOVE, x, y, w, h))
        await asyncio.sleep(0.02)
    await session.send_control(encode_inject_touch(ACTION_UP, x, y_end, w, h, pressure=0.0))
    await asyncio.sleep(0.8)

    after_png = adb.exec_out(adb_path, "screencap", "-p", serial=serial)

    touch_ok = before_png != after_png
    print(
        f"TOUCH test: {'PASS' if touch_ok else 'FAIL'} "
        f"(before={len(before_png)}B after={len(after_png)}B)"
    )

    drain_task.cancel()
    try:
        await drain_task
    except asyncio.CancelledError:
        pass

    await session.stop()
    print("Done", file=sys.stderr)

    if not (keycode_ok and touch_ok):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
