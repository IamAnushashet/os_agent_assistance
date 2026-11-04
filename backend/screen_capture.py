"""
Fast, DPI-Aware Desktop Screen Capture using MSS and Win32 APIs.
Supports live frame streaming, cursor rendering, and base64 encoding for Vision LLM.
"""

import io
import base64
import ctypes
from ctypes import wintypes
import logging
from typing import Tuple, Optional, List, Dict, Any
from PIL import Image, ImageDraw
import mss

logger = logging.getLogger("screen_capture")
logger.setLevel(logging.INFO)

user32 = ctypes.windll.user32

# Enable Per-Monitor DPI Awareness V2 if available on Windows 10/11
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass

_sct_instance = None


def ensure_interactive_desktop():
    """
    Attaches current thread to the interactive 'default' desktop on WinSta0.
    Required on Windows so worker threads running in FastAPI/anyio can perform BitBlt.
    """
    try:
        hdesk = user32.OpenDesktopW("default", 0, False, 0x01FF)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        pass


def get_screen_dimensions() -> Tuple[int, int]:
    """Returns primary monitor screen resolution in virtual screen coordinates."""
    w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
    h = user32.GetSystemMetrics(1)  # SM_CYSCREEN
    return max(w, 800), max(h, 600)


def create_fallback_image(width: int = 1920, height: int = 1080) -> Image.Image:
    """Creates a sleek fallback image if GDI screen grab is temporarily unavailable."""
    img = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)
    text = "Windows Desktop Mirror Active\nSynchronizing display stream..."
    draw.text((width // 2 - 120, height // 2 - 20), text, fill=(148, 163, 184))
    return img


def get_cursor_position() -> Tuple[int, int, bool]:
    """Returns current mouse cursor coordinates (x, y, visible)."""
    ensure_interactive_desktop()
    try:
        class POINT(ctypes.Structure):
            _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]

        class CURSORINFO(ctypes.Structure):
            _fields_ = [
                ('cbSize', wintypes.DWORD),
                ('flags', wintypes.DWORD),
                ('hCursor', ctypes.c_void_p),
                ('ptScreenPos', POINT)
            ]

        ci = CURSORINFO()
        ci.cbSize = ctypes.sizeof(CURSORINFO)
        if user32.GetCursorInfo(ctypes.byref(ci)) and (ci.flags & 1):
            return ci.ptScreenPos.x, ci.ptScreenPos.y, True

        pt = POINT()
        if user32.GetCursorPos(ctypes.byref(pt)):
            return pt.x, pt.y, True
    except Exception:
        pass
    return 0, 0, False


def draw_cursor_on_image(img: Image.Image, scale: float = 1.0) -> Image.Image:
    """Draws a high-precision, high-contrast cursor on the screenshot frame."""
    cx, cy, visible = get_cursor_position()
    if not visible:
        return img

    if scale and scale < 1.0:
        x = int(cx * scale)
        y = int(cy * scale)
        s = max(0.65, scale)
    else:
        x = cx
        y = cy
        s = 1.0

    if 0 <= x < img.width and 0 <= y < img.height:
        draw = ImageDraw.Draw(img)
        # Standard Windows pointer polygon
        cursor_poly = [
            (x, y),
            (x, y + int(22 * s)),
            (x + int(5 * s), y + int(17 * s)),
            (x + int(10 * s), y + int(26 * s)),
            (x + int(14 * s), y + int(24 * s)),
            (x + int(9 * s), y + int(15 * s)),
            (x + int(16 * s), y + int(15 * s))
        ]

        # Bold black border for contrast
        for dx in [-2, -1, 0, 1, 2]:
            for dy in [-2, -1, 0, 1, 2]:
                if abs(dx) + abs(dy) <= 2:
                    draw.polygon([(px + dx, py + dy) for px, py in cursor_poly], fill=(0, 0, 0))

        # Crisp white interior
        draw.polygon(cursor_poly, fill=(255, 255, 255), outline=(0, 0, 0))
        # Electric cyan tip
        draw.ellipse((x - 1, y - 1, x + 2, y + 2), fill=(6, 182, 212))

    return img


def get_active_monitor_index() -> int:
    """Returns index of the monitor currently containing mouse cursor or foreground window."""
    try:
        user32 = ctypes.windll.user32
        cursor = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(cursor))
        cx, cy = cursor.x, cursor.y

        global _sct_instance
        if _sct_instance is None:
            _sct_instance = mss.MSS()

        for idx in range(1, len(_sct_instance.monitors)):
            m = _sct_instance.monitors[idx]
            if m["left"] <= cx < m["left"] + m["width"] and m["top"] <= cy < m["top"] + m["height"]:
                return idx
    except Exception:
        pass
    return 1


