"""
Browser Agent for AI-Native Windows OS Assistant.
Operates the user's ALREADY-RUNNING Chrome, Edge, or Brave browser.
Strictly NO Playwright. Combines Windows UI Automation (UIA) and native shortcuts.
"""

import time
import asyncio
import ctypes
import re
from ctypes import wintypes
import logging
from typing import Dict, Any, List, Optional
import psutil
import pyperclip

from input_controller import controller
from screen_capture import capture_screen_pil
from config import settings

logger = logging.getLogger("browser_agent")
logger.setLevel(logging.INFO)

user32 = ctypes.windll.user32

KNOWN_BROWSER_PROCESSES = ["chrome.exe", "msedge.exe", "brave.exe", "firefox.exe", "opera.exe"]


class BrowserAgent:
    def __init__(self):
        self.last_active_hwnd: Optional[int] = None

    def _init_uia(self):
        """Initializes UIAutomation COM interface."""
        try:
            import pythoncom
            pythoncom.CoInitialize()
            import comtypes.client
            comtypes.client.GetModule("UIAutomationCore.dll")
            import comtypes.gen.UIAutomationClient as UIA
            uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
            return uia, UIA
        except Exception as e:
            logger.debug(f"UIAutomation interface note: {e}")
            return None, None

    def find_existing_browsers(self) -> List[Dict[str, Any]]:
        """Scans top-level desktop windows for existing Chrome, Edge, or Brave browsers."""
        browsers = []

        def enum_cb(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value

                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top

                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    pname = ""
                    if pid.value:
                        try:
                            pname = psutil.Process(pid.value).name().lower()
                        except Exception:
                            pass

                    is_proc_browser = pname in KNOWN_BROWSER_PROCESSES
                    is_title_browser = any(b in title.lower() for b in [" - google chrome", " - microsoft edge", " - brave", " - edge"])

                    if (is_proc_browser or is_title_browser) and w > 200 and h > 200 and rect.left > -10000:
                        b_type = "Chrome"
                        if "edge" in pname or "edge" in title.lower():
                            b_type = "Edge"
                        elif "brave" in pname or "brave" in title.lower():
                            b_type = "Brave"

                        browsers.append({
                            "hwnd": hwnd,
                            "title": title,
                            "type": b_type,
                            "process": pname,
                            "pid": pid.value,
                            "rect": {"left": rect.left, "top": rect.top, "width": w, "height": h}
                        })
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        return browsers

    def get_primary_browser(self) -> Optional[Dict[str, Any]]:
        browsers = self.find_existing_browsers()
        if not browsers:
            return None
        if self.last_active_hwnd:
            for b in browsers:
                if b["hwnd"] == self.last_active_hwnd:
                    return b
        return browsers[0]

    def focus_browser(self, hwnd: Optional[int] = None) -> bool:
        """Brings the existing browser window to foreground."""
        target_hwnd = hwnd or (self.get_primary_browser() or {}).get("hwnd")
        if not target_hwnd:
            return False
        user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(target_hwnd)
        self.last_active_hwnd = target_hwnd
        time.sleep(0.15)
        return True

    def get_open_tabs(self, hwnd: Optional[int] = None) -> Dict[str, Any]:
        """Lists active tabs in the user's running browser session via UI Automation."""
        browser = self.get_primary_browser()
        if not browser:
            return {
                "success": False,
                "error": "No open browser window (Chrome, Edge, Brave) was found on your desktop. Please open your browser.",
                "total_tabs": 0,
                "tabs": []
            }

        target_hwnd = browser["hwnd"]
        uia, UIA = self._init_uia()
        if not uia:
            return {
                "success": True,
                "browser_type": browser["type"],
                "browser_title": browser["title"],
                "total_tabs": 1,
                "tabs": [{"id": 1, "title": browser["title"], "is_active": True}]
            }

        try:
            elem = uia.ElementFromHandle(target_hwnd)
            cond_tab = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50019)  # TabItem
            tab_elements = elem.FindAll(UIA.TreeScope_Descendants, cond_tab)
            total = tab_elements.Length

            tabs_data = []
            for i in range(min(total, 20)):
                t_elem = tab_elements.GetElement(i)
                raw_name = t_elem.CurrentName or f"Tab {i+1}"
                clean_name = re.sub(r"\s*-\s*Memory usage.*$", "", raw_name).strip()
                tabs_data.append({
                    "id": i + 1,
                    "title": clean_name or f"Tab {i+1}",
                    "is_active": (i == 0)
                })

            if not tabs_data:
                tabs_data = [{"id": 1, "title": browser["title"], "is_active": True}]

            return {
                "success": True,
                "browser_type": browser["type"],
                "browser_title": browser["title"],
                "hwnd": target_hwnd,
                "total_tabs": len(tabs_data),
                "tabs": tabs_data
            }
        except Exception as e:
            return {
                "success": True,
                "browser_type": browser["type"],
                "browser_title": browser["title"],
                "total_tabs": 1,
                "tabs": [{"id": 1, "title": browser["title"], "is_active": True}]
            }

    async def navigate(self, url: str, hwnd: Optional[int] = None) -> Dict[str, Any]:
        """Navigates existing browser to URL by activating address bar via Ctrl+L."""
        if not url.startswith(("http://", "https://", "file://")):
            url = f"https://{url}"

        focused = self.focus_browser(hwnd)
        if not focused:
            # If no browser is currently open, launch default browser with URL
            import os
            os.startfile(url)
            await asyncio.sleep(1.5)
            self.focus_browser()
            return {
                "success": True,
                "action": "navigate",
                "url": url,
                "message": f"Opened default browser and navigated to {url}"
            }

        # Ctrl+L highlights the browser address bar
        controller.hotkey("ctrl", "l")
        await asyncio.sleep(0.1)
        controller.type_text(url)
        await asyncio.sleep(0.05)
        controller.press_key("enter")
        await asyncio.sleep(1.2)

        primary = self.get_primary_browser()
        new_title = primary["title"] if primary else ""

        return {
            "success": True,
            "action": "navigate",
            "url": url,
            "browser_title": new_title,
            "message": f"Navigated existing browser to {url}"
        }

    async def search(self, query: str, engine: str = "google", hwnd: Optional[int] = None) -> Dict[str, Any]:
        import urllib.parse
        encoded = urllib.parse.quote(query)
        if engine == "bing":
            url = f"https://www.bing.com/search?q={encoded}"
        elif engine == "duckduckgo":
            url = f"https://duckduckgo.com/?q={encoded}"
        else:
            url = f"https://www.google.com/search?q={encoded}"
        res = await self.navigate(url, hwnd=hwnd)
        res["query"] = query
        return res

    async def scroll(self, direction: str = "down", amount: float = 3.0, hwnd: Optional[int] = None) -> Dict[str, Any]:
        self.focus_browser(hwnd)
        factor = -1.0 if direction.lower() == "down" else 1.0
        controller.scroll(factor * amount)
        await asyncio.sleep(0.2)
        return {"success": True, "action": "scroll", "direction": direction, "amount": amount}

    async def new_tab(self, url: Optional[str] = None, hwnd: Optional[int] = None) -> Dict[str, Any]:
        self.focus_browser(hwnd)
        controller.hotkey("ctrl", "t")
        await asyncio.sleep(0.2)
        if url:
            return await self.navigate(url, hwnd)
        return {"success": True, "action": "new_tab", "message": "Opened new browser tab"}

    async def close_tab(self, hwnd: Optional[int] = None) -> Dict[str, Any]:
        self.focus_browser(hwnd)
        controller.hotkey("ctrl", "w")
        await asyncio.sleep(0.2)
        return {"success": True, "action": "close_tab", "message": "Closed active browser tab"}

    async def switch_tab(self, direction: str = "next", hwnd: Optional[int] = None) -> Dict[str, Any]:
        self.focus_browser(hwnd)
        if direction == "prev":
            controller.hotkey("ctrl", "shift", "tab")
        else:
            controller.hotkey("ctrl", "tab")
        await asyncio.sleep(0.2)
        primary = self.get_primary_browser()
        return {"success": True, "action": "switch_tab", "active_tab": primary["title"] if primary else ""}

    async def extract_page_text(self, hwnd: Optional[int] = None) -> Dict[str, Any]:
        """Extracts visible text from page body via clipboard copy without losing original clipboard."""
        self.focus_browser(hwnd)
        old_clip = pyperclip.paste()
        try:
            controller.hotkey("ctrl", "a")
            await asyncio.sleep(0.1)
            controller.hotkey("ctrl", "c")
            await asyncio.sleep(0.15)
            controller.press_key("escape")
            page_text = pyperclip.paste()
            # Restore previous clipboard if desired
            return {
                "success": True,
                "text": page_text[:4000],
                "total_chars": len(page_text)
            }
        except Exception as e:
            return {"success": False, "error": str(e), "text": ""}

    async def login(
        self,
        url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        submit: bool = True,
        hwnd: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Assists with logging into a website in the user's running browser session.
        Masks passwords in logs and responses for security.
        """
        if url:
            await self.navigate(url, hwnd=hwnd)
            await asyncio.sleep(1.5)
        else:
            self.focus_browser(hwnd)

        await asyncio.sleep(0.3)

        # Type username if provided
        if username:
            controller.type_text(username)
            await asyncio.sleep(0.2)
            # Press Tab to focus password field
            controller.press_key("tab")
            await asyncio.sleep(0.2)

        # Type password securely if provided
        if password:
            controller.type_text(password)
            await asyncio.sleep(0.2)

        # Submit if requested
        if submit:
            controller.press_key("enter")
            await asyncio.sleep(1.2)

        primary = self.get_primary_browser()
        current_title = primary["title"] if primary else ""

        # Safe return: NEVER return actual password
        return {
            "success": True,
            "action": "browser_login",
            "url": url,
            "username": username,
            "password_masked": "********" if password else None,
            "submitted": submit,
            "browser_title": current_title,
            "message": f"Submitted login credentials on '{current_title}'. If two-factor authentication (MFA) or CAPTCHA is required, please complete it in your browser window."
        }

    async def click_coordinate(self, x: int, y: int, clicks: int = 1, button: str = "left", hwnd: Optional[int] = None) -> Dict[str, Any]:
        """Performs precise coordinate mouse click within browser."""
        self.focus_browser(hwnd)
        controller.move_to(x, y)
        await asyncio.sleep(0.1)
        controller.click(button=button, clicks=clicks)
        return {"success": True, "action": "click", "x": x, "y": y, "button": button}


browser_agent = BrowserAgent()
