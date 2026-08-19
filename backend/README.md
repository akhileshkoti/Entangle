# Entangle backend

Live screen mirroring + remote control for an Android device, using
scrcpy's own on-device server component (vendored in `scrcpy_server/`,
see `NOTICE.md`) for capture and input injection -- no in-app permission
dialog, since it runs as the adb `shell` user rather than through
`MediaProjectionManager`.

## Running it

**Plain browser tab:**
```
python ws_server.py
```
then open `http://127.0.0.1:8000/`. Runs in the foreground with a console
window; logs also go to `logs/ws_server.log`.

**App-mode window (no console window):**
```
python launch_window.py
```
Starts `ws_server.py` in the background via `pythonw.exe` if it isn't
already running (polling until it's up), then opens the page in a
borderless Edge/Chrome "app mode" window using a dedicated browser
profile (`.browser-profile/`) so it doesn't pollute your main profile.
Can be run again any time to open another window against the same
running server -- it won't start a second server if one's already up.

**Stopping the background server:**
```
python stop.py
```
Reads the PID file (`.ws_server.pid`, written on startup) and terminates
that process. Closing an app-mode window does *not* stop the server --
other clients (another window, a browser tab, a webapp) may still be
using it.

## WS transport contract

Any local webapp can connect to `ws://127.0.0.1:8000/ws` and speak this
small protocol (all clients share the one upstream device connection):

- **On connect**, the server sends one JSON text frame: `{"device_name": "..."}`.
- **Server -> client** binary frames are raw H.264 Annex-B NAL payloads
  (a config packet + a keyframe are replayed immediately on connect so a
  late joiner doesn't wait for the next periodic keyframe) -- feed them
  into an MSE-based decoder such as [jmuxer](https://github.com/samirkumardas/jmuxer)
  (vendored in `static/vendor/`).
- **Client -> server** binary frames are raw scrcpy control-message bytes
  (see `scrcpy_common/control_protocol.py` for the wire format, mirrored
  in `static/control_protocol.js`) -- forwarded directly to the device's
  control socket.

## Layout

- `scrcpy_common/` -- adb wrapper, server launcher, wire protocol
  (de)serialization, and the `DeviceSession` that owns one scrcpy-server
  run.
- `ws_server.py` -- the persistent process: owns the device session
  (auto-reconnects on failure), fans video out to N WS clients, forwards
  control input from any of them.
- `static/` -- the browser client (video via MSE/jmuxer, input via
  Pointer/Keyboard/Wheel events -> control messages).
- `dump_video_cli.py`, `control_test_cli.py` -- standalone diagnostic
  scripts used while building this out; not part of the running system.
