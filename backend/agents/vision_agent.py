"""
Vision Agent for AI-Native Windows OS Assistant.
Performs multimodal desktop screen understanding, error explanation,
and UI coordinate grounding using Gemini Flash / Groq Vision.
"""

import io
import time
import json
import re
import logging
import ctypes
from ctypes import wintypes
from typing import Dict, Any, List, Optional, Tuple

from screen_capture import capture_screen_pil, get_screenshot_base64, get_screen_dimensions
from llm_gateway import llm_gateway

logger = logging.getLogger("vision_agent")
logger.setLevel(logging.INFO)

user32 = ctypes.windll.user32


class VisionAgent:
    def __init__(self):
        self.last_capture_time: float = 0.0
        self.last_screenshot_b64: Optional[str] = None
        self.screen_width, self.screen_height = get_screen_dimensions()

    def get_active_window_info(self) -> Dict[str, Any]:
        """Returns details about foreground window."""
        fg = user32.GetForegroundWindow()
        if not fg:
            return {"hwnd": 0, "title": "", "rect": {"left": 0, "top": 0, "width": 0, "height": 0}}

        length = user32.GetWindowTextLengthW(fg)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(fg, buff, length + 1)
        title = buff.value

        rect = wintypes.RECT()
        user32.GetWindowRect(fg, ctypes.byref(rect))
        w = max(0, rect.right - rect.left)
        h = max(0, rect.bottom - rect.top)

        return {
            "hwnd": fg,
            "title": title,
            "rect": {"left": rect.left, "top": rect.top, "width": w, "height": h}
        }

    def _generate_local_screen_summary(self, active_win: Dict[str, Any]) -> str:
        """Deterministic local fallback summary when no cloud API key is present."""
        active_title = (active_win.get("title") or "").strip() or "Desktop"
        visible = []

        def enum_cb(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    t = buff.value.strip()
                    if t and t not in ["Program Manager", "Settings", active_title]:
                        if t not in visible:
                            visible.append(t)
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

        other_str = f" Other visible apps: {', '.join(visible[:3])}." if visible else ""
        return f"Currently active window: **{active_title}** on a {self.screen_width}x{self.screen_height} display.{other_str}"

    async def analyze_screen(self, prompt: Optional[str] = None) -> Dict[str, Any]:
        """Analyzes screen using Gemini Flash or local introspection."""
        active_win = self.get_active_window_info()
        b64 = get_screenshot_base64(scale=0.85, quality=80)
        self.last_screenshot_b64 = b64
        self.last_capture_time = time.time()

        user_prompt = prompt or (
            "Analyze this Windows desktop screenshot and provide a concise, high-level summary (2-3 sentences). "
            "Highlight the active application, open windows, and any visible errors or tasks."
        )

        system_prompt = (
            f"You are the Vision Agent for a Windows OS Assistant.\n"
            f"Screen Resolution: {self.screen_width}x{self.screen_height}.\n"
            f"Foreground Window: '{active_win.get('title')}'.\n"
            f"Provide a concise, grounded factual summary."
        )

        res = await llm_gateway.vision_analyze(
            prompt=user_prompt,
            image_b64=b64,
            system_prompt=system_prompt
        )

        analysis = res.get("analysis", "").strip()
        if not res.get("success") or not analysis:
            analysis = self._generate_local_screen_summary(active_win)

        return {
            "success": True,
            "analysis": analysis,
            "summary": analysis,
            "message": analysis,
            "active_window": active_win,
            "timestamp": self.last_capture_time
        }

    async def explain_error_on_screen(self) -> Dict[str, Any]:
        """Scans screen for dialog errors, tracebacks, or warning alerts."""
        prompt = (
            "Examine this desktop screen specifically for any error messages, crash dialogs, terminal tracebacks, "
            "or warning alerts. If an error is found:\n"
            "1. What is the exact error message or code?\n"
            "2. Which application threw it?\n"
            "3. What is the root cause?\n"
            "4. Provide step-by-step instructions or commands to resolve it."
        )
        return await self.analyze_screen(prompt=prompt)

    async def locate_target_coordinates(self, target_description: str) -> Dict[str, Any]:
        """Locates screen coordinates (x, y) for an on-screen UI element."""
        # Step 1: Attempt Windows UI Automation discovery
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import comtypes.client
            comtypes.client.GetModule("UIAutomationCore.dll")
            import comtypes.gen.UIAutomationClient as UIA
            uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)

            active_win = self.get_active_window_info()
            fg = active_win.get("hwnd")
            if fg:
                elem = uia.ElementFromHandle(fg)
                if elem:
                    cond = uia.CreateTrueCondition()
                    walker = uia.CreateTreeWalker(cond)
                    target_lower = target_description.lower()

                    def search_tree(el, depth=0):
                        if depth > 5:
                            return None
                        child = walker.GetFirstChildElement(el)
                        while child:
                            try:
                                name = child.CurrentName or ""
                                if name and target_lower in name.lower():
                                    r = child.CurrentBoundingRectangle
                                    if r.right > r.left and r.bottom > r.top:
                                        return ((r.left + r.right) // 2, (r.top + r.bottom) // 2, name)
                                res = search_tree(child, depth + 1)
                                if res:
                                    return res
                            except Exception:
                                pass
                            child = walker.GetNextSiblingElement(child)
                        return None

                    found = search_tree(elem)
                    if found:
                        cx, cy, ename = found
                        return {"success": True, "method": "uiautomation", "x": cx, "y": cy, "target": target_description}
        except Exception:
            pass

        # Step 2: Fallback to Vision LLM coordinate prediction
        b64 = get_screenshot_base64(scale=1.0, quality=85)
        prompt = (
            f"You are a precise screen coordinate locator. "
            f"Find the target element: '{target_description}'. "
            f"Screen Resolution is {self.screen_width}x{self.screen_height}. "
            f"Return strict JSON: {{\"found\": true, \"x\": <int>, \"y\": <int>}} or {{\"found\": false}}."
        )
        res = await llm_gateway.vision_analyze(prompt, b64)
        if res.get("success"):
            text = res.get("analysis", "")
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group(0))
                    if data.get("found"):
                        return {"success": True, "method": "vision_llm", "x": int(data.get("x", 0)), "y": int(data.get("y", 0)), "target": target_description}
                except Exception:
                    pass

        return {"success": False, "error": f"Target element '{target_description}' could not be located on screen."}


vision_agent = VisionAgent()
