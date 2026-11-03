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
