"""
Trusted Backend Security Boundary & Permission Engine.
Enforces Default-Deny access control, risk classification, 6-choice human approvals,
and immediate system-wide Emergency Stop.
"""

import asyncio
import logging
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set

logger = logging.getLogger("permission_engine")
logger.setLevel(logging.INFO)


class ActionCategory(str, Enum):
    SAFE_READ = "SAFE_READ"
    FILE_READ = "FILE_READ"
    FILE_WRITE = "FILE_WRITE"
    FILE_DELETE = "FILE_DELETE"
    BROWSER_ACTION = "BROWSER_ACTION"
    SYSTEM_COMMAND = "SYSTEM_COMMAND"
    SYSTEM_KILL = "SYSTEM_KILL"
    HIGH_RISK_SYSTEM = "HIGH_RISK_SYSTEM"
    VISION_CAPTURE = "VISION_CAPTURE"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PermissionDecision(str, Enum):
    ALLOW_ONCE = "ALLOW_ONCE"
    ALLOW_SESSION = "ALLOW_SESSION"
    ALLOW_PROJECT = "ALLOW_PROJECT"
    ALLOW_FULL = "ALLOW_FULL"
    DENY = "DENY"
    CANCEL = "CANCEL"


class PermissionEngine:
    def __init__(self):
        self._emergency_stopped: bool = False
        self._pending_approvals: Dict[str, asyncio.Future] = {}
        self._session_grants: Dict[str, Set[str]] = {}
        self._full_access_grants: Dict[str, bool] = {}

    def is_emergency_stopped(self) -> bool:
        return self._emergency_stopped

    def trigger_emergency_stop(self) -> Dict[str, Any]:
        """Halts all active tasks immediately and cancels all pending approvals."""
        self._emergency_stopped = True
        logger.critical("🛑 EMERGENCY STOP TRIGGERED! All agent operations locked.")
        for aid, fut in list(self._pending_approvals.items()):
            if not fut.done():
                fut.set_result((PermissionDecision.CANCEL, {"reason": "Emergency Stop engaged"}))
        self._pending_approvals.clear()
        return {"status": "stopped", "message": "Emergency stop active. All operations locked."}

    def clear_emergency_stop(self) -> Dict[str, Any]:
        self._emergency_stopped = False
        logger.info("Emergency stop cleared. Normal operation resumed.")
        return {"status": "resumed", "message": "Emergency stop cleared."}

    def is_action_permitted(
        self,
        task_id: str,
        workspace_root: str,
        category: ActionCategory,
        permission_mode: str = "balanced"
    ) -> Tuple[bool, str]:
        """
        Evaluates whether an action is authorized under current policy.
        Returns: (is_permitted: bool, grant_source: str)
        """
        if self._emergency_stopped:
            return False, "EMERGENCY_STOP_ACTIVE"

        # Explicit High-Risk protections: Deletion, Process Termination, Destructive Shell
        if category in [ActionCategory.FILE_DELETE, ActionCategory.SYSTEM_KILL, ActionCategory.HIGH_RISK_SYSTEM]:
            if task_id in self._session_grants and category.value in self._session_grants[task_id]:
                return True, "SESSION_GRANT"
            return False, "HIGH_RISK_EXPLICIT_APPROVAL_REQUIRED"

        # Full Access mode (autonomous within balanced bounds)
        if self._full_access_grants.get(task_id) or permission_mode == "full_access":
            return True, "FULL_ACCESS_MODE"

        # Check strict human confirmation mode: when ask_every_step is active, prompt for every action step!
        if permission_mode in ["ask_every_step", "strict"]:
            if task_id in self._session_grants and category.value in self._session_grants[task_id]:
                return True, "SESSION_GRANT"
            return False, "STRICT_STEP_APPROVAL_REQUIRED"

        # Low-risk reads and browser navigation are permitted in balanced mode
        if category in [ActionCategory.SAFE_READ, ActionCategory.FILE_READ, ActionCategory.VISION_CAPTURE]:
            return True, "SAFE_READ_POLICY"

        if category in [ActionCategory.BROWSER_ACTION]:
            return True, "BROWSER_AUTOMATION_POLICY"

        # In balanced mode: safe non-destructive file writes (e.g. creating PPTX/PDF documents or writing files) are permitted
        if category == ActionCategory.FILE_WRITE and permission_mode == "balanced":
            return True, "SAFE_FILE_WRITE_POLICY"

        # Check session grants
        if task_id in self._session_grants and category.value in self._session_grants[task_id]:
            return True, "SESSION_GRANT"

        # Default-Deny for writes, process management, and shell execution
        return False, "APPROVAL_REQUIRED"

    async def request_approval(
        self,
        task_id: str,
        workspace_root: str,
        action_type: str,
        reason: Optional[str] = None,
        impact: Optional[str] = None,
        risk_level: str = "MEDIUM",
        approval_id: Optional[str] = None
    ) -> Tuple[PermissionDecision, Dict[str, Any]]:
        """Suspends worker execution until human grants permission via UI or phone."""
        if self._emergency_stopped:
            return PermissionDecision.CANCEL, {"reason": "Emergency stop is active"}

        aid = approval_id or f"appr-{secrets.token_hex(6)}"
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._pending_approvals[aid] = fut

        logger.info(f"Awaiting human approval for {action_type} (ID: {aid}, Risk: {risk_level})")

        try:
            # 5-minute timeout on human approvals
            decision, meta = await asyncio.wait_for(fut, timeout=300.0)
            return decision, meta
        except asyncio.TimeoutError:
            logger.warning(f"Approval request {aid} timed out. Defaulting to DENY.")
            return PermissionDecision.DENY, {"reason": "Approval request timed out after 300s"}
        finally:
            self._pending_approvals.pop(aid, None)

    def resolve_approval(self, approval_id: str, decision_str: str, meta: Optional[Dict[str, Any]] = None) -> bool:
        """Called when user clicks an approval button on Desktop or Phone."""
        fut = self._pending_approvals.get(approval_id)
        if not fut or fut.done():
            return False

        try:
            dec = PermissionDecision(decision_str.upper())
        except Exception:
            dec = PermissionDecision.DENY

        meta = meta or {}
        fut.set_result((dec, meta))
        return True

    def grant_session_permission(self, task_id: str, category: str):
        if task_id not in self._session_grants:
            self._session_grants[task_id] = set()
        self._session_grants[task_id].add(category)

    def reset_session(self, task_id: str):
        self._session_grants.pop(task_id, None)
        self._full_access_grants.pop(task_id, None)


permission_engine = PermissionEngine()
