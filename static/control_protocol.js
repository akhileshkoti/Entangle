// Exact mirror of scrcpy_common/control_protocol.py -- keep both in sync.
const TYPE_INJECT_KEYCODE = 0;
const TYPE_INJECT_TEXT = 1;
const TYPE_INJECT_TOUCH_EVENT = 2;
const TYPE_INJECT_SCROLL_EVENT = 3;

const ACTION_DOWN = 0;
const ACTION_UP = 1;
const ACTION_MOVE = 2;

const POINTER_ID_MOUSE = 0xFFFFFFFFFFFFFFFFn;

function floatToU16Fp(f) {
  f = Math.max(0, Math.min(1, f));
  return Math.round(f * 0xFFFF);
}

function floatToI16Fp(f) {
  f = Math.max(-1, Math.min(1, f));
  return Math.round(f * 0x7FFF);
}

function encodeInjectKeycode(action, keycode, repeat = 0, metastate = 0) {
  const buf = new ArrayBuffer(14);
  const v = new DataView(buf);
  v.setUint8(0, TYPE_INJECT_KEYCODE);
  v.setUint8(1, action);
  v.setInt32(2, keycode, false);
  v.setInt32(6, repeat, false);
  v.setInt32(10, metastate, false);
  return buf;
}

function encodeInjectTouch(action, x, y, screenW, screenH, opts = {}) {
  const pointerId = opts.pointerId !== undefined ? BigInt(opts.pointerId) : POINTER_ID_MOUSE;
  const pressure = opts.pressure !== undefined ? opts.pressure : 1.0;
  const actionButton = opts.actionButton || 0;
  const buttons = opts.buttons || 0;

  const buf = new ArrayBuffer(32);
  const v = new DataView(buf);
  v.setUint8(0, TYPE_INJECT_TOUCH_EVENT);
  v.setUint8(1, action);
  v.setBigUint64(2, pointerId, false);
  v.setInt32(10, Math.round(x), false);
  v.setInt32(14, Math.round(y), false);
  v.setUint16(18, screenW, false);
  v.setUint16(20, screenH, false);
  v.setUint16(22, floatToU16Fp(pressure), false);
  v.setInt32(24, actionButton, false);
  v.setInt32(28, buttons, false);
  return buf;
}

function encodeInjectScroll(x, y, screenW, screenH, hscroll, vscroll, buttons = 0) {
  const buf = new ArrayBuffer(21);
  const v = new DataView(buf);
  v.setUint8(0, TYPE_INJECT_SCROLL_EVENT);
  v.setInt32(1, Math.round(x), false);
  v.setInt32(5, Math.round(y), false);
  v.setUint16(9, screenW, false);
  v.setUint16(11, screenH, false);
  v.setInt16(13, floatToI16Fp(hscroll / 16), false);
  v.setInt16(15, floatToI16Fp(vscroll / 16), false);
  v.setInt32(17, buttons, false);
  return buf;
}

function encodeInjectText(text) {
  const data = new TextEncoder().encode(text);
  const buf = new ArrayBuffer(5 + data.length);
  const v = new DataView(buf);
  v.setUint8(0, TYPE_INJECT_TEXT);
  v.setUint32(1, data.length, false);
  new Uint8Array(buf, 5).set(data);
  return buf;
}
