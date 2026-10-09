# Entangle

Live screen mirroring + remote control for one or more Android devices,
using scrcpy's own on-device server component (vendored in
`scrcpy_server/`, see `NOTICE.md`) for capture and input injection -- no
in-app permission dialog, since it runs as the adb `shell` user rather
than through `MediaProjectionManager`.

Named after quantum entanglement: your PC and the phone's screen/input,
kept in sync as if linked at a distance.

Cross-platform: everything here is plain Python (`asyncio`/`aiohttp`) and
shells out to `adb`, so the core (`ws_server.py` and everything it uses)
runs the same on Windows, Linux, and macOS. Only `launch_window.py` (the
optional no-console app-mode-window convenience launcher) has any
OS-specific logic, and it already branches for all three.

## Setup

**Prerequisites:**
- Python 3.10+
- `adb` (Android SDK Platform Tools) -- either on `PATH`, or with
  `ANDROID_SDK_ROOT`/`ANDROID_HOME` pointing at your SDK install
  (`find_adb()` in `scrcpy_common/adb.py` checks both, plus a couple of
  common default install locations per OS as a last resort)
- A Chromium-based browser (Edge, Chrome, or Chromium) if you want the
  app-mode window (`launch_window.py`) -- any browser works for the
  plain-tab flow
- One or more Android devices with **USB debugging enabled**
  (Settings -> About phone -> tap Build number 7x to unlock Developer
  options -> enable USB debugging), connected over USB (or already set up
  for wireless `adb`) and authorized -- accept the "Allow USB debugging?"
  prompt on the phone the first time

**Install:**
```
git clone https://github.com/akhileshkoti/Entangle.git
cd Entangle
pip install -r requirements.txt
```

**Verify adb sees your device(s):**
```
adb devices
```
Each should show as `device` (not `unauthorized` or `offline`).

Then jump to "Running it" below.

## Security -- read this before exposing to a network

The server binds to `0.0.0.0` by default (`config.WS_SERVER_BIND_HOST`)
and has **no authentication**. Anyone who can reach the port on your
network gets full live view + touch/keyboard control of every attached
device, no prompt. This is a deliberate choice for a trusted home network;
if that's not your situation, either set `WS_SERVER_BIND_HOST` back to
`127.0.0.1` in `config.py`, or add an access-control layer in front before
running this anywhere less trusted.

## Running it

Defaults to port 8000; override with `ENTANGLE_PORT` if that's taken
(common -- it's also Django's `runserver` default, Python's
`http.server` default, etc.):
```
ENTANGLE_PORT=9000 python ws_server.py
```
(`set ENTANGLE_PORT=9000` then run, on Windows cmd; `$env:ENTANGLE_PORT=9000`
in PowerShell.) Applies to every command below the same way, including
`launch_window.py`, which passes its environment through to the server
it starts.

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

## Laptops / desktops over VNC

