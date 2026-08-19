# Entangle backend

Live screen mirroring + remote control for one or more Android devices,
using scrcpy's own on-device server component (vendored in
`scrcpy_server/`, see `NOTICE.md`) for capture and input injection -- no
in-app permission dialog, since it runs as the adb `shell` user rather
than through `MediaProjectionManager`.

## Security -- read this before exposing to a network

The server binds to `0.0.0.0` by default (`config.WS_SERVER_BIND_HOST`)
and has **no authentication**. Anyone who can reach the port on your
network gets full live view + touch/keyboard control of every attached
device, no prompt. This is a deliberate choice for a trusted home network;
if that's not your situation, either set `WS_SERVER_BIND_HOST` back to
`127.0.0.1` in `config.py`, or add an access-control layer in front before
running this anywhere less trusted.

## Running it

**Plain browser tab:**
```
python ws_server.py
```
then open `http://127.0.0.1:8000/`. On startup it logs every LAN IP it's
reachable on (`logs/ws_server.log`) -- use one of those from another
device on the network. Runs in the foreground with a console window.

**App-mode window (no console window):**
```
python launch_window.py [serial]
```
Starts `ws_server.py` in the background via `pythonw.exe` if it isn't
already running (polling until it's up), then opens a borderless
Edge/Chrome "app mode" window using a dedicated browser profile
(`.browser-profile/`). With no argument it opens the device list; pass a
device serial to jump straight to that device's viewer. Safe to run again
any time -- it reuses the already-running server rather than starting a
second one.

**Stopping the background server:**
```
python stop.py
```
Reads the PID file (`.ws_server.pid`, written on startup) and terminates
that process. Closing an app-mode window does *not* stop the server --
other clients (another window, a browser tab, a webapp, someone else on
the network) may still be using it.

## Multiple devices

Every `adb`-attached, authorized device is discovered automatically
(polled every 2s) and listed at `/`. Capture only actually starts for a
given device once someone opens its viewer (`/d/<serial>/`) -- with zero
viewers, nothing runs on that phone (no battery/CPU cost, no on-device
process). The on-device scrcpy-server process is killed the moment the
last viewer for that device disconnects.

Since `adb` commands become ambiguous with more than one device attached,
every adb call in `scrcpy_common/adb.py` takes an optional `serial` and
passes `-s <serial>` through -- `DeviceSession` always sets this from
whichever device it was constructed for.

## WS transport contract

Any local webapp can connect to `ws://<host>:8000/d/<serial>/ws` for a
given device and speak this small protocol (all clients for the same
device share that device's one upstream connection):

- **On connect**, the server sends one JSON text frame:
  `{"device_name": "...", "serial": "..."}`.
- **Server -> client** binary frames are raw H.264 Annex-B NAL payloads
  (a config packet + a keyframe are replayed immediately on connect so a
  late joiner doesn't wait for the next periodic keyframe) -- feed them
  into an MSE-based decoder such as [jmuxer](https://github.com/samirkumardas/jmuxer)
  (vendored in `static/vendor/`).
- **Client -> server** binary frames are raw scrcpy control-message bytes
  (see `scrcpy_common/control_protocol.py` for the wire format, mirrored
  in `static/control_protocol.js`) -- forwarded directly to that device's
  control socket.

`GET /api/devices` returns the current device list as JSON
(`[{serial, model, connected, viewers}, ...]`) if a webapp wants to build
its own device picker instead of using `/`.

## Layout

- `scrcpy_common/` -- adb wrapper (serial-aware), server launcher, wire
  protocol (de)serialization, and the `DeviceSession` that owns one
  scrcpy-server run for one device.
- `device_manager.py` -- discovers attached devices; one `DeviceHub` per
  device, lazily starting/stopping its `DeviceSession` based on viewer
  count and fanning video out to that device's connected WS clients.
- `ws_server.py` -- the persistent process: owns the `DeviceManager`,
  routes HTTP/WS per device, forwards control input.
- `static/` -- the browser client: `index.html`/`devices.js` (device
  list), `device.html`/`app.js` (viewer: video via MSE/jmuxer, input via
  Pointer/Keyboard/Wheel events -> control messages).
- `dump_video_cli.py`, `control_test_cli.py` -- standalone diagnostic
  scripts (`--serial`/positional arg to target a device) used while
  building this out; not part of the running system.
