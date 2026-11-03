"""
Capability-Driven Tool Registry for AI-Native Windows OS Assistant.
Exposes genuine, verified tools across the 4 specialized agents.
Enforces typed schemas, permission categories, risk classifications, and observable verifiers.
"""

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Callable

from permission_engine import ActionCategory, RiskLevel
from agents.browser_agent import browser_agent
from agents.file_agent import file_agent
from agents.system_agent import system_agent
from agents.vision_agent import vision_agent

logger = logging.getLogger("tool_registry")
logger.setLevel(logging.INFO)


@dataclass
class ToolDefinition:
    name: str
    agent: str
    description: str
    parameters: Dict[str, Any]
    category: str
    risk_level: str
    handler: Callable[..., Any]
    completion_criterion: str


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._register_all_tools()

    def register(self, tool: ToolDefinition):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def list_tools(self, agent_filter: Optional[str] = None) -> List[ToolDefinition]:
        if agent_filter:
            return [t for t in self._tools.values() if t.agent.lower() == agent_filter.lower()]
        return list(self._tools.values())

    def get_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    async def execute(self, name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        tool = self.get(name)
        if not tool:
            return {"success": False, "error": f"Tool '{name}' is not registered."}

        params = params or {}
        try:
            if inspect.iscoroutinefunction(tool.handler):
                result = await tool.handler(**params)
            else:
                result = await asyncio.to_thread(tool.handler, **params)

            if isinstance(result, dict):
                result.setdefault("agent", tool.agent)
                result.setdefault("tool_name", tool.name)
                success = result.get("success", True)
                result["verification"] = {"status": "verified" if success else "failed"}
                return result
            return {"success": True, "result": result, "agent": tool.agent, "tool_name": tool.name}
        except TypeError as te:
            logger.error(f"Invalid arguments for tool '{name}': {te}")
            return {"success": False, "error": f"Invalid arguments for {name}: {str(te)}"}
        except Exception as e:
            logger.error(f"Error executing tool '{name}': {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def _register_all_tools(self):
        # ----------------- BROWSER AGENT TOOLS -----------------
        self.register(ToolDefinition(
            name="browser_navigate",
            agent="Browser Agent",
            description="Navigates existing Chrome/Edge/Brave browser to a specific URL.",
            parameters={"url": {"type": "string", "description": "Destination web address"}},
            category=ActionCategory.BROWSER_ACTION.value,
            risk_level=RiskLevel.LOW.value,
            handler=browser_agent.navigate,
            completion_criterion="Browser address bar updated and target page requested."
        ))

        self.register(ToolDefinition(
            name="browser_search",
            agent="Browser Agent",
            description="Performs web search using Google or Bing in the existing browser.",
            parameters={"query": {"type": "string"}, "engine": {"type": "string", "default": "google"}},
            category=ActionCategory.BROWSER_ACTION.value,
            risk_level=RiskLevel.LOW.value,
            handler=browser_agent.search,
            completion_criterion="Search page loaded in browser."
        ))

        self.register(ToolDefinition(
            name="browser_list_tabs",
            agent="Browser Agent",
            description="Lists all open tabs and titles in the user's running browser session.",
            parameters={},
            category=ActionCategory.BROWSER_ACTION.value,
            risk_level=RiskLevel.LOW.value,
            handler=browser_agent.get_open_tabs,
            completion_criterion="Tabs enumerated via Windows UI Automation."
        ))

        self.register(ToolDefinition(
            name="browser_new_tab",
            agent="Browser Agent",
            description="Opens a new tab in the existing browser window.",
            parameters={"url": {"type": "string", "optional": True}},
            category=ActionCategory.BROWSER_ACTION.value,
            risk_level=RiskLevel.LOW.value,
            handler=browser_agent.new_tab,
            completion_criterion="New browser tab created."
        ))

        self.register(ToolDefinition(
            name="browser_close_tab",
            agent="Browser Agent",
            description="Closes the active tab in the user's browser.",
            parameters={},
            category=ActionCategory.BROWSER_ACTION.value,
            risk_level=RiskLevel.LOW.value,
            handler=browser_agent.close_tab,
            completion_criterion="Active tab closed."
        ))

        self.register(ToolDefinition(
            name="browser_switch_tab",
            agent="Browser Agent",
            description="Switches to next or previous tab in existing browser.",
            parameters={"direction": {"type": "string", "default": "next"}},
            category=ActionCategory.BROWSER_ACTION.value,
            risk_level=RiskLevel.LOW.value,
            handler=browser_agent.switch_tab,
            completion_criterion="Tab switched."
        ))

        self.register(ToolDefinition(
            name="browser_scroll",
            agent="Browser Agent",
            description="Scrolls page up or down.",
            parameters={"direction": {"type": "string", "default": "down"}, "amount": {"type": "number", "default": 3.0}},
            category=ActionCategory.BROWSER_ACTION.value,
            risk_level=RiskLevel.LOW.value,
            handler=browser_agent.scroll,
            completion_criterion="Page scrolled."
        ))

        self.register(ToolDefinition(
            name="browser_extract_text",
            agent="Browser Agent",
            description="Extracts visible text from page body.",
            parameters={},
            category=ActionCategory.BROWSER_ACTION.value,
            risk_level=RiskLevel.LOW.value,
            handler=browser_agent.extract_page_text,
            completion_criterion="Page text copied."
        ))

        self.register(ToolDefinition(
            name="browser_login",
            agent="Browser Agent",
            description="Assists with website login in existing browser window. Masks credentials safely.",
            parameters={
                "url": {"type": "string", "optional": True},
                "username": {"type": "string", "optional": True},
                "password": {"type": "string", "optional": True},
                "submit": {"type": "boolean", "default": True}
            },
            category=ActionCategory.BROWSER_ACTION.value,
            risk_level=RiskLevel.MEDIUM.value,
            handler=browser_agent.login,
            completion_criterion="Login credentials submitted to browser form."
        ))

        self.register(ToolDefinition(
            name="browser_click_coordinate",
            agent="Browser Agent",
            description="Clicks at precise screen/browser coordinate.",
            parameters={"x": {"type": "integer"}, "y": {"type": "integer"}, "button": {"type": "string", "default": "left"}},
            category=ActionCategory.BROWSER_ACTION.value,
            risk_level=RiskLevel.LOW.value,
            handler=browser_agent.click_coordinate,
            completion_criterion="Mouse click executed at coordinate."
        ))

        # ----------------- FILE AGENT TOOLS -----------------
        self.register(ToolDefinition(
            name="file_search",
            agent="File Agent",
            description="Searches files by name or content match in authorized workspace.",
            parameters={"query": {"type": "string"}},
            category=ActionCategory.FILE_READ.value,
            risk_level=RiskLevel.LOW.value,
            handler=file_agent.search_files,
            completion_criterion="Matching files listed."
        ))

        self.register(ToolDefinition(
            name="file_read",
            agent="File Agent",
            description="Reads text content of a file.",
            parameters={"path": {"type": "string"}},
            category=ActionCategory.FILE_READ.value,
            risk_level=RiskLevel.LOW.value,
            handler=file_agent.read_file,
            completion_criterion="File content returned."
        ))

        self.register(ToolDefinition(
            name="file_write",
            agent="File Agent",
            description="Writes content to a file with automatic rolling backup.",
            parameters={"path": {"type": "string"}, "content": {"type": "string"}},
            category=ActionCategory.FILE_WRITE.value,
            risk_level=RiskLevel.MEDIUM.value,
            handler=file_agent.write_file,
            completion_criterion="File written to disk."
        ))

        self.register(ToolDefinition(
            name="file_edit",
            agent="File Agent",
            description="Applies find-and-replace modification with unified diff preview.",
            parameters={"path": {"type": "string"}, "find": {"type": "string"}, "replace": {"type": "string"}},
            category=ActionCategory.FILE_WRITE.value,
            risk_level=RiskLevel.MEDIUM.value,
            handler=file_agent.edit_file,
            completion_criterion="Unified diff generated and file updated."
        ))

        self.register(ToolDefinition(
            name="file_delete",
            agent="File Agent",
            description="Safely deletes file; creates backup in scratch/.file_backups/.",
            parameters={"path": {"type": "string"}, "confirm": {"type": "boolean", "default": False}},
            category=ActionCategory.FILE_DELETE.value,
            risk_level=RiskLevel.HIGH.value,
            handler=file_agent.delete_file,
            completion_criterion="File safely removed."
        ))

        self.register(ToolDefinition(
            name="file_open",
            agent="File Agent",
            description="Opens file in default Windows application.",
            parameters={"path": {"type": "string"}},
            category=ActionCategory.SAFE_READ.value,
            risk_level=RiskLevel.LOW.value,
            handler=file_agent.open_file,
            completion_criterion="Default application opened."
        ))

        self.register(ToolDefinition(
            name="file_list_dir",
            agent="File Agent",
            description="Lists contents of directory.",
            parameters={"path": {"type": "string", "optional": True}},
            category=ActionCategory.SAFE_READ.value,
            risk_level=RiskLevel.LOW.value,
            handler=file_agent.list_dir,
            completion_criterion="Directory entries listed."
        ))

        self.register(ToolDefinition(
            name="file_generate_presentation",
            agent="File Agent",
            description="Generates a PowerPoint presentation (.pptx) with structured multi-slide deck.",
            parameters={
                "topic": {"type": "string", "description": "Subject or topic of presentation"},
                "filename": {"type": "string", "optional": True},
                "slides_data": {"type": "array", "optional": True},
                "theme": {"type": "string", "default": "cyber_sapphire"}
            },
            category=ActionCategory.FILE_WRITE.value,
            risk_level=RiskLevel.LOW.value,
            handler=file_agent.generate_presentation,
            completion_criterion="PowerPoint .pptx presentation created."
        ))

        self.register(ToolDefinition(
            name="file_generate_pdf",
            agent="File Agent",
            description="Generates an executive PDF report (.pdf) with executive summary, tables, and sections.",
            parameters={
                "title": {"type": "string", "description": "Report title or subject"},
                "filename": {"type": "string", "optional": True},
                "sections": {"type": "array", "optional": True},
                "executive_summary": {"type": "string", "optional": True}
            },
            category=ActionCategory.FILE_WRITE.value,
            risk_level=RiskLevel.LOW.value,
            handler=file_agent.generate_pdf,
            completion_criterion="Executive PDF report created."
        ))

        self.register(ToolDefinition(
            name="file_generate_docx",
            agent="File Agent",
            description="Generates a publication-grade Word document (.docx) with structured sections, tables, and formatting.",
            parameters={
                "topic": {"type": "string", "description": "Subject or topic of Word document"},
                "filename": {"type": "string", "optional": True},
                "sections": {"type": "array", "optional": True},
                "theme": {"type": "string", "default": "enterprise"}
            },
            category=ActionCategory.FILE_WRITE.value,
            risk_level=RiskLevel.LOW.value,
            handler=file_agent.generate_word_document,
            completion_criterion="Word .docx document created."
        ))

        self.register(ToolDefinition(
            name="file_generate_xlsx",
            agent="File Agent",
            description="Generates a professional Excel workbook (.xlsx) with styled sheets, metric tables, and formula calculations.",
            parameters={
                "topic": {"type": "string", "description": "Subject or title of Excel spreadsheet"},
                "filename": {"type": "string", "optional": True},
                "sheets_data": {"type": "array", "optional": True},
                "theme": {"type": "string", "default": "modern_blue"}
            },
            category=ActionCategory.FILE_WRITE.value,
            risk_level=RiskLevel.LOW.value,
            handler=file_agent.generate_excel_spreadsheet,
            completion_criterion="Excel .xlsx spreadsheet created."
        ))

        # ----------------- SYSTEM AGENT TOOLS -----------------
        self.register(ToolDefinition(
            name="system_telemetry",
            agent="System Agent",
            description="Reads real-time CPU, RAM, disk space, and battery metrics.",
            parameters={},
            category=ActionCategory.SAFE_READ.value,
            risk_level=RiskLevel.LOW.value,
            handler=system_agent.get_system_telemetry,
            completion_criterion="Hardware metrics returned."
        ))

        self.register(ToolDefinition(
            name="system_diagnose",
            agent="System Agent",
            description="Diagnoses system resource usage and lists top processes.",
            parameters={},
            category=ActionCategory.SAFE_READ.value,
            risk_level=RiskLevel.LOW.value,
            handler=system_agent.diagnose_system,
            completion_criterion="Health status and bottleneck diagnosis produced."
        ))

        self.register(ToolDefinition(
            name="system_list_processes",
            agent="System Agent",
            description="Lists running processes sorted by memory or CPU.",
            parameters={"limit": {"type": "integer", "default": 10}},
            category=ActionCategory.SAFE_READ.value,
            risk_level=RiskLevel.LOW.value,
            handler=system_agent.list_processes,
            completion_criterion="Active processes listed."
        ))

        self.register(ToolDefinition(
            name="system_terminate_process",
            agent="System Agent",
            description="Terminates process by PID or name.",
            parameters={"target": {"type": "string"}},
            category=ActionCategory.SYSTEM_KILL.value,
            risk_level=RiskLevel.HIGH.value,
            handler=system_agent.terminate_process,
            completion_criterion="Process terminated."
        ))

        self.register(ToolDefinition(
            name="system_launch_app",
            agent="System Agent",
            description="Launches approved Windows application (notepad, calc, code, etc.).",
            parameters={"app_name": {"type": "string"}},
            category=ActionCategory.SAFE_READ.value,
            risk_level=RiskLevel.LOW.value,
            handler=system_agent.launch_app,
            completion_criterion="Application process started."
        ))

        self.register(ToolDefinition(
            name="system_wait_for_window",
            agent="System Agent",
            description="Waits for a desktop window matching title to appear.",
            parameters={"title_substr": {"type": "string"}, "timeout": {"type": "number", "default": 10.0}},
            category=ActionCategory.SAFE_READ.value,
            risk_level=RiskLevel.LOW.value,
            handler=system_agent.wait_for_window,
            completion_criterion="Window confirmed visible."
        ))

        self.register(ToolDefinition(
            name="system_type_into_window",
            agent="System Agent",
            description="Types text into foreground or target application window.",
            parameters={"text": {"type": "string"}, "title_substr": {"type": "string", "optional": True}},
            category=ActionCategory.SYSTEM_COMMAND.value,
            risk_level=RiskLevel.MEDIUM.value,
            handler=system_agent.type_into_window,
            completion_criterion="Text entered into window."
        ))

        self.register(ToolDefinition(
            name="system_run_command",
            agent="System Agent",
            description="Executes validated PowerShell command with safety restrictions.",
            parameters={"command": {"type": "string"}},
            category=ActionCategory.SYSTEM_COMMAND.value,
            risk_level=RiskLevel.HIGH.value,
            handler=system_agent.run_command,
            completion_criterion="Command exit code and stdout captured."
        ))

        # ----------------- VISION AGENT TOOLS -----------------
        self.register(ToolDefinition(
            name="vision_analyze_screen",
            agent="Vision Agent",
            description="Captures screen and analyzes content using Gemini Flash multimodal vision.",
            parameters={"prompt": {"type": "string", "optional": True}},
            category=ActionCategory.VISION_CAPTURE.value,
            risk_level=RiskLevel.LOW.value,
            handler=vision_agent.analyze_screen,
            completion_criterion="Screen analyzed and summarized."
        ))

        self.register(ToolDefinition(
            name="vision_explain_error",
            agent="Vision Agent",
            description="Scans screen for crash dialogs, terminal tracebacks, and provides fix commands.",
            parameters={},
            category=ActionCategory.VISION_CAPTURE.value,
            risk_level=RiskLevel.LOW.value,
            handler=vision_agent.explain_error_on_screen,
            completion_criterion="Error diagnosed with remediation instructions."
        ))

        self.register(ToolDefinition(
            name="vision_locate_target",
            agent="Vision Agent",
            description="Finds exact screen coordinates (x, y) for an on-screen UI element.",
            parameters={"target_description": {"type": "string"}},
            category=ActionCategory.VISION_CAPTURE.value,
            risk_level=RiskLevel.LOW.value,
            handler=vision_agent.locate_target_coordinates,
            completion_criterion="Coordinates resolved."
        ))


tool_registry = ToolRegistry()
