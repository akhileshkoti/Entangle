import asyncio
from dataclasses import dataclass

DEVICE_NAME_FIELD_LENGTH = 64

PACKET_FLAG_SESSION = 1 << 63
PACKET_FLAG_CONFIG = 1 << 62
PACKET_FLAG_KEY_FRAME = 1 << 61
PTS_MASK = (1 << 61) - 1


@dataclass
class VideoPacket:
    pts: int
    is_config: bool
    is_key_frame: bool
    data: bytes


@dataclass
class SessionMeta:
    width: int
    height: int
    is_client_resize: bool


async def recv_exact(reader: asyncio.StreamReader, n: int) -> bytes:
    return await reader.readexactly(n)


async def read_device_meta(reader: asyncio.StreamReader) -> str:
    await recv_exact(reader, 1)  # dummy byte (tunnel_forward handshake)
    raw = await recv_exact(reader, DEVICE_NAME_FIELD_LENGTH)
    return raw.rstrip(b"\x00").decode("utf-8", errors="replace")


async def read_codec_id(reader: asyncio.StreamReader) -> int:
    raw = await recv_exact(reader, 4)
    return int.from_bytes(raw, "big")


async def iter_video_stream(reader: asyncio.StreamReader):
    """Yields SessionMeta and VideoPacket items in wire order.

    The video socket interleaves two distinct 12-byte packet shapes: a
    session/resolution packet (3x u32 BE: flags, width, height; no payload)
    and a normal frame packet (u64 BE pts+flags, u32 BE size, then `size`
    bytes of payload). Both headers are 12 bytes; which shape it is is
    determined by bit 63 of the first 8 bytes (PACKET_FLAG_SESSION), which
    is never set on a real frame's pts (max pts fits in the low 61 bits).
    """
    while True:
        header = await recv_exact(reader, 12)
        first_u64 = int.from_bytes(header[0:8], "big")

        if first_u64 & PACKET_FLAG_SESSION:
            flags = int.from_bytes(header[0:4], "big")
            width = int.from_bytes(header[4:8], "big")
            height = int.from_bytes(header[8:12], "big")
            yield SessionMeta(width=width, height=height, is_client_resize=bool(flags & 1))
            continue

        length = int.from_bytes(header[8:12], "big")
        payload = await recv_exact(reader, length)
        yield VideoPacket(
            pts=first_u64 & PTS_MASK,
            is_config=bool(first_u64 & PACKET_FLAG_CONFIG),
            is_key_frame=bool(first_u64 & PACKET_FLAG_KEY_FRAME),
            data=payload,
        )
