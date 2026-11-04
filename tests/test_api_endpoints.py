"""
Integration test suite for FastAPI REST endpoints in AI OS Assistant.
Tests Chat CRUD, Document Management CRUD, System Telemetry, and Permissions.
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from main import app
from db import init_db, create_task, get_task, list_tasks, save_generated_document

client = TestClient(app)


def setup_module():
    init_db()


def test_status_endpoint():
    res = client.get("/api/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "agents" in data
    assert "browser" in data["agents"]


def test_telemetry_endpoint():
    res = client.get("/api/telemetry")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "cpu_percent" in data
    assert "ram_percent" in data


def test_chat_crud_endpoints():
    # 1. Create task directly via db
    tid = "api-test-task-1"
    create_task(tid, "Initial User Mission", "D:/test", "balanced", "gemini-2.0-flash")

    # 2. Get task
    res = client.get(f"/api/tasks/{tid}")
    assert res.status_code == 200
    assert res.json()["user_prompt"] == "Initial User Mission"

    # 3. Patch / Update task title
    res_patch = client.patch(f"/api/tasks/{tid}", json={"title": "Updated Mission Title"})
    assert res_patch.status_code == 200
    assert res_patch.json()["title"] == "Updated Mission Title"

    # 4. Verify in list
    res_list = client.get("/api/tasks")
    assert res_list.status_code == 200
    tasks = res_list.json()["tasks"]
    assert any(t["id"] == tid for t in tasks)

    # 5. Delete individual task
    res_del = client.delete(f"/api/tasks/{tid}")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    # 6. Verify deleted
    res_not_found = client.get(f"/api/tasks/{tid}")
    assert res_not_found.status_code == 404

    # 7. Test clear all
    create_task("batch-1", "Mission A", "D:/test", "balanced", "gemini")
    create_task("batch-2", "Mission B", "D:/test", "balanced", "gemini")
    res_clear = client.delete("/api/tasks")
    assert res_clear.status_code == 200
    assert res_clear.json()["count"] >= 2


def test_documents_crud_endpoints(tmp_path):
    # 1. Direct generation via API
    res_pptx = client.post("/api/documents/generate", json={
        "doc_type": "pptx",
        "topic": "PES University Robotics",
        "filename": "PES_Robotics_Deck.pptx"
    })
    assert res_pptx.status_code == 200
    p_data = res_pptx.json()
    assert p_data["success"] is True
    assert "PES_Robotics_Deck.pptx" in p_data["filename"]
    assert Path(p_data["path"]).exists()

    # 2. List documents
    res_list = client.get("/api/documents")
    assert res_list.status_code == 200
    docs = res_list.json()["documents"]
    assert len(docs) >= 1
    found = next((d for d in docs if "PES_Robotics_Deck.pptx" in d["filename"]), None)
    assert found is not None

    # 3. View document in new tab & Reveal document
    doc_id = found["id"]
    res_view = client.get(f"/api/documents/view/{doc_id}")
    assert res_view.status_code == 200
    assert "application" in res_view.headers.get("content-type", "")

    res_reveal = client.post("/api/documents/reveal", json={"doc_id": doc_id})
    assert res_reveal.status_code == 200
    assert res_reveal.json()["success"] is True
    assert "path" in res_reveal.json()
    assert Path(res_reveal.json()["path"]).exists()

    res_open = client.post("/api/documents/open", json={"doc_id": doc_id})
    assert res_open.status_code == 200
    assert res_open.json()["success"] is True

    # 4. Delete individual document
    res_del = client.delete(f"/api/documents/{doc_id}")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True
    # Verify disk deletion
    assert not Path(found["file_path"]).exists()

    # 5. Test individual document deletion for generated test items
    r_a = client.post("/api/documents/generate", json={"doc_type": "pptx", "topic": "Deck A"}).json()
    r_b = client.post("/api/documents/generate", json={"doc_type": "pdf", "topic": "Report B"}).json()
    if r_a.get("doc_id"):
        client.delete(f"/api/documents/{r_a['doc_id']}")
    if r_b.get("doc_id"):
        client.delete(f"/api/documents/{r_b['doc_id']}")


def test_websocket_remote_pairing():
    # 1. Pairing with PIN 4826
    with client.websocket_connect("/ws/remote") as ws:
        ws.send_json({"pin": "4826"})
        resp = ws.receive_json()
        assert resp["type"] == "AUTH_SUCCESS"
        assert "token" in resp

    # 2. Pairing with valid token
    from config import settings
    with client.websocket_connect("/ws/remote") as ws:
        ws.send_json({"token": settings.REMOTE_AUTH_TOKEN})
        resp = ws.receive_json()
        assert resp["type"] == "AUTH_SUCCESS"


def test_file_upload_and_conversion_endpoints(tmp_path):
    # 1. Test POST /api/files/upload
    sample_content = b"Financial Revenue Analysis\nQ1: $120,000\nQ2: $145,000\nQ3: $180,000\nQ4: $210,000\nTotal Annual: $655,000"
    files = {"file": ("q4_financials.txt", sample_content, "text/plain")}
    res_upload = client.post("/api/files/upload", files=files)
    assert res_upload.status_code == 200
    up_data = res_upload.json()
    assert up_data["success"] is True
    assert up_data["filename"].startswith("q4_financials")
    uploaded_path = Path(up_data["path"])
    assert uploaded_path.exists()

    # 2. Test GET /api/files/uploads
    res_list = client.get("/api/files/uploads")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["success"] is True
    assert any(f["filename"].startswith("q4_financials") for f in list_data["uploads"])

    # 3. Test POST /api/files/extract
    res_extract = client.post("/api/files/extract", json={"path": str(uploaded_path)})
    assert res_extract.status_code == 200
    ext_data = res_extract.json()
    assert ext_data["success"] is True
    assert "Financial Revenue" in ext_data["text"]

    # 4. Test POST /api/files/convert (Single File: TXT -> DOCX)
    res_convert_docx = client.post("/api/files/convert", json={
        "source_path": str(uploaded_path),
        "target_format": "docx"
    })
    assert res_convert_docx.status_code == 200
    conv_docx_data = res_convert_docx.json()
    assert conv_docx_data["success"] is True
    assert conv_docx_data["filename"].endswith(".docx")
    assert Path(conv_docx_data["path"]).exists()

    # 5. Test POST /api/files/convert (Single File: TXT -> PDF)
    res_convert_pdf = client.post("/api/files/convert", json={
        "source_path": str(uploaded_path),
        "target_format": "pdf"
    })
    assert res_convert_pdf.status_code == 200
    conv_pdf_data = res_convert_pdf.json()
    assert conv_pdf_data["success"] is True
    assert conv_pdf_data["filename"].endswith(".pdf")
    assert Path(conv_pdf_data["path"]).exists()

    # 6. Test Directory Batch Conversion
    batch_dir = tmp_path / "batch_docs"
    batch_dir.mkdir(parents=True, exist_ok=True)
    (batch_dir / "report1.txt").write_text("Report 1 metrics\nValue: 100", encoding="utf-8")
    (batch_dir / "report2.txt").write_text("Report 2 metrics\nValue: 200", encoding="utf-8")

    res_batch = client.post("/api/files/convert", json={
        "source_path": str(batch_dir),
        "target_format": "docx"
    })
    assert res_batch.status_code == 200
    b_data = res_batch.json()
    assert b_data["success"] is True
    assert b_data["is_batch"] is True
    assert b_data["converted_count"] == 2

    # 7. Test Semantic Planner conversion routing
    from semantic_planner import semantic_planner
    plan = semantic_planner._rule_based_fallback(f"[Attached file: {uploaded_path}]\nConvert this file to Excel")
    assert len(plan.steps) >= 1
    assert plan.steps[0].tool_name == "file_convert_document"
    assert plan.steps[0].params["target_format"] == "xlsx"
    assert plan.steps[0].params["source_path"] == str(uploaded_path)

    plan_folder = semantic_planner._rule_based_fallback(f"Please go to folder {batch_dir} and convert all files to Word")
    assert len(plan_folder.steps) >= 1
    assert plan_folder.steps[0].tool_name == "file_convert_document"
    assert plan_folder.steps[0].params["target_format"] == "docx"


def test_human_approval_resolution_endpoints():
    import asyncio
    from permission_engine import permission_engine, PermissionDecision

    # 1. Setup a mock pending approval
    appr_id = "test-appr-42"
    fut = asyncio.get_event_loop().create_future() if asyncio.get_event_loop().is_running() else asyncio.new_event_loop().create_future()
    permission_engine._pending_approvals[appr_id] = fut

    # 2. POST /api/approvals/{approval_id}/decision with "allow_once"
    res = client.post(f"/api/approvals/{appr_id}/decision", json={"decision": "allow_once"})
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["decision"] == "allow_once"

    # Verify Future received ALLOW_ONCE
    dec, meta = fut.result()
    assert dec == PermissionDecision.ALLOW_ONCE

    # 3. Setup another pending approval for "allow_session"
    appr_id_session = "test-appr-session-99"
    fut_session = asyncio.new_event_loop().create_future()
    permission_engine._pending_approvals[appr_id_session] = fut_session

    res_session = client.post(f"/api/approvals/{appr_id_session}/decision", json={"decision": "allow_session"})
    assert res_session.status_code == 200
    assert res_session.json()["success"] is True

    dec_s, _ = fut_session.result()
    assert dec_s == PermissionDecision.ALLOW_SESSION


def test_monitors_and_multi_screen_endpoints():
    """Validates multi-monitor enumeration and screenshot targeting."""
    res = client.get("/api/monitors")
    assert res.status_code == 200
    data = res.json()
    assert "monitors" in data
    assert len(data["monitors"]) >= 1
    first_mon = data["monitors"][0]
    assert "index" in first_mon
    assert "width" in first_mon
    assert "height" in first_mon

    # Test screenshot with specific monitor index
    shot_res = client.get(f"/api/screenshot?monitor={first_mon['index']}&scale=0.2")
    assert shot_res.status_code == 200
    assert shot_res.headers["content-type"] == "image/jpeg"
    assert len(shot_res.content) > 100
