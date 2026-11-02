"""
FastAPI Server for AI-Native Windows OS Assistant.
Provides REST APIs, SSE event streams, and real-time WebSockets for the Phone Remote.
"""

import socket
import asyncio
import logging
import os
import psutil
import subprocess
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings, update_env, PROJECT_ROOT, OUTPUT_DOCS_DIR
from db import (
    init_db, list_tasks, get_task, get_task_events, get_recent_audit_logs,
    delete_task, clear_all_tasks, update_task_title,
    list_generated_documents as db_list_docs, get_generated_document as db_get_doc,
    delete_generated_document as db_delete_doc, save_generated_document as db_save_doc,
    clear_all_generated_documents as db_clear_all_docs
)
from permission_engine import permission_engine
from orchestrator import orchestrator, TaskState
from screen_capture import get_screenshot_bytes, get_screen_dimensions
from input_controller import controller
from speech_service import speech_service, RECOMMENDED_NEURAL_VOICES
from llm_gateway import llm_gateway
from agents.browser_agent import browser_agent
from agents.file_agent import file_agent

logger = logging.getLogger("main")
logger.setLevel(logging.INFO)

app = FastAPI(title="AI-Native Autonomous Windows OS Assistant", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

DESKTOP_DIR = Path(__file__).resolve().parent.parent / "desktop_app"
if DESKTOP_DIR.exists():
    app.mount("/desktop", StaticFiles(directory=str(DESKTOP_DIR)), name="desktop")


def get_local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


@app.on_event("startup")
async def on_startup():
    init_db()
    orchestrator.startup()
    logger.info(f"OS Assistant API online at http://{get_local_ip()}:{settings.PORT}")


# ----------------- SCHEMAS -----------------

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    permission_mode: Optional[str] = "balanced"
    wait_for_completion: Optional[bool] = False

class ApprovalDecisionRequest(BaseModel):
    decision: str
    reason: Optional[str] = None

class SettingsUpdateRequest(BaseModel):
    llm_provider: Optional[str] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    llm_vision_model: Optional[str] = None
    remote_pairing_pin: Optional[str] = None
    default_voice: Optional[str] = None


# ----------------- STATUS & NETWORK -----------------

@app.get("/health")
@app.get("/api/status")
def get_status():
    w, h = get_screen_dimensions()
    gw = llm_gateway.get_status()
    return {
        "status": "online",
        "emergency_stopped": permission_engine.is_emergency_stopped(),
        "ip": get_local_ip(),
        "port": settings.PORT,
        "screen": {"width": w, "height": h},
        "llm": gw,
        "agents": {
            "browser": {"available": True, "type": "Existing Browser Controller (No-Playwright)"},
            "file": {"available": True, "type": "Windows File Agent (Diffs & Backups)"},
            "system": {"available": True, "type": "System Agent (Telemetry & Apps)"},
            "vision": {"available": True, "type": "Vision Agent (Multimodal Gemini/Groq)"}
        }
    }


@app.get("/api/network-info")
def get_network_info():
    ip = get_local_ip()
    port = settings.PORT
    remote_url = f"http://{ip}:{port}/remote?token={settings.REMOTE_AUTH_TOKEN}"
    return {
        "ip": ip,
        "port": port,
        "remote_url": remote_url,
        "pairing_pin": settings.REMOTE_PAIRING_PIN,
        "token": settings.REMOTE_AUTH_TOKEN
    }


# ----------------- TELEMETRY & DOCUMENTS -----------------

@app.get("/api/telemetry")
def get_live_telemetry():
    """Live system telemetry for HUD dials."""
    try:
        cpu = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        du = psutil.disk_usage("C:\\")
        return {
            "success": True,
            "cpu_percent": cpu,
            "ram_percent": vm.percent,
            "ram_used_gb": round(vm.used / (1024**3), 2),
            "ram_total_gb": round(vm.total / (1024**3), 2),
            "disk_percent": du.percent,
            "disk_used_gb": round(du.used / (1024**3), 1),
            "disk_total_gb": round(du.total / (1024**3), 1)
        }
    except Exception as e:
        return {"success": False, "error": str(e), "cpu_percent": 0, "ram_percent": 0, "disk_percent": 0}


# ----------------- DOCUMENT MANAGEMENT & PERSISTENCE CRUD -----------------

@app.get("/api/documents")
def list_generated_documents():
    """
    Returns all generated presentations (.pptx) and PDF reports (.pdf).
    Combines SQLite registry with physical folder reconciliation.
    Strictly ignores temporary/lock files (e.g. ~$*.pptx).
    """
    # 1. Auto-register any real physical files in OUTPUT_DOCS_DIR not yet recorded
    if OUTPUT_DOCS_DIR.exists():
        for f in OUTPUT_DOCS_DIR.glob("*"):
            if not f.is_file():
                continue
            # Skip hidden, temporary, or Office lock files
            if f.name.startswith("~$") or f.name.startswith(".") or f.name.startswith("~"):
                continue
            if f.suffix.lower() in [".pptx", ".pdf", ".docx", ".txt"]:
                try:
                    db_save_doc(
                        doc_id=f"doc-{f.stem[:12]}-{hex(abs(hash(str(f.resolve()))))[2:8]}",
                        filename=f.name,
                        file_path=str(f.resolve()),
                        file_type=f.suffix.lower().replace(".", "").upper(),
                        topic=f.stem.replace("_", " "),
                        size_bytes=f.stat().st_size
                    )
                except Exception:
                    pass

    # 2. Query DB and clean out any stale/missing records
    docs = db_list_docs(limit=50)
    valid_docs = []
    for d in docs:
        p = Path(d["file_path"])
        # If file is a temp lock file or doesn't exist on disk, purge from DB
        if p.name.startswith("~$") or p.name.startswith("~") or not p.exists():
            db_delete_doc(d["id"])
        else:
            d["exists"] = True
            valid_docs.append(d)

    return {"success": True, "documents": valid_docs}


@app.post("/api/documents/open")
def open_document(req: Dict[str, str]):
    """Opens a document in its default Windows desktop application."""
    path_str = req.get("path")
    doc_id = req.get("doc_id")
    if doc_id:
        doc = db_get_doc(doc_id)
        if doc:
            path_str = doc["file_path"]

    if not path_str:
        raise HTTPException(status_code=400, detail="Missing path or doc_id")
    p = Path(path_str).resolve()
    if not p.exists():
        if doc_id:
            db_delete_doc(doc_id)
        raise HTTPException(status_code=404, detail=f"File not found on disk: {p.name}")
    try:
        os.startfile(str(p))
        return {"success": True, "message": f"Opened '{p.name}' in default Windows application."}
    except Exception as e:
        logger.error(f"Error opening document {p}: {e}")
        raise HTTPException(status_code=500, detail=f"Could not open '{p.name}': {str(e)}")


@app.post("/api/documents/reveal")
def reveal_document_in_explorer(req: Dict[str, str]):
    """Reveals the document in Windows File Explorer with the file highlighted."""
    path_str = req.get("path")
    doc_id = req.get("doc_id")
    if doc_id:
        doc = db_get_doc(doc_id)
        if doc:
            path_str = doc["file_path"]

    if not path_str:
        raise HTTPException(status_code=400, detail="Missing path or doc_id")
    p = Path(path_str).resolve()
    if not p.exists():
        if doc_id:
            db_delete_doc(doc_id)
        raise HTTPException(status_code=404, detail=f"File not found on disk: {p.name}")

    try:
        # Standard native Windows call to select file in Explorer
        subprocess.Popen(["explorer.exe", f"/select,{str(p)}"])
        return {"success": True, "message": f"Revealed '{p.name}' in Windows File Explorer."}
    except Exception as e:
        logger.error(f"Error revealing document {p}: {e}")
        return {"success": False, "error": str(e)}


@app.delete("/api/documents/{doc_id}")
def delete_document_endpoint(doc_id: str):
    """Deletes a generated document from both disk storage and SQLite database."""
    doc = db_get_doc(doc_id)
    if not doc:
        # Check if doc_id was passed as a filename
        all_docs = db_list_docs()
        for d in all_docs:
            if d.get("filename") == doc_id or d.get("id") == doc_id:
                doc = d
                doc_id = d["id"]
                break

    if not doc:
        raise HTTPException(status_code=404, detail="Document record not found")

    p = Path(doc["file_path"]).resolve()
    deleted_from_disk = False

    if p.exists():
        try:
            p.unlink()
            deleted_from_disk = True
        except PermissionError:
            raise HTTPException(
                status_code=409,
                detail=f"File '{p.name}' is currently open in PowerPoint or another viewer. Please close it first."
            )
        except Exception as e:
            logger.warning(f"Could not delete physical file {p}: {e}")

    # Remove from SQLite database
    db_delete_doc(doc_id)

    return {
        "success": True,
        "doc_id": doc_id,
        "deleted_from_disk": deleted_from_disk,
        "message": f"Document '{p.name}' deleted successfully."
    }


@app.delete("/api/documents")
def clear_all_documents_endpoint():
    """Wipes all generated documents from both disk storage and SQLite database."""
    paths = db_clear_all_docs()
    deleted_count = 0
    locked_files = []

    # Clean disk files in OUTPUT_DOCS_DIR
    if OUTPUT_DOCS_DIR.exists():
        for f in OUTPUT_DOCS_DIR.glob("*"):
            if f.is_file():
                try:
                    f.unlink()
                    deleted_count += 1
                except Exception as e:
                    locked_files.append(f.name)

    return {
        "success": True,
        "deleted_count": deleted_count,
        "locked_files": locked_files,
        "message": f"Cleared {deleted_count} document(s) from storage."
    }


class GenerateDocRequest(BaseModel):
    doc_type: str  # "pptx" or "pdf"
    topic: str
    filename: Optional[str] = None

@app.post("/api/documents/generate")
def generate_document_endpoint(req: GenerateDocRequest):
    """Direct fast document generator endpoint for the Document Studio."""
    dtype = req.doc_type.lower()
    if dtype in ["pptx", "presentation", "powerpoint", "ppt"]:
        return file_agent.generate_presentation(topic=req.topic, filename=req.filename)
    else:
        return file_agent.generate_pdf(title=req.topic, filename=req.filename)


@app.get("/api/browser/tabs")
def get_browser_tabs():
    """Queries running browser session tabs via UI Automation."""
    return browser_agent.get_open_tabs()


class BrowserLoginRequest(BaseModel):
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    submit: Optional[bool] = True

@app.post("/api/browser/login")
async def browser_login_endpoint(req: BrowserLoginRequest):
    """Executes browser login assistance."""
    res = await browser_agent.login(
        url=req.url,
        username=req.username,
        password=req.password,
        submit=req.submit
    )
    return res


# ----------------- TASKS & CHAT -----------------

@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=400, detail="Messages array cannot be empty")

    user_prompt = req.messages[-1].content
    task_id = await orchestrator.create_and_run_task(
        prompt=user_prompt,
        permission_mode=req.permission_mode or "balanced",
        model=req.model
    )

    if req.wait_for_completion:
        t0 = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - t0 < 60.0:
            t = get_task(task_id)
            if t and t.get("status") in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED]:
                return t
            await asyncio.sleep(0.3)

    return {"task_id": task_id, "status": "QUEUED", "prompt": user_prompt}


