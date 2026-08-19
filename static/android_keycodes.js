// KeyboardEvent.code -> Android AKEYCODE_*, for non-printable/navigation
// keys. Printable characters are sent via INJECT_TEXT instead (handles
// IME/composed input correctly, which per-keycode mapping can't).
const ANDROID_KEYCODES = {
  Enter: 66,
  NumpadEnter: 66,
  Backspace: 67,
  Tab: 61,
  Escape: 111,
  Space: 62,
  Delete: 112,
  ArrowUp: 19,
  ArrowDown: 20,
  ArrowLeft: 21,
  ArrowRight: 22,
  Home: 122,
  End: 123,
  PageUp: 92,
  PageDown: 93,
};