The same device list also shows any machines running a VNC server, viewed
and controlled in the browser with [noVNC](https://github.com/novnc/noVNC)
(vendored in `static/vendor/novnc/`, MPL-2.0). Browsers can't open raw TCP,
so `ws_server.py` relays each viewer's WebSocket to the machine's VNC port
byte-for-byte (what `websockify` normally does) -- no extra process or
dependency.

**Add machines** to `vnc_hosts.json` (ships as an empty list; see
`vnc_hosts.example.json`):
```json
[
  {"name": "dev-laptop", "host": "192.168.1.42", "port": 5900},
  {"name": "macbook", "host": "192.168.1.57"}
]
```
`port` defaults to 5900. The file is re-read whenever it changes, no
restart needed. Each entry appears under "Laptops (VNC)" at `/` (reachability
re-checked every 10s) and opens at `/vnc/<name>/`, which asks for the VNC
password if the server wants one.

**Any other machine, by IP:** the "+ Open remote device" button under
Laptops (VNC) asks for IP/hostname, port, an optional device name, and
username/password, then opens the viewer -- no `vnc_hosts.json` entry
needed. It hands credentials to the viewer through `sessionStorage` rather
than the URL, so they stay out of browser history. To do the same from a
link, script or another app, use the URL API below. Since the browser picks
the host here, the relay only forwards anything once the target has greeted
it as a VNC server (`RFB xxx.yyy`) -- it can't be used to reach other
services on the network. Set `config.VNC_ALLOW_DIRECT_HOSTS = False` to
allow only listed hosts.

### VNC viewer URL API

Open these in a browser (or link to them) to get straight to a machine's
screen. Two forms:

| URL | Opens |
| --- | --- |
| `http://<entangle>:<port>/vnc/?host=<ip>` | Any VNC server, by IP or hostname |
| `http://<entangle>:<port>/vnc/<name>/` | A machine listed in `vnc_hosts.json` |

Query parameters (all optional except `host` on the first form):

| Parameter | Meaning |
| --- | --- |
| `host` | IP address or hostname of the VNC server (`/vnc/?host=...` form only) |
| `port` | VNC port, default `5900` (`/vnc/?host=...` form only) |
| `devicename` | Name shown as the page title and status label. Defaults to the `vnc_hosts.json` name, or the host |
| `username` | Login username -- only macOS Screen Sharing asks for one (the Mac account's username) |
| `password` | VNC password, or the macOS account password |

With `username`/`password` (as needed) the viewer signs in on its own;
without them, or if they're wrong, it shows the sign-in form instead.
Values must be URL-encoded (space -> `%20`, `&` -> `%26`, `#` -> `%23`,
`+` -> `%2B`).

Examples (Entangle running at `192.168.245.117:1201`):
```
# Mac by IP, signed in automatically, labelled "Lab MacBook"
http://192.168.245.117:1201/vnc/?host=192.168.244.128&devicename=Lab%20MacBook&username=lanforge&password=lanforge

# Windows/Linux VNC server on a non-default port (VNC password only, no username)
http://192.168.245.117:1201/vnc/?host=192.168.240.210&port=5901&devicename=HPtesting&password=secret

# Machine from vnc_hosts.json, relabelled, signed in automatically
http://192.168.245.117:1201/vnc/Macs-MacBook-Air/?devicename=Lab%20MacBook&username=lanforge&password=lanforge
```

What happens to the credentials: the page removes `username`/`password`
from the address bar as soon as it loads (other parameters stay, so a
reload still reaches the same machine, and asks to sign in again), sends no
`Referer`, and `ws_server.py` logs `password=***`. The browser's history
still keeps the URL exactly as it was opened, though, and anyone you share
such a link with has the password.

Errors: a missing/invalid `host` or `port` returns HTTP 400; an unknown
`<name>` returns 404; with `config.VNC_ALLOW_DIRECT_HOSTS = False` the
`/vnc/?host=...` form returns 403.

**On each machine:**
- The VNC server must accept connections from the machine running
  Entangle: allow its port through the firewall, and make sure it isn't
  set to listen on localhost only.
- Use plain **VNC password** authentication. That's the default for
  TightVNC, TigerVNC, UltraVNC and x11vnc. macOS Screen Sharing works too
  (it asks for your macOS username + password; the AES that login needs is
  normally HTTPS-only in browsers, so `static/subtle_aes_fallback.js`
  supplies it when Entangle is opened over plain `http://<lan-ip>`). RealVNC Server's default
  login won't connect -- switch it to "VNC password" in its Options ->
  Security.

**Security:** the relay only ever connects to hosts listed in
`vnc_hosts.json` or -- unless `config.VNC_ALLOW_DIRECT_HOSTS = False` --
ones given by IP that answer as VNC servers. Since Entangle itself has no
authentication, each machine's VNC password is its only protection --
anyone who can reach Entangle can reach the login prompt. VNC traffic is
also usually unencrypted. Keep it on a trusted network.

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

VNC hosts: `ws://<host>:8000/vnc/<name>/ws` is a raw RFB byte stream to
that machine's VNC server (one TCP connection per WS client) -- point any
noVNC `RFB` instance at it; `ws://<host>:8000/vnc/ws?host=<ip>&port=<port>`
does the same for any VNC server not in the list (see above). `GET /api/vnc`
lists the configured ones
(`[{name, host, port, reachable, viewers}, ...]`).

## Layout

- `scrcpy_common/` -- adb wrapper (serial-aware), server launcher, wire
  protocol (de)serialization, and the `DeviceSession` that owns one
  scrcpy-server run for one device.
- `device_manager.py` -- discovers attached devices; one `DeviceHub` per
  device, lazily starting/stopping its `DeviceSession` based on viewer
  count and fanning video out to that device's connected WS clients.
- `vnc_manager.py` -- loads `vnc_hosts.json` and tracks which VNC hosts
  are reachable.
- `ws_server.py` -- the persistent process: owns the `DeviceManager` and
  `VncManager`, routes HTTP/WS per device, forwards control input, relays
  VNC WebSockets to TCP.
- `static/` -- the browser client: `index.html`/`devices.js` (device
  list), `device.html`/`app.js` (viewer: video via MSE/jmuxer, input via
  Pointer/Keyboard/Wheel events -> control messages), `vnc_hosts.js` (VNC
  host list), `vnc.html`/`vnc.js` (VNC viewer, via noVNC).
- `dump_video_cli.py`, `control_test_cli.py` -- standalone diagnostic
  scripts (`--serial`/positional arg to target a device) used while
  building this out; not part of the running system.
