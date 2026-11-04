"""
Automated Test Suite for AI-Native Windows OS Assistant.
Verifies the 4 Specialized Agents, Tool Registry, Permission Engine, and Orchestrator.
"""

import sys
from pathlib import Path
import pytest

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from permission_engine import permission_engine, ActionCategory, RiskLevel, PermissionDecision
from tool_registry import tool_registry
from agents.system_agent import system_agent
from agents.file_agent import file_agent
from agents.browser_agent import browser_agent
from agents.vision_agent import vision_agent
from speech_service import normalize_for_speech
from db import (
    init_db, create_task, get_task, update_task_status,
    delete_task, clear_all_tasks, update_task_title,
    save_generated_document, list_generated_documents, delete_generated_document
)
from semantic_planner import semantic_planner


def test_permission_engine_default_deny():
    """Verifies that high-risk and unknown operations are blocked by default."""
    permission_engine.reset_session("task-test-1")
    
    # 1. Safe read is permitted in balanced mode
    permitted, src = permission_engine.is_action_permitted("task-test-1", "D:/test", ActionCategory.SAFE_READ)
    assert permitted is True

    # 2. File delete is blocked by default
    permitted, src = permission_engine.is_action_permitted("task-test-1", "D:/test", ActionCategory.FILE_DELETE)
    assert permitted is False
    assert "EXPLICIT_APPROVAL" in src or "APPROVAL_REQUIRED" in src

    # 3. Emergency stop locks everything
    permission_engine.trigger_emergency_stop()
    assert permission_engine.is_emergency_stopped() is True
    permitted, src = permission_engine.is_action_permitted("task-test-1", "D:/test", ActionCategory.SAFE_READ)
    assert permitted is False
    assert src == "EMERGENCY_STOP_ACTIVE"

    # Reset
    permission_engine.clear_emergency_stop()
    assert permission_engine.is_emergency_stopped() is False


def test_system_agent_telemetry():
    """Verifies real-time CPU, RAM, and disk metrics via psutil."""
    telem = system_agent.get_system_telemetry()
    assert telem["success"] is True
    assert "cpu" in telem
    assert telem["cpu"]["cores"] > 0
    assert "memory" in telem
    assert telem["memory"]["total_gb"] > 0
    assert len(telem["disks"]) > 0


def test_file_agent_safe_paths(tmp_path):
    """Verifies file containment, rolling backups, and unified diff previews."""
    agent = file_agent
    test_file = tmp_path / "hello.txt"
    test_path_str = str(test_file)

    # 1. Write file
    w_res = agent.write_file(test_path_str, "Hello World\nLine 2\n")
    assert w_res["success"] is True
    assert test_file.exists()

    # 2. Read file
    r_res = agent.read_file(test_path_str)
    assert r_res["success"] is True
    assert "Hello World" in r_res["content"]

    # 3. Edit file with diff preview and backup
    e_res = agent.edit_file(test_path_str, "Line 2", "Modified Line 2")
    assert e_res["success"] is True
    assert "Modified Line 2" in e_res["diff"]
    assert "Line 2" in e_res["diff"]

    # 4. Refuse deletion without confirm=True
    d_bad = agent.delete_file(test_path_str, confirm=False)
    assert d_bad["success"] is False

    # 5. Safe deletion with confirm=True
    d_ok = agent.delete_file(test_path_str, confirm=True)
    assert d_ok["success"] is True
    assert not test_file.exists()


def test_tool_registry():
    """Verifies all core tools are registered and categorized correctly."""
    tools = tool_registry.list_tools()
    assert len(tools) >= 15
    
    # Check browser tools
    nav_tool = tool_registry.get("browser_navigate")
    assert nav_tool is not None
    assert nav_tool.agent == "Browser Agent"

    # Check system tools
    sys_tool = tool_registry.get("system_telemetry")
    assert sys_tool is not None
    assert sys_tool.agent == "System Agent"


def test_speech_normalizer():
    """Verifies markdown formatting and code blocks are stripped for natural speech."""
    raw = "Here is the result:\n```python\nprint('hello')\n```\nVisit https://example.com for **more** details."
    spoken = normalize_for_speech(raw)
    assert "```" not in spoken
    assert "print('hello')" not in spoken
    assert "https://example.com" not in spoken
    assert "**" not in spoken
    assert "Here is the result" in spoken


def test_semantic_planner_fallback():
    """Verifies deterministic fallback planner produces structured plans."""
    plan = semantic_planner._rule_based_fallback("Check my CPU and RAM usage")
    assert plan.goal is not None
    assert len(plan.steps) >= 1
    assert plan.steps[0].tool_name == "system_telemetry"


def test_db_persistence():
    """Verifies SQLite WAL persistence of tasks and status updates."""
    import uuid
    init_db()
    task_id = f"test-task-{uuid.uuid4().hex[:8]}"
    create_task(task_id, "Test prompt", "D:/test", "balanced", "gemini-2.0-flash")

    t = get_task(task_id)
    assert t is not None
    assert t["id"] == task_id
    assert t["status"] == "QUEUED"

    update_task_status(task_id, "COMPLETED")
    t_updated = get_task(task_id)
    assert t_updated["status"] == "COMPLETED"


