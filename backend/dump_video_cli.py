import argparse
import asyncio
import sys

from scrcpy_common.device_session import DeviceSession
from scrcpy_common.protocol import SessionMeta

TERMINAL_ERRORS = (
    asyncio.IncompleteReadError,
    ConnectionError,
    BrokenPipeError,
    OSError,
)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="output.h264", help="output file (ignored with --stdout)")
    parser.add_argument("--stdout", action="store_true", help="write raw H.264 to stdout instead")
    parser.add_argument("--seconds", type=float, default=None, help="stop after N seconds (default: run until Ctrl+C)")
    args = parser.parse_args()

    session = DeviceSession(video=True, audio=False, control=False)
    await session.start()
    print(f"Connected: {session.device_name!r} codec_id=0x{session.video_codec_id:08x}", file=sys.stderr)

    out = sys.stdout.buffer if args.stdout else open(args.out, "wb")
    frame_count = 0
    loop = asyncio.get_event_loop()
    deadline = loop.time() + args.seconds if args.seconds else None

    try:
        async for item in session.video_packets():
            if isinstance(item, SessionMeta):
                print(f"Session: {item.width}x{item.height}", file=sys.stderr)
                continue

            out.write(item.data)
            out.flush()
            frame_count += 1
            if frame_count % 30 == 0:
                print(f"{frame_count} packets", file=sys.stderr)
            if deadline and loop.time() >= deadline:
                break
    except (KeyboardInterrupt, asyncio.CancelledError, *TERMINAL_ERRORS):
        pass
    finally:
        if not args.stdout:
            out.close()
        await session.stop()
        print(f"Done: {frame_count} packets", file=sys.stderr)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
