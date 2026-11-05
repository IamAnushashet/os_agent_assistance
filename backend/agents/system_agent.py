"""
System Agent for AI-Native Windows OS Assistant.
Handles real-time hardware telemetry, process monitoring, application launching,
and validated PowerShell command execution.
"""

import os
import time
import subprocess
import logging
from typing import Dict, Any, List, Optional
import psutil
import ctypes
from ctypes import wintypes

from input_controller import controller

logger = logging.getLogger("system_agent")
logger.setLevel(logging.INFO)

user32 = ctypes.windll.user32

COMMON_APP_MAP = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "code": "code",
    "vs code": "code",
    "vscode": "code",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "pwsh": "pwsh.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "files": "explorer.exe",
    "paint": "mspaint.exe",
    "wordpad": "write.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "brave": "brave.exe",
    "settings": "ms-settings:",
    "clock": "ms-clock:",
    "alarms": "ms-clock:",
    "alarms_clock": "ms-clock:",
    "calendar": "outlookcal:",
    "mail": "outlookmail:",
    "powerpoint": "powerpnt.exe",
    "ppt": "powerpnt.exe",
    "word": "winword.exe",
    "ms word": "winword.exe",
    "excel": "excel.exe",
    "ms excel": "excel.exe",
    "snipping tool": "snippingtool.exe",
    "snip": "snippingtool.exe"
}

BLOCKED_COMMAND_PATTERNS = [
    "format-volume", "rmdir /s /q c:\\", "del /f /s /q c:\\", "remove-item -recurse -force c:\\",
    "stop-computer", "restart-computer", "set-executionpolicy unrestricted", "reg delete hklm"
]


