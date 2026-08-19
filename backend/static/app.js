const video = document.getElementById('video');
const statusEl = document.getElementById('status');
const startBtn = document.getElementById('start-btn');
const focusCatcher = document.getElementById('focus-catcher');

let jmuxer = null;
let ws = null;
let deviceW = 0;
let deviceH = 0;

function setStatus(text) {
  statusEl.textContent = text;
}

function sendControl(buf) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(buf);
  }
}

function updateDeviceSize() {
  deviceW = video.videoWidth;
  deviceH = video.videoHeight;
}
video.addEventListener('loadedmetadata', updateDeviceSize);
video.addEventListener('resize', updateDeviceSize);

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  // Page is served at /d/<serial>/ -- the per-device WS endpoint is the
  // same path with 'ws' appended.
  const wsPath = location.pathname.endsWith('/') ? location.pathname + 'ws' : location.pathname + '/ws';
  ws = new WebSocket(`${proto}://${location.host}${wsPath}`);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => {
    setStatus('Connected');
    if (jmuxer) {
      jmuxer.destroy();
    }
    jmuxer = new JMuxer({
      node: 'video',
      mode: 'video',
      flushingTime: 0,
      fps: 30,
      debug: false,
    });
  };

  ws.onmessage = (event) => {
    if (typeof event.data === 'string') {
      const meta = JSON.parse(event.data);
      setStatus(`Connected: ${meta.device_name || 'unknown device'}`);
      return;
    }
    if (jmuxer) {
      jmuxer.feed({ video: new Uint8Array(event.data) });
    }
  };

  ws.onclose = () => {
    setStatus('Disconnected, reconnecting...');
    setTimeout(connect, 1000);
  };

  ws.onerror = () => ws.close();
}

startBtn.addEventListener('click', () => {
  startBtn.style.display = 'none';
  video.play().catch(() => {});
});

video.addEventListener('play', () => {
  startBtn.style.display = 'none';
});

video.addEventListener('pause', () => {
  if (video.readyState > 0) {
    startBtn.style.display = 'block';
  }
});

// --- Pointer input: mouse/touch/pen unified via Pointer Events ---

function pointToDevice(e) {
  return normalizeCoords(e.clientX, e.clientY, video, deviceW, deviceH);
}

video.addEventListener('pointerdown', (e) => {
  if (!deviceW || !deviceH) return;
  // Without this, the browser's default mousedown behavior (shift focus
  // to body, since <video> isn't itself focusable) wins over our explicit
  // focus() call below, and the hidden text input never actually gets
  // focus -- so keydown/input events on it never fire.
  e.preventDefault();
  video.setPointerCapture(e.pointerId);
  const { x, y } = pointToDevice(e);
  sendControl(encodeInjectTouch(ACTION_DOWN, x, y, deviceW, deviceH, { buttons: e.buttons }));
  focusCatcher.focus();
});

video.addEventListener('pointermove', (e) => {
  if (!deviceW || !deviceH || e.buttons === 0) return;
  const { x, y } = pointToDevice(e);
  sendControl(encodeInjectTouch(ACTION_MOVE, x, y, deviceW, deviceH, { buttons: e.buttons }));
});

function pointerEnd(e) {
  if (!deviceW || !deviceH) return;
  const { x, y } = pointToDevice(e);
  sendControl(encodeInjectTouch(ACTION_UP, x, y, deviceW, deviceH, { pressure: 0, buttons: 0 }));
}
video.addEventListener('pointerup', pointerEnd);
video.addEventListener('pointercancel', pointerEnd);

video.addEventListener('wheel', (e) => {
  if (!deviceW || !deviceH) return;
  e.preventDefault();
  const { x, y } = pointToDevice(e);
  sendControl(encodeInjectScroll(x, y, deviceW, deviceH, e.deltaX, -e.deltaY, 0));
}, { passive: false });

video.addEventListener('contextmenu', (e) => e.preventDefault());

// --- Keyboard input: navigation keys via keycode, text via INJECT_TEXT ---

focusCatcher.addEventListener('keydown', (e) => {
  const keycode = ANDROID_KEYCODES[e.code];
  if (keycode !== undefined) {
    e.preventDefault();
    sendControl(encodeInjectKeycode(ACTION_DOWN, keycode));
  }
});

focusCatcher.addEventListener('keyup', (e) => {
  const keycode = ANDROID_KEYCODES[e.code];
  if (keycode !== undefined) {
    e.preventDefault();
    sendControl(encodeInjectKeycode(ACTION_UP, keycode));
  }
});

focusCatcher.addEventListener('input', () => {
  if (focusCatcher.value) {
    sendControl(encodeInjectText(focusCatcher.value));
    focusCatcher.value = '';
  }
});

connect();
