"""
Windows Input Controller using Native User32 APIs.
Handles mouse movement, clicks, scrolling, dragging, and keyboard keystrokes.
"""

import time
import ctypes
from ctypes import wintypes
from typing import Tuple, List, Optional
import pyperclip
from screen_capture import ensure_interactive_desktop

user32 = ctypes.windll.user32

# Mouse flags
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP = 0x0040
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000

# Keyboard flags
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004

VK_CODES = {
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "win": 0x5B,
    "windows": 0x5B,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
    "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B
}


class InputController:
    """Provides high-performance, DPI-normalized mouse and keyboard control."""

    def move_to(self, x: int, y: int):
        ensure_interactive_desktop()
        user32.SetCursorPos(int(x), int(y))

    def move_relative(self, dx: int, dy: int):
        ensure_interactive_desktop()
        # Method 1: native relative mouse event (smooth acceleration)
        user32.mouse_event(MOUSEEVENTF_MOVE, int(dx), int(dy), 0, 0)
        # Ensure position moved
        pt = wintypes.POINT()
        if not user32.GetCursorPos(ctypes.byref(pt)):
            user32.SetCursorPos(pt.x + int(dx), pt.y + int(dy))

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left", clicks: int = 1, double_click: bool = False, **kwargs):
        ensure_interactive_desktop()
        if double_click or kwargs.get("double", False):
            clicks = max(clicks, 2)

        if x is not None and y is not None:
            self.move_to(int(x), int(y))
            time.sleep(0.03)

        btn = str(button).lower().strip()
        if btn in ["right", "r", "2"]:
            down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
        elif btn in ["middle", "m", "3"]:
            down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
        else:
            down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

        for i in range(clicks):
            user32.mouse_event(down_flag, 0, 0, 0, 0)
            time.sleep(0.04)
            user32.mouse_event(up_flag, 0, 0, 0, 0)
            if i < clicks - 1:
                time.sleep(0.08)

    def mouse_down(self, button: str = "left"):
        ensure_interactive_desktop()
        flag = MOUSEEVENTF_LEFTDOWN if button == "left" else MOUSEEVENTF_RIGHTDOWN
        user32.mouse_event(flag, 0, 0, 0, 0)

    def mouse_up(self, button: str = "left"):
        ensure_interactive_desktop()
        flag = MOUSEEVENTF_LEFTUP if button == "left" else MOUSEEVENTF_RIGHTUP
        user32.mouse_event(flag, 0, 0, 0, 0)

    def scroll(self, amount: float):
        ensure_interactive_desktop()
        # Native Windows WHEEL_DELTA is 120
        clicks = int(amount * 120)
        user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, clicks, 0)

    def key_down(self, key_name: str):
        ensure_interactive_desktop()
        k = key_name.lower().strip()
        vk = VK_CODES.get(k)
        if vk is None and len(k) == 1:
            vk = ord(k.upper())
        if vk:
            user32.keybd_event(vk, 0, 0, 0)

    def key_up(self, key_name: str):
        ensure_interactive_desktop()
        k = key_name.lower().strip()
        vk = VK_CODES.get(k)
        if vk is None and len(k) == 1:
            vk = ord(k.upper())
        if vk:
            user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)

    def press_key(self, key_name: str):
        ensure_interactive_desktop()
        self.key_down(key_name)
        time.sleep(0.03)
        self.key_up(key_name)

    def hotkey(self, *keys):
        """Simulates simultaneous key combinations, e.g. hotkey('ctrl', 'l')."""
        ensure_interactive_desktop()
        for k in keys:
            self.key_down(k)
            time.sleep(0.02)
        time.sleep(0.05)
        for k in reversed(keys):
            self.key_up(k)
            time.sleep(0.02)

    def type_text(self, text: str):
        """Types unicode string into foreground window safely. Uses clipboard paste for multi-word or large text."""
        ensure_interactive_desktop()
        if not text:
            return
        if len(text) > 15 or "\n" in text or "http" in text:
            self.paste_text(text)
            return

        for ch in text:
            code = ord(ch)
            user32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
            user32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
            time.sleep(0.005)

    def paste_text(self, text: str):
        """Pastes large text blocks via clipboard to avoid key drop."""
        ensure_interactive_desktop()
        try:
            pyperclip.copy(text)
            time.sleep(0.05)
            self.hotkey("ctrl", "v")
            time.sleep(0.1)
        except Exception as e:
            # Fallback to direct key typing
            for ch in text:
                code = ord(ch)
                user32.keybd_event(0, code, KEYEVENTF_UNICODE, 0)
                user32.keybd_event(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0)
                time.sleep(0.005)


controller = InputController()
