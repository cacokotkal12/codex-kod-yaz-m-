import os
import time

IS_WIN = os.name == "nt"

try:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    SendInput = user32.SendInput

    KEYEVENTF_SCANCODE = 0x0008
    KEYEVENTF_KEYUP = 0x0002

    SC_ENTER = 0x1C
    SC_V = 0x2F
    SC_LCTRL = 0x1D

    PUL = ctypes.POINTER(ctypes.c_ulong)

    class KeyBdInput(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", PUL),
        ]

    class Input_I(ctypes.Union):
        _fields_ = [("ki", KeyBdInput)]

    class Input(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("ii", Input_I)]

    def _send_scancode(scan_code: int, key_up: bool = False) -> None:
        extra = ctypes.c_ulong(0)
        flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if key_up else 0)
        ii_ = Input_I()
        ii_.ki = KeyBdInput(0, scan_code, flags, 0, ctypes.pointer(extra))
        SendInput(1, ctypes.pointer(Input(ctypes.c_ulong(1), ii_)), ctypes.sizeof(Input))

    def _tap_scancode(scan_code: int, delay_s: float = 0.005) -> None:
        _send_scancode(scan_code, False)
        time.sleep(delay_s)
        _send_scancode(scan_code, True)

    def send_enter_directinput() -> None:
        _tap_scancode(SC_ENTER)

    def send_ctrl_v_directinput() -> None:
        _send_scancode(SC_LCTRL, False)
        time.sleep(0.005)
        _tap_scancode(SC_V)
        time.sleep(0.005)
        _send_scancode(SC_LCTRL, True)

except Exception:
    user32 = None

    def send_enter_directinput() -> None:
        pass

    def send_ctrl_v_directinput() -> None:
        pass


def send_enter() -> None:
    if IS_WIN and user32:
        send_enter_directinput()


def send_ctrl_v() -> None:
    if IS_WIN and user32:
        send_ctrl_v_directinput()
