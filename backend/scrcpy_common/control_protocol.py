import struct

# Confirmed against server/src/main/java/com/genymobile/scrcpy/control/ControlMessage.java
# and ControlMessageReader.java at scrcpy tag v4.1.
TYPE_INJECT_KEYCODE = 0
TYPE_INJECT_TEXT = 1
TYPE_INJECT_TOUCH_EVENT = 2
TYPE_INJECT_SCROLL_EVENT = 3
TYPE_SET_DISPLAY_POWER = 10

ACTION_DOWN = 0  # KeyEvent.ACTION_DOWN / MotionEvent.ACTION_DOWN
ACTION_UP = 1  # KeyEvent.ACTION_UP / MotionEvent.ACTION_UP
ACTION_MOVE = 2  # MotionEvent.ACTION_MOVE

KEYCODE_HOME = 3
KEYCODE_BACK = 4

POINTER_ID_MOUSE = 0xFFFFFFFFFFFFFFFF


def _float_to_u16fp(f: float) -> int:
    f = max(0.0, min(1.0, f))
    return round(f * 0xFFFF)


def _float_to_i16fp(f: float) -> int:
    f = max(-1.0, min(1.0, f))
    return round(f * 0x7FFF)


def encode_inject_keycode(action: int, keycode: int, repeat: int = 0, metastate: int = 0) -> bytes:
    return struct.pack(">BBiii", TYPE_INJECT_KEYCODE, action, keycode, repeat, metastate)


def encode_inject_touch(
    action: int,
    x: int,
    y: int,
    screen_w: int,
    screen_h: int,
    pointer_id: int = POINTER_ID_MOUSE,
    pressure: float = 1.0,
    action_button: int = 0,
    buttons: int = 0,
) -> bytes:
    return struct.pack(
        ">BBQiiHHHii",
        TYPE_INJECT_TOUCH_EVENT,
        action,
        pointer_id,
        x,
        y,
        screen_w,
        screen_h,
        _float_to_u16fp(pressure),
        action_button,
        buttons,
    )


def encode_inject_scroll(
    x: int, y: int, screen_w: int, screen_h: int, hscroll: float, vscroll: float, buttons: int = 0
) -> bytes:
    return struct.pack(
        ">BiiHHhhi",
        TYPE_INJECT_SCROLL_EVENT,
        x,
        y,
        screen_w,
        screen_h,
        _float_to_i16fp(hscroll / 16),
        _float_to_i16fp(vscroll / 16),
        buttons,
    )


def encode_inject_text(text: str) -> bytes:
    data = text.encode("utf-8")
    return struct.pack(">BI", TYPE_INJECT_TEXT, len(data)) + data


def encode_set_display_power(on: bool) -> bytes:
    return struct.pack(">B?", TYPE_SET_DISPLAY_POWER, on)