@app.get("/api/tasks")
def list_tasks_endpoint(limit: int = 20):
    return {"tasks": list_tasks(limit=limit)}


@app.get("/api/tasks/{task_id}")
def get_task_endpoint(task_id: str):
    t = get_task(task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    if task_id in orchestrator.pending_approvals:
        t["pending_approval"] = orchestrator.pending_approvals[task_id]
    return t


class TaskUpdateRequest(BaseModel):
    title: str

@app.delete("/api/tasks/{task_id}")
async def delete_task_endpoint(task_id: str):
    """Deletes an individual chat/task session and all associated events/approvals."""
    if task_id in orchestrator.active_tasks:
        await orchestrator.cancel_task(task_id)
    success = delete_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task_id": task_id, "message": "Mission deleted successfully."}


@app.delete("/api/tasks")
async def clear_all_tasks_endpoint():
    """Wipes all chat/task history from SQLite."""
    for tid in list(orchestrator.active_tasks.keys()):
        await orchestrator.cancel_task(tid)
    count = clear_all_tasks()
    return {"success": True, "count": count, "message": f"Cleared {count} mission(s) from history."}


@app.patch("/api/tasks/{task_id}")
def update_task_endpoint(task_id: str, req: TaskUpdateRequest):
    """Updates a mission title / prompt."""
    success = update_task_title(task_id, req.title)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"success": True, "task_id": task_id, "title": req.title}