def list_monitors() -> List[Dict[str, Any]]:
    """Lists all active physical monitors plus virtual combined multi-monitor desktop."""
    global _sct_instance
    try:
        if _sct_instance is None:
            _sct_instance = mss.MSS()
        res = []
        for idx, m in enumerate(_sct_instance.monitors):
            label = "All Screens (Combined Desktop)" if idx == 0 else f"Screen {idx}"
            if m.get("is_primary"):
                label += " (Primary)"
            res.append({
                "index": idx,
                "label": label,
                "left": m["left"],
                "top": m["top"],
                "width": m["width"],
                "height": m["height"],
                "is_primary": bool(m.get("is_primary", False))
            })
        return res
    except Exception:
        w, h = get_screen_dimensions()
        return [{"index": 1, "label": "Screen 1 (Primary)", "left": 0, "top": 0, "width": w, "height": h, "is_primary": True}]


def capture_screen_pil(
    scale: float = 1.0,
    draw_cursor: bool = True,
    monitor_index: Optional[int] = None
) -> Image.Image:
    """
    Captures display and renders mouse cursor.
    Supports specific monitor (1, 2, ...), all monitors combined (0),
    or auto-detection of the monitor containing active window/cursor.
    """
    global _sct_instance
    ensure_interactive_desktop()
    img = None
    target_offset = (0, 0)

    # Primary capture attempt: MSS
    try:
        if _sct_instance is None:
            _sct_instance = mss.MSS()

        # Select target monitor
        if monitor_index is not None and 0 <= monitor_index < len(_sct_instance.monitors):
            target_mon = _sct_instance.monitors[monitor_index]
        else:
            # Auto-detect active screen
            active_idx = get_active_monitor_index()
            if active_idx < len(_sct_instance.monitors):
                target_mon = _sct_instance.monitors[active_idx]
            elif len(_sct_instance.monitors) > 1:
                target_mon = _sct_instance.monitors[1]
            else:
                target_mon = _sct_instance.monitors[0]

        target_offset = (target_mon["left"], target_mon["top"])
        sct_img = _sct_instance.grab(target_mon)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    except Exception:
        # Fallback to PIL ImageGrab if available
        try:
            from PIL import ImageGrab
            all_screens = (monitor_index == 0)
            img = ImageGrab.grab(all_screens=all_screens)
        except Exception:
            w, h = get_screen_dimensions()
            img = create_fallback_image(w, h)

    if scale != 1.0 and 0.1 <= scale <= 2.0 and img is not None:
        new_w = max(1, int(img.width * scale))
        new_h = max(1, int(img.height * scale))
        img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)

    if draw_cursor and img is not None:
        img = draw_cursor_on_image(img, scale=scale)

    return img


def get_screenshot_bytes(
    scale: float = 0.75,
    quality: int = 70,
    draw_cursor: bool = True,
    monitor_index: Optional[int] = None
) -> bytes:
    img = capture_screen_pil(scale=scale, draw_cursor=draw_cursor, monitor_index=monitor_index)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def get_screenshot_base64(scale: float = 0.85, quality: int = 80, monitor_index: Optional[int] = None) -> str:
    raw = get_screenshot_bytes(scale=scale, quality=quality, draw_cursor=True, monitor_index=monitor_index)
    return base64.b64encode(raw).decode("utf-8")
