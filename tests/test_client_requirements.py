"""
Comprehensive verification test suite for client requirements:
1. Modifying existing files (safe find/replace, diff previews, rollback backups).
2. Deleting with permission (risk classification, human approval gate, safe viewer lock release).
3. Creating PPT, Word, Excel, and PDF with actual publication-grade content.
4. Browser URL login assistance (credentials typing, password masking, MFA handoff).
5. Storing and retrieving all audit logs in SQLite WAL.
"""

import os
import sys
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from main import app
from config import PROJECT_ROOT, SCRATCH_DIR, BACKUPS_DIR
from db import init_db, log_audit, get_recent_audit_logs, clear_audit_logs
from agents.file_agent import file_agent
from tool_registry import tool_registry
from permission_engine import permission_engine, ActionCategory, RiskLevel

client = TestClient(app)


def test_file_modification_with_diff_and_backup():
    """Requirement 1: Modifying existing files with diff preview and backup."""
    init_db()
    test_file = SCRATCH_DIR / "test_client_modify.txt"
    test_file.write_text("Line 1: Initial content\nLine 2: Target to replace\nLine 3: End notes", encoding="utf-8")

    # 1. Edit file via direct API endpoint
    res = client.post("/api/files/edit", json={
        "path": str(test_file),
        "find": "Target to replace",
        "replace": "Modified by AI Agent successfully"
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "diff" in data
    assert "+Line 2: Modified by AI Agent successfully" in data["diff"]
    assert data["backup_path"] is not None
    assert Path(data["backup_path"]).exists()

    # 2. Verify on disk
    new_content = test_file.read_text(encoding="utf-8")
    assert "Modified by AI Agent successfully" in new_content
    assert "Target to replace" not in new_content

    # Cleanup test file
    if test_file.exists():
        test_file.unlink()


def test_file_deletion_permission_and_safety():
    """Requirement 2: Deleting with permission and safety backup."""
    del_file = SCRATCH_DIR / "test_client_delete.txt"
    del_file.write_text("Important client file to be deleted safely", encoding="utf-8")

    # 1. Verify confirm=False is rejected
    res_no_confirm = file_agent.delete_file(str(del_file), confirm=False)
    assert res_no_confirm["success"] is False
    assert del_file.exists()

    # 2. Verify permission engine classifies file_delete as HIGH risk
    tool = tool_registry.get("file_delete")
    assert tool is not None
    assert tool.category == ActionCategory.FILE_DELETE.value
    assert tool.risk_level == RiskLevel.HIGH.value

    # Under balanced governance, high-risk deletion requires explicit approval
    is_permitted, grant_src = permission_engine.is_action_permitted(
        task_id="test-task-del",
        workspace_root=str(PROJECT_ROOT),
        category=ActionCategory.FILE_DELETE,
        permission_mode="balanced"
    )
    assert is_permitted is False
    assert grant_src == "HIGH_RISK_EXPLICIT_APPROVAL_REQUIRED"

    # 3. Executed with confirmation: creates rollback backup in scratch/.file_backups/
    res_api = client.request("DELETE", "/api/files", json={"path": str(del_file), "confirm": True})
    assert res_api.status_code == 200
    api_data = res_api.json()
    assert api_data["success"] is True
    assert not del_file.exists()
    assert api_data["backup_path"] is not None
    assert Path(api_data["backup_path"]).exists()


def test_creation_of_all_four_document_formats():
    """Requirement 3: Genuine PPTX, DOCX, XLSX, and PDF generation with domain content."""
    # 1. PowerPoint (.pptx)
    res_pptx = client.post("/api/documents/generate", json={
        "doc_type": "pptx",
        "topic": "Autonomous AI Multi Agent Architecture"
    })
    assert res_pptx.status_code == 200
    pptx_data = res_pptx.json()
    assert pptx_data["success"] is True
    assert Path(pptx_data["file_path"]).exists()
    assert pptx_data["file_path"].endswith(".pptx")
    assert pptx_data["slides_count"] >= 3

    # 2. Word Document (.docx)
    res_docx = client.post("/api/documents/generate", json={
        "doc_type": "docx",
        "topic": "Enterprise Security and Compliance Dossier"
    })
    assert res_docx.status_code == 200
    docx_data = res_docx.json()
    assert docx_data["success"] is True
    assert Path(docx_data["file_path"]).exists()
    assert docx_data["file_path"].endswith(".docx")
    assert docx_data["sections_count"] >= 3

    # 3. Excel Spreadsheet (.xlsx)
    res_xlsx = client.post("/api/documents/generate", json={
        "doc_type": "xlsx",
        "topic": "Q4 Financial Model and KPI Tracking"
    })
    assert res_xlsx.status_code == 200
    xlsx_data = res_xlsx.json()
    assert xlsx_data["success"] is True
    assert Path(xlsx_data["file_path"]).exists()
    assert xlsx_data["file_path"].endswith(".xlsx")
    assert xlsx_data["sheets_count"] >= 3

    # 4. Executive PDF Report (.pdf)
    res_pdf = client.post("/api/documents/generate", json={
        "doc_type": "pdf",
        "topic": "Autonomous Agent Systems Comprehensive Whitepaper"
    })
    assert res_pdf.status_code == 200
    pdf_data = res_pdf.json()
    assert pdf_data["success"] is True
    assert Path(pdf_data["file_path"]).exists()
    assert pdf_data["file_path"].endswith(".pdf")

    # 5. Verify all 4 documents are returned in the Document Studio shelf
    res_list = client.get("/api/documents")
    assert res_list.status_code == 200
    docs = res_list.json()["documents"]
    doc_paths = [d["file_path"] for d in docs]
    assert pptx_data["file_path"] in doc_paths
    assert docx_data["file_path"] in doc_paths
    assert xlsx_data["file_path"] in doc_paths
    assert pdf_data["file_path"] in doc_paths


def test_browser_login_endpoint():
    """Requirement 4: Browser Agent login assistance with password masking and MFA detection."""
    res = client.post("/api/browser/login", json={
        "url": None,  # don't trigger actual external HTTP request in test
        "username": "client_tester@enterprise.org",
        "password": "SuperSecretPassword123!",
        "submit": False
    })
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["action"] == "browser_login"
    assert data["username"] == "client_tester@enterprise.org"
    # STRICT SECURITY REQUIREMENT: password must never appear in response
    assert data["password_masked"] == "********"
    assert "SuperSecretPassword123!" not in str(data)
    assert "MFA" in data["message"] or "verification" in data["message"]


def test_audit_logs_storage_and_retrieval():
    """Requirement 5: Storing and querying all audit logs in SQLite WAL."""
    clear_audit_logs()

    # Log several events
    log_audit("task-log-1", "TASK_CREATED", {"prompt": "Create test report", "mode": "balanced"})
    log_audit("task-log-1", "APPROVAL_REQUIRED", {"tool": "file_delete", "risk": "HIGH"})
    log_audit("task-log-1", "APPROVAL_RESOLVED", {"decision": "ALLOW_ONCE"})
    log_audit("task-log-1", "TASK_COMPLETED", {"status": "SUCCESS", "actions": 2})

    # Retrieve via API
    res = client.get("/api/logs/audit?limit=50")
    assert res.status_code == 200
    logs = res.json()["audit_logs"]
    assert len(logs) == 4
    event_names = [l["event_name"] for l in logs]
    assert "TASK_CREATED" in event_names
    assert "APPROVAL_REQUIRED" in event_names
    assert "APPROVAL_RESOLVED" in event_names
    assert "TASK_COMPLETED" in event_names

    # Test clear endpoint
    res_clear = client.delete("/api/logs/audit")
    assert res_clear.status_code == 200
    assert res_clear.json()["count"] == 4

    res_empty = client.get("/api/logs/audit")
    assert len(res_empty.json()["audit_logs"]) == 0


def test_browser_activity_in_new_tab():
    """Verify that focus/open browser and browser navigation always occur in a fresh new tab."""
    from semantic_planner import semantic_planner

    # 1. Direct API endpoint /api/browser/open
    res = client.post("/api/browser/open")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["action"] == "new_tab"

    # 2. Semantic planner routes 'open browser' / 'focus browser' to browser_new_tab
    plan_open = semantic_planner._rule_based_fallback("open my existing browser")
    assert len(plan_open.steps) >= 1
    assert plan_open.steps[0].tool_name == "browser_new_tab"

    plan_focus = semantic_planner._rule_based_fallback("focus browser")
    assert len(plan_focus.steps) >= 1
    assert plan_focus.steps[0].tool_name == "browser_new_tab"

    plan_chrome = semantic_planner._rule_based_fallback("open chrome browser")
    assert len(plan_chrome.steps) >= 1
    assert plan_chrome.steps[0].tool_name == "browser_new_tab"