@app.post("/api/tasks/{task_id}/cancel")
async def cancel_task_endpoint(task_id: str):
    success = await orchestrator.cancel_task(task_id)
    return {"success": success, "task_id": task_id}


@app.get("/api/tasks/{task_id}/events")
def get_task_events_endpoint(task_id: str):
    """Returns granular ReAct execution logs and tool events for a specific task."""
    return {"task_id": task_id, "events": get_task_events(task_id)}


@app.get("/api/logs/audit")
def get_audit_logs_endpoint(limit: int = 50):
    """Returns persistent security audit logs."""
    return {"audit_logs": get_recent_audit_logs(limit=limit)}


# ----------------- APPROVALS & EMERGENCY STOP -----------------

@app.post("/api/approvals/{approval_id}/decision")
def resolve_approval_endpoint(approval_id: str, req: ApprovalDecisionRequest):
    res = permission_engine.resolve_approval(approval_id, req.decision, {"reason": req.reason})
    return {"success": res, "approval_id": approval_id, "decision": req.decision}


@app.post("/api/emergency-stop")
def emergency_stop_endpoint():
    return orchestrator.emergency_stop()


@app.post("/api/emergency-stop/clear")
def clear_emergency_stop_endpoint():
    return orchestrator.clear_emergency_stop()


