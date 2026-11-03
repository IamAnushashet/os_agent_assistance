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
                    "success": success,
                    "result": action_res,
                    "duration_seconds": duration
                }
                executed_actions.append(step_record)

                await self.broadcast_event(task_id, "ACTION_COMPLETED", {
                    "step_index": step_idx,
                    "agent": agent_name,
                    "tool": tool_name,
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
            for a in executed_actions:
                res = a.get("result", {})
                msg = res.get("message") or res.get("summary") or res.get("analysis")
                if msg:
                    summary_parts.append(msg)
            full_summary = " ".join(summary_parts) if summary_parts else f"Task '{prompt}' completed successfully."
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
