"""
Central Multi-Agent Orchestrator for AI-Native Windows OS Assistant.
Coordinates Browser, File, System, and Vision Agents through a verified ReAct loop.
Enforces default-deny human permissions and truthful outcome verification.
"""

import asyncio
import time
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Set

from db import (
    create_task,
    get_task,
    list_tasks,
    update_task_status,
    save_task_plan,
    save_completion_report,
    add_task_event,
    log_audit,
    recover_stale_tasks,
    get_db_connection
)
from permission_engine import permission_engine, PermissionDecision, ActionCategory, RiskLevel
from tool_registry import tool_registry
from semantic_planner import semantic_planner
from speech_service import speech_service
from llm_gateway import llm_gateway
from config import PROJECT_ROOT, settings

logger = logging.getLogger("orchestrator")
logger.setLevel(logging.INFO)


class TaskState:
    QUEUED = "QUEUED"
    PLANNING = "PLANNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MultiAgentOrchestrator:
    def __init__(self):
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.event_subscribers: Dict[str, List[asyncio.Queue]] = {}
        self.pending_approvals: Dict[str, Dict[str, Any]] = {}
        self.default_workspace = str(PROJECT_ROOT)

    def startup(self):
        """Startup hook: recovers tasks left in flight from unexpected process restart."""
        recover_stale_tasks()
        logger.info("Multi-Agent Orchestrator initialized cleanly.")

    def subscribe(self, task_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        if task_id not in self.event_subscribers:
            self.event_subscribers[task_id] = []
        self.event_subscribers[task_id].append(q)
        return q

    def unsubscribe(self, task_id: str, q: asyncio.Queue):
        if task_id in self.event_subscribers:
            if q in self.event_subscribers[task_id]:
                self.event_subscribers[task_id].remove(q)
            if not self.event_subscribers[task_id]:
                del self.event_subscribers[task_id]

    async def broadcast_event(self, task_id: str, event_type: str, data: Dict[str, Any]):
        payload = {
            "task_id": task_id,
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        add_task_event(task_id, event_type, data)
        try:
            log_audit(task_id, event_type, data)
        except Exception:
            pass

        for q in list(self.event_subscribers.get(task_id, [])):
            try:
                await q.put(payload)
            except Exception:
                pass

    def emergency_stop(self) -> Dict[str, Any]:
        """Instantly halts all active tasks and locks execution."""
        res = permission_engine.trigger_emergency_stop()
        for tid, worker in list(self.active_tasks.items()):
            if not worker.done():
                worker.cancel()
            update_task_status(tid, TaskState.CANCELLED, error_message="Emergency Stop Triggered")
        self.active_tasks.clear()
        try:
            log_audit(None, "EMERGENCY_STOP_ACTIVATED", {"status": "stopped", "reason": "User emergency stop"})
        except Exception:
            pass
        return res

    def clear_emergency_stop(self) -> Dict[str, Any]:
        res = permission_engine.clear_emergency_stop()
        try:
            log_audit(None, "EMERGENCY_STOP_CLEARED", {"status": "resumed"})
        except Exception:
            pass
        return res

    async def cancel_task(self, task_id: str) -> bool:
        update_task_status(task_id, TaskState.CANCELLED, error_message="Cancelled by user")
        permission_engine.reset_session(task_id)

        worker = self.active_tasks.get(task_id)
        if worker and not worker.done():
            worker.cancel()

        await self.broadcast_event(task_id, "TASK_CANCELLED", {"reason": "User cancellation"})
        self.active_tasks.pop(task_id, None)
        return True

    async def create_and_run_task(
        self,
        prompt: str,
        workspace: Optional[str] = None,
        permission_mode: str = "balanced",
        model: Optional[str] = None
    ) -> str:
        """Public API entrypoint: creates task and spawns the multi-agent worker."""
        if permission_engine.is_emergency_stopped():
            raise RuntimeError("Emergency stop is currently active. Clear emergency stop in Settings to proceed.")

        ws = workspace or self.default_workspace
        task_id = f"task-{uuid.uuid4().hex[:10]}"
        create_task(task_id, prompt, ws, permission_mode, model or settings.LLM_MODEL)

        await self.broadcast_event(task_id, "TASK_CREATED", {
            "prompt": prompt,
            "workspace": ws,
            "permission_mode": permission_mode
        })

        worker = asyncio.create_task(
            self._run_multi_agent_pipeline(task_id, prompt, ws, permission_mode)
        )
        self.active_tasks[task_id] = worker
        return task_id

    def _print_console_response(self, task_id: str, prompt: str, text: str):
        """Prints the AI Assistant response directly to the executable stdout/terminal console."""
        try:
            border = "=" * 70
            divider = "-" * 70
            enc = sys.stdout.encoding or "utf-8"
            safe_text = str(text).encode(enc, errors="replace").decode(enc, errors="replace")
            safe_prompt = str(prompt).encode(enc, errors="replace").decode(enc, errors="replace")
            print(f"\n{border}\n[AI ASSISTANT RESPONSE] Task: {task_id} - Prompt: '{safe_prompt}'\n{divider}\n{safe_text}\n{border}\n", flush=True)
        except Exception:
            try:
                print(f"\n[AI ASSISTANT RESPONSE - {task_id}]: {text}\n", flush=True)
            except Exception:
                pass

    async def _run_multi_agent_pipeline(
        self,
        task_id: str,
        prompt: str,
        workspace: str,
        permission_mode: str
    ):
        """Execution Lifecycle: Plan -> Permission Check -> Execute -> Verify -> Synthesize."""
        try:
            await asyncio.sleep(0.01)

            # 1. PLANNING
            update_task_status(task_id, TaskState.PLANNING)
            await self.broadcast_event(task_id, "PHASE_CHANGED", {"phase": TaskState.PLANNING})

            # Retrieve recent conversation context for multi-turn task continuity
            chat_history = []
            try:
                from db import list_tasks
                recent_tasks = list_tasks(limit=8)
                for pt in reversed(recent_tasks):
                    if pt.get("id") == task_id:
                        continue
                    u_prompt = pt.get("user_prompt")
                    if u_prompt:
                        chat_history.append({"role": "user", "content": u_prompt})
                    plan_data = pt.get("plan") or {}
                    rep_data = pt.get("completion_report") or {}
                    resp = plan_data.get("conversational_response") or rep_data.get("summary") or ""
                    if resp:
                        chat_history.append({"role": "assistant", "content": resp})
            except Exception as ex:
                logger.warning(f"Could not load chat history for task planning: {ex}")

            plan_obj = await semantic_planner.formulate_plan(prompt=prompt, chat_history=chat_history)
            plan = plan_obj.to_dict()
            save_task_plan(task_id, plan)
            await self.broadcast_event(task_id, "PLAN_GENERATED", plan)

            # Conversational shortcut
            if plan.get("is_conversational"):
                reply = plan.get("conversational_response") or "Hello! How can I assist you with Windows today?"
                report = {
                    "task_id": task_id,
                    "prompt": prompt,
                    "summary": reply,
                    "spoken_summary": speech_service.filter_text_for_speech(reply),
                    "agents_used": ["Assistant"],
                    "steps_completed": 0
                }
                save_completion_report(task_id, report)
                update_task_status(task_id, TaskState.COMPLETED)
                await self.broadcast_event(task_id, "TASK_COMPLETED", report)
                self._print_console_response(task_id, prompt, reply)
                return

            # 2. EXECUTION
            update_task_status(task_id, TaskState.EXECUTING)
            await self.broadcast_event(task_id, "PHASE_CHANGED", {"phase": TaskState.EXECUTING})

            executed_actions = []
            agents_engaged = set()
            steps = plan.get("steps", [])

            for step_idx, step in enumerate(steps[:10]):
                if permission_engine.is_emergency_stopped():
                    raise asyncio.CancelledError("Emergency Stop active.")

                agent_name = step.get("agent", "System Agent")
                tool_name = step.get("tool_name", "")
                params = step.get("params", {})
                category = ActionCategory(step.get("category", ActionCategory.SYSTEM_COMMAND.value))
                risk = step.get("risk_level", RiskLevel.LOW.value)
                agents_engaged.add(agent_name)

                # Permission Gate
                is_permitted, grant_src = permission_engine.is_action_permitted(
                    task_id=task_id,
                    workspace_root=workspace,
                    category=category,
                    permission_mode=permission_mode
                )

                if not is_permitted:
                    appr_id = f"appr-{uuid.uuid4().hex[:8]}"
                    approval_info = {
                        "id": appr_id,
                        "approval_id": appr_id,
                        "step_index": step_idx,
                        "title": step.get("title"),
                        "agent": agent_name,
                        "tool": tool_name,
                        "reason": step.get("reason"),
                        "risk_level": risk
                    }
                    self.pending_approvals[task_id] = approval_info
                    update_task_status(task_id, TaskState.AWAITING_APPROVAL)
                    await self.broadcast_event(task_id, "APPROVAL_REQUIRED", approval_info)

                    decision, meta = await permission_engine.request_approval(
                        task_id=task_id,
                        workspace_root=workspace,
                        action_type=f"{agent_name}.{tool_name}",
                        reason=step.get("reason"),
                        risk_level=risk,
                        approval_id=appr_id
                    )
                    self.pending_approvals.pop(task_id, None)
                    await self.broadcast_event(task_id, "APPROVAL_RESOLVED", {
                        "approval_id": appr_id,
                        "decision": decision.value
                    })

                    if decision in [PermissionDecision.DENY, PermissionDecision.CANCEL]:
                        update_task_status(task_id, TaskState.CANCELLED)
                        await self.broadcast_event(task_id, "TASK_CANCELLED", {
                            "reason": f"User denied {agent_name} action"
                        })
                        return

                    if decision == PermissionDecision.ALLOW_SESSION:
                        permission_engine.grant_session_permission(task_id, category.value)

                    update_task_status(task_id, TaskState.EXECUTING)

                # Multi-Agent Coordination Context Passing:
                # Dynamic parameter handoff between coordinated agent steps
                if executed_actions:
                    last_step = executed_actions[-1]
                    last_res = last_step.get("result", {})
                    last_params = last_step.get("params", {})
                    prev_path = last_res.get("path") or last_res.get("file_path") or last_params.get("path") or ""

                    # 1. File path propagation (File Agent -> System Agent / File Agent)
                    if "path" in params and params["path"] in ["$PREV_PATH", "{prev_path}", "$LAST_FILE", ""]:
                        if prev_path:
                            params["path"] = prev_path
                    elif tool_name == "file_open" and not params.get("path") and prev_path:
                        params["path"] = prev_path

                    if "file_path" in params and params["file_path"] in ["$PREV_PATH", "{prev_path}", "$LAST_FILE", ""]:
                        if prev_path:
                            params["file_path"] = prev_path

                    # 2. Command target substitution (File Agent -> System Agent)
                    if tool_name == "system_run_command" and "command" in params:
                        cmd = params["command"]
                        if ("$PREV_PATH" in cmd or "{prev_path}" in cmd) and prev_path:
                            params["command"] = cmd.replace("$PREV_PATH", prev_path).replace("{prev_path}", prev_path)

                    # 3. Vision coordinates propagation (Vision Agent -> System Agent mouse click)
                    if tool_name == "system_mouse_click":
                        if ("x" not in params or params.get("x") is None) and "x" in last_res:
                            params["x"] = last_res["x"]
                        if ("y" not in params or params.get("y") is None) and "y" in last_res:
                            params["y"] = last_res["y"]

                # Execute Registered Tool
                t0 = time.time()
                if tool_name.startswith("file_generate_") or tool_name.startswith("file_convert"):
                    params.setdefault("task_id", task_id)

                await self.broadcast_event(task_id, "ACTION_EXECUTING", {
                    "step_index": step_idx,
                    "agent": agent_name,
                    "tool": tool_name,
                    "params": params
                })

                action_res = await tool_registry.execute(tool_name, params)
                duration = round(time.time() - t0, 2)
                success = action_res.get("success", True)

                step_record = {
                    "step_index": step_idx,
                    "title": step.get("title"),
                    "agent": agent_name,
                    "tool": tool_name,
                    "params": params,
                    "success": success,
                    "result": action_res,
                    "duration_seconds": duration
                }
                executed_actions.append(step_record)

                await self.broadcast_event(task_id, "ACTION_COMPLETED", {
                    "step_index": step_idx,
                    "agent": agent_name,
                    "tool": tool_name,
                    "params": params,
                    "success": success,
                    "summary": action_res.get("message") or ("Step completed" if success else action_res.get("error")),
                    "duration_seconds": duration
                })

                # Honest Failure Halting
                if not success:
                    err_msg = action_res.get("error") or f"Step {step_idx + 1} ({step.get('title')}) failed."
                    update_task_status(task_id, TaskState.FAILED, error_message=err_msg)
                    fail_report = {
                        "task_id": task_id,
                        "prompt": prompt,
                        "status": "FAILED",
                        "error": err_msg,
                        "summary": f"Task stopped at step {step_idx + 1}: {err_msg}",
                        "spoken_summary": f"I encountered an issue with step {step_idx + 1}: {err_msg}",
                        "actions": executed_actions
                    }
                    save_completion_report(task_id, fail_report)
                    await self.broadcast_event(task_id, "TASK_FAILED", fail_report)
                    return

            # 3. COMPLETION
            summary_parts = []
            code_displays = []
            for a in executed_actions:
                tool_name = a.get("tool", "")
                params = a.get("params", {})
                res = a.get("result", {})
                msg = (
                    res.get("message")
                    or res.get("summary")
                    or res.get("analysis")
                    or res.get("explanation")
                    or res.get("diagnosis")
                )

                if tool_name == "file_write":
                    code_content = params.get("content", "").strip()
                    target_path = res.get("path") or params.get("path") or "script.py"

                    # If params didn't have content, attempt to read directly from written file on disk
                    if not code_content and target_path:
                        for p_cand in [Path(target_path), (PROJECT_ROOT / target_path).resolve()]:
                            if p_cand.exists() and p_cand.is_file():
                                try:
                                    code_content = p_cand.read_text(encoding="utf-8", errors="ignore").strip()
                                    if code_content:
                                        break
                                except Exception:
                                    pass

                    ext = Path(target_path).suffix.lstrip(".").lower() or "code"
                    filename = Path(target_path).name

                    code_exts = {"py", "cpp", "c", "h", "hpp", "java", "js", "ts", "jsx", "tsx", "html", "css", "sh", "bat", "cmd", "ps1", "json", "sql", "cs", "rb", "go", "rs", "php"}
                    is_code = ext in code_exts or any(k in code_content for k in ["#include", "def ", "class ", "import ", "function", "public static", "<!DOCTYPE"])

                    if is_code and len(code_content) > 0:
                        bytes_cnt = res.get("bytes_written") or len(code_content.encode("utf-8"))
                        code_displays.append(
                            f"Saved locally to `{filename}` ({bytes_cnt} bytes):\n\n"
                            f"```{ext}\n{code_content}\n```"
                        )
                    elif msg:
                        summary_parts.append(msg)

                elif "recent_files" in res or tool_name == "file_get_recent":
                    r_files = res.get("recent_files", [])
                    sort_by = res.get("sort_by", "date")
                    if r_files:
                        lines = [f"### 📁 Recent Files ({sort_by.title()} Sort)\n"]
                        lines.append("| File Name | Size | Last Modified |")
                        lines.append("|:---|:---|:---|")
                        for rf in r_files:
                            lines.append(f"| `{rf.get('name')}` | {rf.get('size_kb')} KB | {rf.get('modified_str')} |")
                        interactive_prompt = res.get("interactive_prompt", "Would you like me to open any of these files for you?")
                        lines.append(f"\n*{interactive_prompt}*")
                        summary_parts.append("\n".join(lines))
                    elif msg:
                        summary_parts.append(msg)

                elif "tabs" in res or tool_name == "browser_list_tabs":
                    tabs = res.get("tabs", [])
                    if tabs:
                        t_lines = [f"### 🌐 Active Browser Tabs ({len(tabs)} open)\n"]
                        for idx, tab in enumerate(tabs, 1):
                            t_title = tab.get("title") or "Untitled Tab"
                            t_url = tab.get("url") or ""
                            t_lines.append(f"{idx}. **{t_title}**\n   `{t_url}`")
                        summary_parts.append("\n".join(t_lines))
                    elif msg:
                        summary_parts.append(msg)

                elif "text" in res and tool_name in ["file_extract_text", "browser_extract_text"]:
                    extracted = res.get("text", "").strip()
                    doc_fn = Path(params.get("file_path", "")).name or "Extracted Document"
                    if extracted:
                        summary_parts.append(f"### 📄 Extracted Content ({doc_fn})\n\n{extracted}")
                    elif msg:
                        summary_parts.append(msg)

                elif tool_name == "system_check_battery" or ("percent" in res and "power_plugged" in res):
                    pct = res.get("percent")
                    plugged = res.get("power_plugged")
                    status_lbl = "Plugged in / Charging" if plugged else "Discharging on Battery"
                    secs = res.get("seconds_left")
                    time_rem = f", ~{round(secs / 60)} minutes remaining" if secs and secs > 0 else ""
                    summary_parts.append(f"🔋 **Battery Status**: {pct}% ({status_lbl}{time_rem})")

                elif "processes" in res or tool_name == "system_list_processes":
                    procs = res.get("processes", [])
                    if procs:
                        p_lines = ["### ⚙️ Top Active Processes\n", "| Process Name | PID | CPU % | RAM % |", "|:---|:---|:---|:---|"]
                        for pr in procs:
                            p_lines.append(f"| `{pr.get('name')}` | {pr.get('pid')} | {pr.get('cpu_pct')}% | {pr.get('memory_pct')}% |")
                        summary_parts.append("\n".join(p_lines))
                    elif msg:
                        summary_parts.append(msg)

                elif "cpu" in res and "memory" in res and tool_name == "system_telemetry":
                    c_pct = res.get("cpu", {}).get("percent")
                    m = res.get("memory", {})
                    telem_str = f"💻 **System Telemetry**: CPU: {c_pct}% | RAM: {m.get('used_gb')}GB / {m.get('total_gb')}GB ({m.get('percent')}%)"
                    batt = res.get("battery")
                    if batt:
                        b_status = "Charging" if batt.get("power_plugged") else "Discharging"
                        telem_str += f" | Battery: {batt.get('percent')}% ({b_status})"
                    summary_parts.append(telem_str)

                elif tool_name == "system_run_command" and res.get("stdout"):
                    out = res.get("stdout", "").strip()
                    summary_parts.append(f"**Command Output:**\n```powershell\n{out}\n```")

                elif tool_name == "system_launch_app" and res.get("output"):
                    app_n = res.get("app", "Application")
                    out = res.get("output", "").strip()
                    summary_parts.append(f"💻 Opened **{app_n}** window and executed command:\n```powershell\n{out}\n```")

                elif "entries" in res or tool_name == "file_list_dir":
                    entries = res.get("entries", [])
                    dir_path = res.get("path", "")
                    if entries:
                        dirs = [e["name"] for e in entries if e.get("is_dir")]
                        files = [e["name"] for e in entries if not e.get("is_dir")]
                        l_parts = [f"### 📂 Directory Contents: `{dir_path}`\n"]
                        if dirs:
                            l_parts.append("**Directories:**\n" + "\n".join(f"- 📁 `{d}/`" for d in sorted(dirs)))
                        if files:
                            l_parts.append("\n**Files:**\n" + "\n".join(f"- 📄 `{f}`" for f in sorted(files)))
                        summary_parts.append("\n".join(l_parts))
                    elif msg:
                        summary_parts.append(msg)

                elif "files" in res or tool_name == "file_search":
                    files = res.get("files", [])
                    q_term = res.get("query") or params.get("query", "")
                    if files:
                        lines = [f"### 🔍 File Search Results for `{q_term}` ({len(files)} match{'es' if len(files) != 1 else ''})\n"]
                        exact_matches = [
                            f for f in files
                            if f.get("name", "").lower() == q_term.lower()
                            or Path(f.get("name", "")).name.lower() == Path(q_term).name.lower()
                            or Path(f.get("path", "")).name.lower() == Path(q_term).name.lower()
                        ]
                        if exact_matches:
                            lines.append("**Exact Match Found:**")
                            for ef in exact_matches:
                                sz_kb = round(ef.get("size", 0) / 1024, 1) if ef.get("size") is not None else None
                                sz_str = f" ({sz_kb} KB)" if sz_kb is not None else ""
                                lines.append(f"- 📄 **Path:** `{ef.get('path')}`{sz_str}")
                            lines.append("")
                        other_matches = [f for f in files if f not in exact_matches]
                        if other_matches:
                            if exact_matches:
                                lines.append("**Other Matches:**")
                            for of in other_matches:
                                c_flag = " *(content match)*" if of.get("content_match") else ""
                                sz_kb = round(of.get("size", 0) / 1024, 1) if of.get("size") is not None else None
                                sz_str = f" ({sz_kb} KB)" if sz_kb is not None else ""
                                lines.append(f"- 📄 `{of.get('name')}`{c_flag}: `{of.get('path')}`{sz_str}")
                        summary_parts.append("\n".join(lines))
                    else:
                        summary_parts.append(f"🔍 No files found matching `{q_term}` in the workspace.")

                elif tool_name == "file_read" and ("content" in res or "path" in res):
                    content = res.get("content", "")
                    f_path = res.get("path") or params.get("path", "")
                    fn = Path(f_path).name or "File"
                    ext = Path(f_path).suffix.lstrip(".").lower() or "text"
                    total_chars = res.get("total_chars", len(content))
                    if res.get("error"):
                        summary_parts.append(f"❌ Error reading `{fn}`: {res.get('error')}")
                    elif len(content) <= 3000:
                        summary_parts.append(f"### 📄 File: `{fn}`\n**Location:** `{f_path}` ({total_chars} characters)\n\n```{ext}\n{content}\n```")
                    else:
                        preview = content[:3000]
                        summary_parts.append(f"### 📄 File: `{fn}`\n**Location:** `{f_path}` (Showing first 3,000 of {total_chars} characters)\n\n```{ext}\n{preview}\n...\n```")

                elif tool_name == "browser_navigate" and ("url" in res or "title" in res):
                    dest_url = res.get("url") or params.get("url", "")
                    page_title = res.get("title") or dest_url
                    summary_parts.append(f"🌐 **Browser Navigated**: [{page_title}]({dest_url})")

                elif tool_name == "browser_search" and ("query" in res or "url" in res):
                    q = res.get("query") or params.get("query", "")
                    engine = res.get("engine") or params.get("engine", "google")
                    summary_parts.append(f"🔍 **Web Search ({engine.title()})**: Searched for `{q}` in active browser session.")

                elif tool_name == "vision_locate_target" and "coordinates" in res:
                    coords = res.get("coordinates") or {}
                    t_name = res.get("target") or params.get("target", "element")
                    summary_parts.append(f"🎯 **Target Located**: `{t_name}` at screen coordinates `(X: {coords.get('x')}, Y: {coords.get('y')})`.")

                elif tool_name in ["vision_analyze_screen", "vision_explain_error", "system_diagnose"]:
                    analysis_text = res.get("analysis") or res.get("explanation") or res.get("diagnosis") or msg
                    if analysis_text:
                        summary_parts.append(analysis_text)

                elif msg:
                    summary_parts.append(msg)

            if code_displays:
                # Filter out redundant "Successfully written to <filename>" when code_displays already presents it
                clean_parts = [p for p in summary_parts if not any(cd_fn in p for cd_fn in [Path(a.get("params", {}).get("path", "")).name for a in executed_actions if a.get("params", {}).get("path")])]
                full_summary = "\n\n".join(code_displays)
                if clean_parts:
                    full_summary = " ".join(clean_parts) + "\n\n" + full_summary
                spoken = f"Successfully generated and saved {len(code_displays)} code file to your Windows workspace."
            else:
                full_summary = "\n\n".join(summary_parts) if summary_parts else f"Task '{prompt}' completed successfully."
                
                # If prompt is a question, explanation, or informational query, synthesize with LLM Gateway
                query_indicators = [
                    "explain", "describe", "what is", "what are", "how does", "how do", "how to",
                    "architecture", "overview", "structure", "tell me", "analyze", "break down",
                    "can you give", "give me", "give the", "give path", "where is", "where are",
                    "path of", "location of", "find", "search", "show me", "which", "why", "who",
                    "summarize", "detail", "check if", "is there", "list", "read", "display", "print"
                ]
                is_query = any(w in prompt.lower() for w in query_indicators) or "?" in prompt
                if is_query and summary_parts:
                    try:
                        context_data = "\n\n".join(summary_parts)
                        synth_messages = [
                            {"role": "system", "content": "You are the Autonomous Multi-Agent OS Assistant operating the user's actual Windows computer. The user asked a question or requested specific information about files, directories, processes, browser, or system state. Provide a direct, concise, professional, and clear answer using the observed evidence and context. If a file path or location was requested, state the exact path prominently first. Use clean Markdown formatting."},
                            {"role": "user", "content": f"User Request: {prompt}\n\nObserved Evidence / Workspace Data:\n{context_data}\n\nPlease provide a clear, comprehensive, and helpful direct answer to the user's request."}
                        ]
                        synth_resp = await llm_gateway.chat_complete(synth_messages)
                        if synth_resp and synth_resp.get("content"):
                            full_summary = synth_resp["content"].strip()
                    except Exception as e:
                        logger.warning(f"Synthesis call failed, falling back to raw summary: {e}")

                spoken = speech_service.filter_text_for_speech(full_summary)

            # If any action created or converted a document, attach created_document directly to final_report
            created_document = None
            for a in reversed(executed_actions):
                res = a.get("result", {})
                if isinstance(res, dict):
                    fname = res.get("filename") or ""
                    is_doc = any(fname.lower().endswith(ext) for ext in [".pdf", ".pptx", ".docx", ".xlsx", ".txt", ".csv"])
                    if res.get("doc_id") or (fname and is_doc):
                        created_document = {
                            "doc_id": res.get("doc_id", ""),
                            "filename": fname or (Path(res.get("file_path") or res.get("path") or "document").name),
                            "file_path": str(res.get("file_path") or res.get("path") or ""),
                            "file_type": res.get("file_type") or (fname.split(".")[-1].upper() if "." in fname else "DOC"),
                            "title": res.get("title", ""),
                            "size_bytes": res.get("file_size", 0)
                        }
                        break

            final_report = {
                "task_id": task_id,
                "prompt": prompt,
                "status": "COMPLETED",
                "summary": full_summary,
                "spoken_summary": spoken,
                "agents_used": list(agents_engaged),
                "actions_count": len(executed_actions),
                "actions": executed_actions,
                "created_document": created_document
            }

            if created_document and (created_document.get("doc_id") or created_document.get("file_path") or created_document.get("filename")):
                try:
                    doc_id_val = created_document.get("doc_id") or ""
                    fp_val = str(created_document.get("file_path") or "")
                    fname_val = created_document.get("filename") or (Path(fp_val).name if fp_val else "")
                    conn = get_db_connection()
                    with conn:
                        conn.execute(
                            """
                            UPDATE generated_documents 
                            SET task_id = ? 
                            WHERE (id != '' AND id = ?) 
                               OR (file_path != '' AND (file_path = ? OR file_path LIKE ? OR filename = ?))
                            """,
                            (task_id, doc_id_val, fp_val, f"%{fname_val}", fname_val)
                        )
                    conn.close()
                except Exception:
                    pass

            save_completion_report(task_id, final_report)
            update_task_status(task_id, TaskState.COMPLETED)
            await self.broadcast_event(task_id, "TASK_COMPLETED", final_report)
            self._print_console_response(task_id, prompt, full_summary)
            log_audit(task_id, "TASK_COMPLETED", {"agents": list(agents_engaged), "actions": len(executed_actions)})

        except asyncio.CancelledError:
            update_task_status(task_id, TaskState.CANCELLED)
            await self.broadcast_event(task_id, "TASK_CANCELLED", {"reason": "Operation cancelled"})
        except Exception as e:
            logger.error(f"Task pipeline error for {task_id}: {e}", exc_info=True)
            update_task_status(task_id, TaskState.FAILED, error_message=str(e))
            await self.broadcast_event(task_id, "TASK_FAILED", {"error": str(e)})
        finally:
            self.active_tasks.pop(task_id, None)


orchestrator = MultiAgentOrchestrator()
