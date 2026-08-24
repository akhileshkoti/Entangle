import asyncio
import subprocess
import sys

from scrcpy_common import adb, protocol, scrcpy_launcher


class DeviceSession:
    """Owns one scrcpy-server run: pushes the jar, launches it via
    app_process, connects the enabled sockets (in the server's fixed
    accept order: video, audio, control, all over a single adb-forwarded
    port), and exposes the video stream + control channel."""

    def __init__(self, video=True, audio=False, control=False, serial: str | None = None, **server_opts):
        self.video = video
        self.audio = audio
        self.control = control
        self.serial = serial
        self.server_opts = server_opts

        self.adb_path = adb.find_adb()
        self.scid = None
        self.server_process = None
        self._local_port = None
        self._log_task = None

        self.device_name = None
        self.video_codec_id = None
        self.video_reader = None
        self.video_writer = None
        self.control_reader = None
        self.control_writer = None
        self._control_lock = asyncio.Lock()

    async def start(self):
        # No forward_remove_all here: with multiple devices attached, that
        # call is global across ALL of them and would tear down other
        # devices' active forwards. Each session's own port is tracked and
        # removed individually in stop().
        await asyncio.to_thread(scrcpy_launcher.push_server_jar, self.adb_path, serial=self.serial)
        self.scid = scrcpy_launcher.generate_scid()

        self.server_process = await asyncio.to_thread(
            scrcpy_launcher.start_server,
            self.adb_path,
            self.scid,
            serial=self.serial,
            video=self.video,
            audio=self.audio,
            control=self.control,
            **self.server_opts,
        )
        # Drain the remote process's stdout continuously so a chatty server
        # (log_level, warnings) can never fill the pipe buffer and block it.
        self._log_task = asyncio.create_task(self._drain_server_log())

        # Give app_process's JVM a moment to actually start before asking adb
        # to forward to its (not-yet-bound) abstract socket -- forwarding
        # too early appears to leave the tunnel in a bad state that later
        # connect attempts on the same port never recover from, even after
        # the server is ready (observed empirically; not documented).
        await asyncio.sleep(2.0)

        socket_name = f"localabstract:scrcpy_{self.scid}"
        self._local_port = await asyncio.to_thread(adb.forward, self.adb_path, socket_name, serial=self.serial)

        # The server only writes the handshake (dummy byte + device name) on
        # the first-opened socket AFTER every enabled socket has been
        # accepted (video, then audio, then control) -- not right after the
        # first accept. Reading the handshake before every socket is
        # connected deadlocks: the server blocks waiting for the remaining
        # accept()s, and we block waiting for bytes it won't send yet. So:
        # connect every enabled socket first, THEN read the handshake.
        video_reader = video_writer = None
        control_reader = control_writer = None

        if self.video:
            video_reader, video_writer = await self._connect_socket_with_retry()
        if self.audio:
            await self._connect_socket_with_retry()  # not used by this project
        if self.control:
            control_reader, control_writer = await self._connect_socket_with_retry()

        first_reader = video_reader if self.video else control_reader
        self.device_name = await self._read_handshake(first_reader)

        if self.video:
            self.video_reader, self.video_writer = video_reader, video_writer
            self.video_codec_id = await protocol.read_codec_id(self.video_reader)
        if self.control:
            self.control_reader, self.control_writer = control_reader, control_writer

    async def _read_handshake(self, reader: asyncio.StreamReader) -> str:
        await protocol.recv_exact(reader, 1)  # dummy byte
        raw = await protocol.recv_exact(reader, protocol.DEVICE_NAME_FIELD_LENGTH)
        return raw.rstrip(b"\x00").decode("utf-8", errors="replace")

    async def _drain_server_log(self):
        loop = asyncio.get_event_loop()
        while True:
            line = await loop.run_in_executor(None, self.server_process.stdout.readline)
            if not line:
                break
            print(f"[scrcpy-server {self.serial}] {line.rstrip()}", file=sys.stderr)

    async def _connect_socket_with_retry(self, attempts=10, delay=1.0, per_attempt_timeout=3.0):
        # `adb forward`'s local port accepts immediately regardless of
        # whether the on-device server has bound its socket yet (app_process
        # JVM startup takes a moment), so an early connect gets accepted
        # then instantly closed rather than a clean "refused" -- retry with
        # a generous per-attempt timeout and modest pacing, since each
        # attempt that DOES land creates a real connection the server may
        # commit to as one of its fixed accept-order sockets.
        last_exc = None
        for i in range(attempts):
            try:
                return await asyncio.wait_for(
                    asyncio.open_connection("127.0.0.1", self._local_port), per_attempt_timeout
                )
            except (OSError, asyncio.TimeoutError) as exc:
                last_exc = exc
                print(f"[device_session] connect attempt {i + 1}/{attempts} failed: {exc!r}", file=sys.stderr)
                await asyncio.sleep(delay)
        raise ConnectionError(
            f"could not connect to forwarded port {self._local_port}"
        ) from last_exc

    async def video_packets(self):
        async for item in protocol.iter_video_stream(self.video_reader):
            yield item

    async def send_control(self, payload: bytes) -> None:
        async with self._control_lock:
            self.control_writer.write(payload)
            await self.control_writer.drain()

    async def stop(self):
        if self._log_task is not None:
            self._log_task.cancel()

        for writer in (self.video_writer, self.control_writer):
            if writer is not None:
                writer.close()

        if self._local_port is not None:
            await asyncio.to_thread(adb.forward_remove, self.adb_path, self._local_port, serial=self.serial)

        if self.server_process is not None:
            self.server_process.terminate()
            try:
                await asyncio.to_thread(self.server_process.wait, timeout=3)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