class SystemAgent:
    def get_system_telemetry(self) -> Dict[str, Any]:
        """Collects real-time hardware metrics via psutil."""
        try:
            cpu_pct = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count(logical=True)
            mem = psutil.virtual_memory()

            disks = []
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disks.append({
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "total_gb": round(usage.total / (1024**3), 1),
                        "free_gb": round(usage.free / (1024**3), 1),
                        "used_percent": usage.percent
                    })
                except Exception:
                    pass

            battery = psutil.sensors_battery()
            batt_info = None
            if battery:
                batt_info = {
                    "percent": battery.percent,
                    "power_plugged": battery.power_plugged,
                    "seconds_left": battery.secsleft if battery.secsleft > 0 else None
                }

            uptime_sec = time.time() - psutil.boot_time()

            return {
                "success": True,
                "cpu": {"percent": cpu_pct, "cores": cpu_count},
                "memory": {
                    "total_gb": round(mem.total / (1024**3), 1),
                    "used_gb": round(mem.used / (1024**3), 1),
                    "percent": mem.percent
                },
                "disks": disks,
                "battery": batt_info,
                "uptime_hours": round(uptime_sec / 3600, 1)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def diagnose_system(self) -> Dict[str, Any]:
        """Diagnoses bottlenecks and identifies top memory-consuming processes."""
        telem = self.get_system_telemetry()
        issues = []
        if telem.get("cpu", {}).get("percent", 0) > 85:
            issues.append("CPU usage is high (>85%).")
        if telem.get("memory", {}).get("percent", 0) > 85:
            issues.append("RAM usage is high (>85%).")

        top_procs = self.list_processes(limit=5, sort_by="memory")

        return {
            "success": True,
            "telemetry": telem,
            "status": "Warning" if issues else "Healthy",
            "detected_issues": issues,
            "top_processes": top_procs.get("processes", []),
            "recommendation": "Close unused background applications." if issues else "System operating within optimal parameters."
        }

    def list_processes(self, limit: int = 15, sort_by: str = "memory") -> Dict[str, Any]:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = p.info
                if info['name']:
                    procs.append({
                        "pid": info['pid'],
                        "name": info['name'],
                        "cpu_pct": round(info['cpu_percent'] or 0, 1),
                        "memory_pct": round(info['memory_percent'] or 0, 1)
                    })
            except Exception:
                pass

        if sort_by == "cpu":
            procs.sort(key=lambda x: x["cpu_pct"], reverse=True)
        else:
            procs.sort(key=lambda x: x["memory_pct"], reverse=True)

        return {"success": True, "total": len(procs), "processes": procs[:limit]}

    def terminate_process(self, target: Any) -> Dict[str, Any]:
        """Terminates process by PID or executable name."""
        try:
            pid = None
            pname = ""
            if isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
                pid = int(target)
                p = psutil.Process(pid)
                pname = p.name()
                p.terminate()
            else:
                pname = str(target).lower()
                for p in psutil.process_iter(['pid', 'name']):
                    if p.info['name'] and p.info['name'].lower() == pname:
                        p.terminate()
                        pid = p.info['pid']
                        break
            if pid:
                return {"success": True, "pid": pid, "name": pname, "message": f"Terminated process {pname} (PID {pid})"}
            return {"success": False, "error": f"No running process found matching '{target}'"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def launch_app(self, app_name: str) -> Dict[str, Any]:
        """Launches an approved application by name into an independent desktop window."""
        k = app_name.lower().strip()
        exe = COMMON_APP_MAP.get(k, app_name)
        try:
            # 1. Native Windows ShellExecute: launches GUI and standalone windows
            try:
                os.startfile(exe)
            except Exception:
                # 2. Interactive Console fallback for CLI shells
                if k in ["cmd", "command prompt", "cmd.exe", "command"]:
                    subprocess.Popen('start "Command Prompt" cmd.exe /k', shell=True)
                elif k in ["powershell", "powershell.exe", "pwsh", "pwsh.exe"]:
                    subprocess.Popen('start "Windows PowerShell" powershell.exe -NoExit', shell=True)
                else:
                    creation_flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0x00000010)
                    subprocess.Popen(f'start "" "{exe}"', shell=True, creationflags=creation_flags)

            time.sleep(0.8)
            return {"success": True, "app": app_name, "executable": exe, "message": f"Launched '{app_name}' successfully."}
        except Exception as e:
            return {"success": False, "error": f"Could not launch application '{app_name}': {e}"}

    def wait_for_window(self, title_substr: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Waits for a desktop window containing title_substr to appear."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            wins = self.find_windows_by_title(title_substr)
            if wins:
                hwnd = wins[0]["hwnd"]
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                return {"success": True, "hwnd": hwnd, "title": wins[0]["title"]}
            time.sleep(0.3)

        # Fallback: Check if active foreground window can be utilized
        fg = user32.GetForegroundWindow()
        if fg:
            length = user32.GetWindowTextLengthW(fg)
            if length > 0:
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(fg, buff, length + 1)
                fg_title = buff.value
                return {
                    "success": True,
                    "hwnd": fg,
                    "title": fg_title,
                    "warning": f"Exact title '{title_substr}' not found, but foreground window '{fg_title}' is active."
                }

        return {"success": False, "error": f"Window with title matching '{title_substr}' did not appear within {timeout}s."}

    def find_windows_by_title(self, query: str) -> List[Dict[str, Any]]:
        results = []
        q_lower = query.lower().strip()
        candidates = {q_lower}
        if any(c in q_lower for c in ["cmd", "command prompt", "command", "cmd.exe", "dos"]):
            candidates.update(["command prompt", "cmd", "cmd.exe", "c:\\windows\\system32\\cmd.exe", "terminal", "windows terminal", "conhost"])
        elif any(c in q_lower for c in ["powershell", "pwsh"]):
            candidates.update(["powershell", "pwsh", "terminal", "windows terminal"])
        elif any(c in q_lower for c in ["calc", "calculator"]):
            candidates.update(["calculator", "calc"])
        elif any(c in q_lower for c in ["notepad", "note"]):
            candidates.update(["notepad", "untitled - notepad"])
        elif any(c in q_lower for c in ["chrome", "google chrome"]):
            candidates.update(["chrome", "google chrome"])
        elif any(c in q_lower for c in ["edge", "microsoft edge"]):
            candidates.update(["edge", "microsoft edge"])
        elif any(c in q_lower for c in ["brave"]):
            candidates.update(["brave"])

        def enum_cb(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    t = buff.value
                    t_lower = t.lower()
                    if any(cand in t_lower for cand in candidates):
                        results.append({"hwnd": hwnd, "title": t})
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        cb = WNDENUMPROC(enum_cb)

        # 1. Primary: EnumDesktopWindows via OpenInputDesktop (handles async threads & background workers)
        try:
            h_desk = user32.OpenInputDesktop(0, False, 0x0100)
            if not h_desk:
                h_desk = user32.GetThreadDesktop(ctypes.windll.kernel32.GetCurrentThreadId())
            if h_desk:
                user32.EnumDesktopWindows.argtypes = [wintypes.HANDLE, WNDENUMPROC, wintypes.LPARAM]
                user32.EnumDesktopWindows.restype = wintypes.BOOL
                user32.EnumDesktopWindows(h_desk, cb, 0)
        except Exception:
            pass

        # 2. Fallback: EnumWindows
        if not results:
            try:
                user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
                user32.EnumWindows.restype = wintypes.BOOL
                user32.EnumWindows(cb, 0)
            except Exception:
                pass

        return results

    def type_into_window(self, text: str, title_substr: Optional[str] = None) -> Dict[str, Any]:
        if title_substr:
            wins = self.find_windows_by_title(title_substr)
            if wins:
                hwnd = wins[0]["hwnd"]
                user32.ShowWindow(hwnd, 9)
                user32.SetForegroundWindow(hwnd)
                time.sleep(0.3)
        has_enter = text.endswith("\n")
        clean_text = text.rstrip("\r\n") if has_enter else text
        controller.type_text(clean_text)
        if has_enter:
            time.sleep(0.1)
            controller.press_key("enter")
        return {"success": True, "chars_typed": len(text), "message": f"Typed text into active window."}

    def check_battery(self) -> Dict[str, Any]:
        """Checks laptop battery percentage, power connection, and charging status."""
        try:
            batt = psutil.sensors_battery()
            if not batt:
                return {"success": True, "has_battery": False, "percent": 100, "power_plugged": True, "message": "No battery detected (Desktop workstation or AC connected)."}
            status_text = "Plugged in / Charging" if batt.power_plugged else "Discharging on Battery"
            time_str = f", ~{round(batt.secsleft / 60)} mins remaining" if (batt.secsleft and batt.secsleft > 0) else ""
            return {
                "success": True,
                "has_battery": True,
                "percent": batt.percent,
                "power_plugged": batt.power_plugged,
                "seconds_left": batt.secsleft if batt.secsleft > 0 else None,
                "message": f"Battery is at {batt.percent}% ({status_text}{time_str})."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def mouse_click(self, x: int, y: int, button: str = "left", double_click: bool = False) -> Dict[str, Any]:
        """Performs direct mouse click on desktop coordinates (x, y)."""
        try:
            controller.click(x, y, button=button, double_click=double_click)
            return {"success": True, "x": x, "y": y, "button": button, "message": f"Clicked mouse {button} button at ({x}, {y})."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_command(self, command: str, timeout: float = 15.0) -> Dict[str, Any]:
        """Executes validated PowerShell command with safety restrictions."""
        cmd_lower = command.lower()
        for blocked in BLOCKED_COMMAND_PATTERNS:
            if blocked in cmd_lower:
                return {"success": False, "error": f"Command rejected: contains blocked destructive pattern '{blocked}'."}

        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return {
                "success": (res.returncode == 0),
                "returncode": res.returncode,
                "stdout": res.stdout[:4000],
                "stderr": res.stderr[:2000]
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Command execution timed out after {timeout} seconds."}
        except Exception as e:
            return {"success": False, "error": str(e)}


system_agent = SystemAgent()