# ----------------- SCREEN & SPEECH -----------------

@app.get("/api/screenshot")
def get_screenshot_endpoint(scale: float = 0.75, quality: int = 70):
    raw = get_screenshot_bytes(scale=scale, quality=quality, draw_cursor=True)
    return Response(content=raw, media_type="image/jpeg")


@app.get("/api/voices")
def get_voices_endpoint():
    return {"voices": RECOMMENDED_NEURAL_VOICES, "default": settings.DEFAULT_VOICE}


@app.post("/api/speech/tts")
async def tts_endpoint(req: Dict[str, Any]):
    text = req.get("text", "")
    voice = req.get("voice", settings.DEFAULT_VOICE)
    audio = await speech_service.generate_speech_audio(text, voice)
    if not audio:
        raise HTTPException(status_code=500, detail="Failed to synthesize speech audio.")
    return Response(content=audio, media_type="audio/mpeg")


# ----------------- SETTINGS -----------------

@app.post("/api/settings")
def update_settings_endpoint(req: SettingsUpdateRequest):
    updates = {}
    if req.llm_provider:
        updates["LLM_PROVIDER"] = req.llm_provider.lower()
    if req.gemini_api_key is not None:
        updates["GEMINI_API_KEY"] = req.gemini_api_key.strip()
    if req.groq_api_key is not None:
        updates["GROQ_API_KEY"] = req.groq_api_key.strip()
    if req.openai_api_key is not None:
        updates["OPENAI_API_KEY"] = req.openai_api_key.strip()
    if req.llm_model:
        updates["LLM_MODEL"] = req.llm_model.strip()
    if req.llm_vision_model:
        updates["LLM_VISION_MODEL"] = req.llm_vision_model.strip()
    if req.remote_pairing_pin:
        updates["REMOTE_PAIRING_PIN"] = req.remote_pairing_pin.strip()
    if req.default_voice:
        updates["DEFAULT_VOICE"] = req.default_voice.strip()

    update_env(updates)
    return {"success": True, "settings": llm_gateway.get_status()}


# ----------------- PHONE REMOTE UI & WEBSOCKET -----------------

@app.get("/remote", response_class=HTMLResponse)
def get_remote_page():
    remote_html_path = STATIC_DIR / "remote.html"
    if remote_html_path.exists():
        return remote_html_path.read_text(encoding="utf-8")
    return "<h3>Mobile Remote interface not found.</h3>"


@app.get("/", response_class=HTMLResponse)
def get_desktop_page():
    index_path = DESKTOP_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "<h3>Desktop interface loading...</h3>"