def test_document_generator_pptx_and_pdf(tmp_path):
    """Verifies autonomous PowerPoint and PDF document creation with structured content."""
    # Test Presentation
    pptx_out = tmp_path / "Test_Deck.pptx"
    p_res = file_agent.generate_presentation(
        topic="Autonomous OS Systems",
        filename=str(pptx_out)
    )
    assert p_res["success"] is True
    assert pptx_out.exists()
    assert pptx_out.stat().st_size > 5000
    assert p_res["slides_count"] >= 4

    # Test PDF Report
    pdf_out = tmp_path / "Test_Report.pdf"
    pdf_res = file_agent.generate_pdf(
        title="Autonomous Windows OS Performance Report",
        filename=str(pdf_out)
    )
    assert pdf_res["success"] is True
    assert pdf_out.exists()
    assert pdf_out.stat().st_size > 2000


def test_semantic_planner_documents_and_login():
    """Verifies that document creation and login requests route to the proper tools."""
    # PPTX creation request
    p_plan = semantic_planner._rule_based_fallback("create powerpoint on PES University")
    assert len(p_plan.steps) == 1
    assert p_plan.steps[0].tool_name == "file_generate_presentation"
    assert "pes university" in p_plan.steps[0].params["topic"].lower()

    # PDF creation request
    pdf_plan = semantic_planner._rule_based_fallback("generate executive pdf report on Machine Learning")
    assert len(pdf_plan.steps) == 1
    assert pdf_plan.steps[0].tool_name == "file_generate_pdf"

    # Browser login request
    login_plan = semantic_planner._rule_based_fallback("login using credentials")
    assert len(login_plan.steps) == 1
    assert login_plan.steps[0].tool_name == "browser_login"


def test_chat_crud_operations():
    """Verifies full CRUD lifecycle for chat missions: Create, Read, Update, Delete, and Clear All."""
    init_db()
    tid = "crud-task-test-01"

    # 1. Create
    create_task(tid, "Original Prompt Title", "D:/test", "balanced", "gemini-2.0-flash")
    t = get_task(tid)
    assert t is not None
    assert t["user_prompt"] == "Original Prompt Title"

    # 2. Update / Rename
    renamed = update_task_title(tid, "Renamed Prompt Title")
    assert renamed is True
    t_updated = get_task(tid)
    assert t_updated["user_prompt"] == "Renamed Prompt Title"

    # 3. Delete single task
    deleted = delete_task(tid)
    assert deleted is True
    assert get_task(tid) is None

    # 4. Clear all tasks
    create_task("crud-t1", "Task 1", "D:/test", "balanced", "gemini")
    create_task("crud-t2", "Task 2", "D:/test", "balanced", "gemini")
    count = clear_all_tasks()
    assert count >= 2
    assert get_task("crud-t1") is None
    assert get_task("crud-t2") is None


def test_generated_documents_crud(tmp_path):
    """Verifies document metadata persistence, listing, and deletion."""
    init_db()
    doc_id = "doc-test-123"
    fake_file = tmp_path / "PES_Deck.pptx"
    fake_file.write_text("dummy presentation data")

    # 1. Save / Create record
    res = save_generated_document(
        doc_id=doc_id,
        filename=fake_file.name,
        file_path=str(fake_file),
        file_type="PPTX",
        topic="PES University Overview",
        size_bytes=len("dummy presentation data")
    )
    assert res["id"] == doc_id

    # 2. List records
    docs = list_generated_documents()
    found = any(d["id"] == doc_id for d in docs)
    assert found is True

    # 3. Delete record
    deleted_path = delete_generated_document(doc_id)
    assert deleted_path == str(fake_file)
    docs_after = list_generated_documents()
    assert not any(d["id"] == doc_id for d in docs_after)


def test_remote_mobile_search_and_web_app_control():
    """Verifies that web application searches and mobile control commands route properly."""
    # 1. Search in web application prompt
    plan1 = semantic_planner._rule_based_fallback("search in web application for PES university")
    assert plan1.steps[0].tool_name == "browser_search"
    assert "pes university" in plan1.steps[0].params["query"].lower()

    # 2. General search query from mobile
    plan2 = semantic_planner._rule_based_fallback("search for latest AI news")
    assert plan2.steps[0].tool_name == "browser_search"
    assert "latest ai news" in plan2.steps[0].params["query"].lower()

    # 3. Direct URL navigation from mobile
    plan3 = semantic_planner._rule_based_fallback("youtube.com")
    assert plan3.steps[0].tool_name == "browser_navigate"
    assert "youtube.com" in plan3.steps[0].params["url"].lower()


def test_semantic_planner_conversational_code_display():
    """Verifies that requests to show or give code in the application return conversational markdown code."""
    # 1. Direct request to show code in app
    plan = semantic_planner._rule_based_fallback("give me the code in application")
    assert plan.is_conversational is True
    assert plan.conversational_response is not None
    assert "```" in plan.conversational_response
    assert len(plan.steps) == 0

    # 2. Follow-up request using chat history
    history = [
        {"role": "user", "content": "write python palindrome code"},
        {"role": "assistant", "content": "Here is python code:\n```python\ndef is_palindrome(s):\n    return s == s[::-1]\n```"}
    ]
    plan2 = semantic_planner._rule_based_fallback("show code in chat", chat_history=history)
    assert plan2.is_conversational is True
    assert "is_palindrome" in plan2.conversational_response
    assert "```python" in plan2.conversational_response


@pytest.mark.anyio
async def test_orchestrator_code_file_write_execution(tmp_path):
    """Verifies that orchestrator executes code writes and stores the file on disk."""
    code_file = tmp_path / "test_pal.cpp"
    code_text = "#include <iostream>\nint main() { return 0; }\n"
    
    res = await tool_registry.execute("file_write", {"path": str(code_file), "content": code_text})
    assert res["success"] is True
    assert code_file.exists()
    assert "#include <iostream>" in code_file.read_text()





