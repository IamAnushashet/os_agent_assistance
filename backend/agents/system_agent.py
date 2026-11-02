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
    "terminal": "wt.exe",
    "explorer": "explorer.exe",
    "paint": "mspaint.exe",
    "wordpad": "write.exe"
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
        """Launches an approved application by name."""
        k = app_name.lower().strip()
        exe = COMMON_APP_MAP.get(k, app_name)
        try:
            subprocess.Popen(exe, shell=True)
            time.sleep(0.8)
            return {"success": True, "app": app_name, "executable": exe, "message": f"Launched '{app_name}' successfully."}
        except Exception as e:
            return {"success": False, "error": f"Could not launch application '{app_name}': {e}"}

    def wait_for_window(self, title_substr: str, timeout: float = 10.0) -> Dict[str, Any]:
        """Waits for a desktop window containing title_substr to appear."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            for b in self.find_windows_by_title(title_substr):
                user32.ShowWindow(b["hwnd"], 9)
                user32.SetForegroundWindow(b["hwnd"])
                return {"success": True, "hwnd": b["hwnd"], "title": b["title"]}
            time.sleep(0.3)
        return {"success": False, "error": f"Window with title matching '{title_substr}' did not appear within {timeout}s."}

    def find_windows_by_title(self, query: str) -> List[Dict[str, Any]]:
        results = []
        q_lower = query.lower()

        def enum_cb(hwnd, lparam):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    t = buff.value
                    if q_lower in t.lower():
                        results.append({"hwnd": hwnd, "title": t})
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        return results

    def type_into_window(self, text: str, title_substr: Optional[str] = None) -> Dict[str, Any]:
        if title_substr:
            wins = self.find_windows_by_title(title_substr)
            if wins:
                user32.ShowWindow(wins[0]["hwnd"], 9)
                user32.SetForegroundWindow(wins[0]["hwnd"])
                time.sleep(0.2)
        controller.type_text(text)
        return {"success": True, "chars_typed": len(text), "message": f"Typed text into active window."}

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