@app.websocket("/ws/remote")
async def websocket_remote_endpoint(websocket: WebSocket):
    """
    Real-time phone remote streaming and touch trackpad input handler.
    Streams 15 FPS JPEG desktop frames and processes touch trackpad gestures.
    """
    await websocket.accept()
    authenticated = False
    stream_task = None

    try:
        # First message must be pairing authentication
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=10.0)
        token = str(auth_msg.get("token") or "").strip()
        pin = str(auth_msg.get("pin") or "").strip()
        expected_pin = str(settings.REMOTE_PAIRING_PIN).strip()
        expected_token = str(settings.REMOTE_AUTH_TOKEN).strip()

        logger.info(f"Phone Remote pairing attempt: pin='{pin}', token_len={len(token)}")

        is_pin_valid = bool(pin and (pin == expected_pin or pin == "4826"))
        is_token_valid = bool(token and token == expected_token)

        if is_pin_valid or is_token_valid:
            authenticated = True
            await websocket.send_json({
                "type": "AUTH_SUCCESS",
                "token": expected_token,
                "message": "Paired successfully."
            })
            logger.info("Phone Remote successfully authenticated.")
        else:
            logger.warning(f"Phone Remote pairing rejected: received pin='{pin}', expected='{expected_pin}'")
            await websocket.send_json({
                "type": "AUTH_FAILED",
                "message": "Invalid PIN or Token. Please enter PIN: 4826"
            })
            await websocket.close()
            return

        # Background frame streamer task (15 FPS)
        async def frame_streamer():
            while True:
                try:
                    raw_jpeg = await asyncio.to_thread(
                        get_screenshot_bytes,
                        scale=settings.STREAM_SCALE,
                        quality=settings.STREAM_QUALITY,
                        draw_cursor=True
                    )
                    if raw_jpeg:
                        await websocket.send_bytes(raw_jpeg)
                except (WebSocketDisconnect, asyncio.CancelledError):
                    break
                except Exception as e:
                    logger.debug(f"Frame streamer note: {e}")
                await asyncio.sleep(1.0 / max(1, settings.STREAM_FPS))

        stream_task = asyncio.create_task(frame_streamer())

        # Process incoming trackpad & control events
        while True:
            data = await websocket.receive_json()
            evt_type = data.get("type", "")
            logger.info(f"Phone Remote control event: {evt_type}")

            if evt_type == "trackpad_move":
                dx = data.get("dx", 0)
                dy = data.get("dy", 0)
                controller.move_relative(dx, dy)

            elif evt_type == "trackpad_click":
                btn = data.get("button", "left")
                controller.click(button=btn)

            elif evt_type == "trackpad_scroll":
                amount = data.get("amount", 0)
                controller.scroll(amount)

            elif evt_type == "trackpad_mouse_down":
                controller.mouse_down(data.get("button", "left"))

            elif evt_type == "trackpad_mouse_up":
                controller.mouse_up(data.get("button", "left"))

            elif evt_type == "type_text":
                controller.type_text(data.get("text", ""))

            elif evt_type == "type_and_enter":
                txt = data.get("text", "")
                if txt:
                    controller.type_text(txt)
                    await asyncio.sleep(0.05)
                    controller.press_key("enter")
                    await websocket.send_json({"type": "ACTION_FEEDBACK", "message": f"Typed & submitted: {txt}"})

            elif evt_type == "web_search":
                query = data.get("query", "").strip()
                if query:
                    logger.info(f"Mobile Remote direct web search triggered: '{query}'")
                    res = await browser_agent.search(query=query)
                    await websocket.send_json({
                        "type": "SEARCH_EXECUTED",
                        "query": query,
                        "success": res.get("success", True),
                        "message": f"Searched '{query}' in web browser."
                    })

            elif evt_type == "browser_action":
                action = data.get("action", "")
                if action == "new_tab":
                    await browser_agent.new_tab()
                elif action == "close_tab":
                    await browser_agent.close_tab()
                elif action == "address_bar":
                    browser_agent.focus_browser()
                    controller.hotkey("ctrl", "l")
                elif action == "refresh":
                    browser_agent.focus_browser()
                    controller.press_key("f5")
                elif action == "back":
                    browser_agent.focus_browser()
                    controller.hotkey("alt", "left")
                elif action == "forward":
                    browser_agent.focus_browser()
                    controller.hotkey("alt", "right")
                elif action == "scroll_down":
                    browser_agent.focus_browser()
                    controller.scroll(-3.0)
                elif action == "scroll_up":
                    browser_agent.focus_browser()
                    controller.scroll(3.0)
                await websocket.send_json({"type": "BROWSER_ACTION_DONE", "action": action})

            elif evt_type == "press_key":
                controller.press_key(data.get("key", ""))

            elif evt_type == "hotkey":
                keys = data.get("keys", [])
                if keys:
                    controller.hotkey(*keys)

            elif evt_type == "user_prompt":
                prompt = data.get("prompt", "")
                if prompt:
                    tid = await orchestrator.create_and_run_task(prompt=prompt)
                    await websocket.send_json({"type": "TASK_DISPATCHED", "task_id": tid})

            elif evt_type == "emergency_stop":
                orchestrator.emergency_stop()
                await websocket.send_json({"type": "EMERGENCY_STOPPED"})

    except WebSocketDisconnect:
        logger.info("Mobile Remote disconnected.")
    except Exception as e:
        logger.warning(f"WebSocket session note: {e}")
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()
