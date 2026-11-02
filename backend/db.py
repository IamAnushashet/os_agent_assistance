"""
SQLite Database Layer for AI-Native Windows OS Assistant.
Enforces Write-Ahead Logging (WAL) mode for concurrency, crash recovery, and durable audit logs.
"""

import sqlite3
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("db")
logger.setLevel(logging.INFO)

DB_PATH = Path(__file__).resolve().parent / "data" / "assistant.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db():
    """Initializes tables for tasks, events, approvals, persistent rules, and audit logs."""
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                user_prompt TEXT NOT NULL,
                workspace TEXT NOT NULL,
                permission_mode TEXT NOT NULL DEFAULT 'balanced',
                model TEXT NOT NULL DEFAULT 'gemini-2.0-flash',
                status TEXT NOT NULL DEFAULT 'QUEUED',
                plan_json TEXT,
                completion_report_json TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS task_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                action_type TEXT NOT NULL,
                reason TEXT,
                impact TEXT,
                risk_level TEXT NOT NULL DEFAULT 'MEDIUM',
                status TEXT NOT NULL DEFAULT 'PENDING',
                decision TEXT,
                decision_meta_json TEXT,
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                decided_at TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS permission_rules (
                id TEXT PRIMARY KEY,
                project_path TEXT NOT NULL,
                action_category TEXT NOT NULL,
                pattern TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'PROJECT',
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                event_name TEXT NOT NULL,
                details_json TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS generated_documents (
                id TEXT PRIMARY KEY,
                task_id TEXT,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL UNIQUE,
                file_type TEXT NOT NULL,
                topic TEXT,
                size_bytes INTEGER NOT NULL,
                status TEXT DEFAULT 'ACTIVE',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
            );
            """)
        logger.info(f"Database initialized cleanly at: {DB_PATH}")
    finally:
        conn.close()


def create_task(task_id: str, prompt: str, workspace: str, permission_mode: str, model: str):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
            INSERT INTO tasks (id, user_prompt, workspace, permission_mode, model, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'QUEUED', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (task_id, prompt, workspace, permission_mode, model))
    finally:
        conn.close()


def update_task_status(task_id: str, status: str, error_message: Optional[str] = None):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
            UPDATE tasks 
            SET status = ?, error_message = COALESCE(?, error_message), updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (status, error_message, task_id))
    finally:
        conn.close()


def save_task_plan(task_id: str, plan_data: Dict[str, Any]):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
            UPDATE tasks 
            SET plan_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (json.dumps(plan_data), task_id))
    finally:
        conn.close()


def save_completion_report(task_id: str, report_data: Dict[str, Any]):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
            UPDATE tasks 
            SET completion_report_json = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (json.dumps(report_data), task_id))
    finally:
        conn.close()


def add_task_event(task_id: str, event_type: str, data: Dict[str, Any]):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
            INSERT INTO task_events (task_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (task_id, event_type, json.dumps(data)))
    finally:
        conn.close()


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("plan_json"):
            d["plan"] = json.loads(d["plan_json"])
        if d.get("completion_report_json"):
            d["completion_report"] = json.loads(d["completion_report_json"])
        return d
    finally:
        conn.close()


def list_tasks(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))
        tasks = []
        for row in cur.fetchall():
            d = dict(row)
            if d.get("plan_json"):
                try:
                    d["plan"] = json.loads(d["plan_json"])
                except Exception:
                    pass
            tasks.append(d)
        return tasks
    finally:
        conn.close()


def log_audit(task_id: Optional[str], event_name: str, details: Dict[str, Any]):
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
            INSERT INTO audit_logs (task_id, event_name, details_json, timestamp)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (task_id, event_name, json.dumps(details)))
    finally:
        conn.close()


def get_task_events(task_id: str) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM task_events WHERE task_id = ? ORDER BY id ASC", (task_id,))
        events = []
        for r in cur.fetchall():
            item = dict(r)
            if item.get("payload_json"):
                try:
                    item["payload"] = json.loads(item["payload_json"])
                except Exception:
                    pass
            events.append(item)
        return events
    finally:
        conn.close()


def get_recent_audit_logs(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
        logs = []
        for r in cur.fetchall():
            item = dict(r)
            if item.get("details_json"):
                try:
                    item["details"] = json.loads(item["details_json"])
                except Exception:
                    pass
            logs.append(item)
        return logs
    finally:
        conn.close()


def recover_stale_tasks():
    """Startup crash recovery: resets interrupted tasks from prior crashed process."""
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("""
            UPDATE tasks
            SET status = 'CANCELLED', error_message = 'Backend process restarted during execution'
            WHERE status IN ('PLANNING', 'EXECUTING', 'AWAITING_APPROVAL')
            """)
            if cur.rowcount > 0:
                logger.info(f"Crash Recovery: Recovered {cur.rowcount} stale task(s) to CANCELLED state.")
    finally:
        conn.close()


# =============================================================================
# CHAT / TASK CRUD LIFECYCLE
# =============================================================================

def delete_task(task_id: str) -> bool:
    """
    Deletes an individual task and cascades deletion to task_events and approvals.
    Returns True if a task was deleted, False if not found.
    """
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            # With PRAGMA foreign_keys=ON, task_events and approvals are cascade deleted
            cur.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            deleted = cur.rowcount > 0
            if deleted:
                logger.info(f"Deleted task {task_id} and all cascaded events/approvals.")
            return deleted
    finally:
        conn.close()


def clear_all_tasks() -> int:
    """
    Clears all tasks, task_events, and approvals from the database.
    Returns the total number of tasks deleted.
    """
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM tasks")
            count = cur.rowcount
            logger.info(f"Cleared all {count} task(s) from history.")
            return count
    finally:
        conn.close()


def update_task_title(task_id: str, new_title: str) -> bool:
    """
    Renames a task's user prompt / title.
    """
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("""
            UPDATE tasks
            SET user_prompt = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """, (new_title.strip(), task_id))
            return cur.rowcount > 0
    finally:
        conn.close()


# =============================================================================
# GENERATED DOCUMENTS METADATA & PERSISTENCE CRUD
# =============================================================================

def save_generated_document(
    doc_id: str,
    filename: str,
    file_path: str,
    file_type: str,
    topic: str,
    size_bytes: int,
    task_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Persists metadata of a generated deliverable (.pptx, .pdf, etc.) into SQLite.
    """
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
            INSERT INTO generated_documents (id, task_id, filename, file_path, file_type, topic, size_bytes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(file_path) DO UPDATE SET
                filename=excluded.filename,
                size_bytes=excluded.size_bytes,
                topic=excluded.topic,
                created_at=CURRENT_TIMESTAMP
            """, (doc_id, task_id, filename, str(file_path), file_type.upper(), topic, size_bytes))
        logger.info(f"Document registered in DB: {filename} ({file_type}, {size_bytes} bytes)")
        return {
            "id": doc_id,
            "filename": filename,
            "file_path": str(file_path),
            "file_type": file_type.upper(),
            "topic": topic,
            "size_bytes": size_bytes
        }
    finally:
        conn.close()


def list_generated_documents(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Lists all generated documents ordered by latest creation time.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
        SELECT id, task_id, filename, file_path, file_type, topic, size_bytes, status, created_at
        FROM generated_documents
        WHERE status = 'ACTIVE'
        ORDER BY created_at DESC
        LIMIT ?
        """, (limit,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def get_generated_document(doc_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieves a single generated document record by ID.
    """
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM generated_documents WHERE id = ?", (doc_id,))
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def delete_generated_document(doc_id: str) -> Optional[str]:
    """
    Deletes a generated document record by ID.
    Returns the file_path if found, so the caller can delete the file from disk.
    """
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT file_path FROM generated_documents WHERE id = ?", (doc_id,))
            row = cur.fetchone()
            if not row:
                return None
            file_path = row["file_path"]
            cur.execute("DELETE FROM generated_documents WHERE id = ?", (doc_id,))
            logger.info(f"Deleted document record {doc_id} pointing to {file_path}")
            return file_path
    finally:
        conn.close()


def clear_all_generated_documents() -> List[str]:
    """
    Clears all generated document records from the database.
    Returns all file paths that were registered, for cleanup on disk.
    """
    conn = get_db_connection()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute("SELECT file_path FROM generated_documents")
            paths = [row["file_path"] for row in cur.fetchall()]
            cur.execute("DELETE FROM generated_documents")
            logger.info(f"Cleared all {len(paths)} document record(s) from database.")
            return paths
    finally:
        conn.close()


