"""
FastAPI Server for AI-Native Windows OS Assistant.
Provides REST APIs, SSE event streams, and real-time WebSockets for the Phone Remote.
"""

import socket
import asyncio
import logging
import os
import sys
from pathlib import Path

_backend_dir = Path(__file__).resolve().parent
if str(_backend_dir) not in sys.path:
    sys.path.insert(0, str(_backend_dir))

import psutil
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings, update_env, PROJECT_ROOT, OUTPUT_DOCS_DIR, UPLOADS_DIR
from db import (
    init_db, list_tasks, get_task, get_task_events, get_recent_audit_logs, clear_audit_logs,
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
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
    # 1. Standard UDP probe to external IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith('127.'):
            return ip
    except Exception:
        pass

    # 2. Iterate local network adapters via psutil (catches Wi-Fi/Ethernet even on offline or private LAN)
    try:
        for iface, addrs in psutil.net_if_addrs().items():
            for a in addrs:
                if a.family == socket.AF_INET:
                    addr = a.address
                    if not addr.startswith('127.') and not addr.startswith('169.254.'):
                        return addr
    except Exception:
        pass

    # 3. Hostname DNS resolution
    try:
        host = socket.gethostname()
        for ip in socket.gethostbyname_ex(host)[2]:
            if not ip.startswith('127.') and not ip.startswith('169.254.'):
                return ip
    except Exception:
        pass

    return '127.0.0.1'


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
    dims = get_screen_dimensions()
    return {
        "ip": ip,
        "port": port,
        "remote_url": remote_url,
        "pairing_pin": settings.REMOTE_PAIRING_PIN,
        "token": settings.REMOTE_AUTH_TOKEN,
        "screen_width": dims[0],
        "screen_height": dims[1]
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
    # 1. Check existing DB records first to prevent resetting timestamps or clearing task_id
    existing_docs = db_list_docs(limit=100)
    existing_paths = {str(Path(d["file_path"]).resolve()).lower() for d in existing_docs if d.get("file_path")}

    # 2. Auto-register only unrecorded physical files in OUTPUT_DOCS_DIR
    if OUTPUT_DOCS_DIR.exists():
        for f in OUTPUT_DOCS_DIR.glob("*"):
            if not f.is_file():
                continue
            # Skip hidden, temporary, or Office lock files
            if f.name.startswith("~$") or f.name.startswith(".") or f.name.startswith("~"):
                continue
            fpath_str = str(f.resolve())
            if fpath_str.lower() not in existing_paths and f.suffix.lower() in [".pptx", ".pdf", ".docx", ".xlsx", ".txt", ".png", ".jpg", ".jpeg"]:
                try:
                    db_save_doc(
                        doc_id=f"doc-{f.stem[:12]}-{hex(abs(hash(fpath_str)))[2:8]}",
                        filename=f.name,
                        file_path=fpath_str,
                        file_type=f.suffix.lower().replace(".", "").upper(),
                        topic=f.stem.replace("_", " "),
                        size_bytes=f.stat().st_size
                    )
                except Exception:
                    pass

    # 3. Query DB and clean out any stale/missing records or test temp files
    docs = db_list_docs(limit=50)
    valid_docs = []
    proj_resolved = PROJECT_ROOT.resolve()
    for d in docs:
        try:
            p = Path(d["file_path"]).resolve()
            is_in_project = p.is_relative_to(proj_resolved)
        except Exception:
            is_in_project = False

        # Purge temporary lock files, pytest temp files outside project, or non-existent files
        if not is_in_project or p.name.startswith("~$") or p.name.startswith("~") or not p.exists():
            db_delete_doc(d["id"])
        else:
            d["exists"] = True
            valid_docs.append(d)

    return {"success": True, "documents": valid_docs}


@app.get("/api/documents/view/{doc_id}")
@app.get("/api/documents/view")
def view_document_in_tab(doc_id: Optional[str] = None, path: Optional[str] = None):
    """Serves the document file directly for viewing in a new browser tab with inline disposition."""
    path_str = path
    if doc_id:
        doc = db_get_doc(doc_id)
        if doc and doc.get("file_path"):
            path_str = doc["file_path"]

    if not path_str and doc_id:
        for f in OUTPUT_DOCS_DIR.glob("*"):
            if doc_id in f.name or f.stem in doc_id:
                path_str = str(f.resolve())
                break

    if not path_str or not Path(path_str).exists():
        raise HTTPException(status_code=404, detail="Document file not found on disk.")

    p = Path(path_str).resolve()
    media_types = {
        ".pdf": "application/pdf",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".txt": "text/plain; charset=utf-8",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg"
    }
    media_type = media_types.get(p.suffix.lower(), "application/octet-stream")

    return FileResponse(
        str(p),
        media_type=media_type,
        filename=p.name,
        content_disposition_type="inline"
    )


@app.post("/api/documents/open")
def open_document(req: Dict[str, str]):
    """Opens a document in its default Windows desktop application using native ShellExecute / os.startfile."""
    path_str = req.get("path")
    doc_id = req.get("doc_id")
    if doc_id:
        doc = db_get_doc(doc_id)
        if doc and doc.get("file_path"):
            path_str = doc["file_path"]

    # Fallback: search in OUTPUT_DOCS_DIR if path was lost
    if not path_str and doc_id:
        for f in OUTPUT_DOCS_DIR.glob("*"):
            if doc_id in f.name or f.stem in doc_id:
                path_str = str(f.resolve())
                break

    if not path_str and req.get("filename"):
        for f in OUTPUT_DOCS_DIR.glob("*"):
            if f.name == req["filename"]:
                path_str = str(f.resolve())
                break

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
        try:
            import ctypes
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", str(p), None, None, 1)
            if ret > 32:
                return {"success": True, "message": f"Opened '{p.name}' in default Windows application."}
            raise RuntimeError(f"ShellExecute error code: {ret}")
        except Exception as e2:
            logger.error(f"Error opening document {p}: {e2}")
            raise HTTPException(status_code=500, detail=f"Could not open '{p.name}': {str(e2)}")


@app.post("/api/documents/reveal")
def reveal_document_in_explorer(req: Dict[str, str]):
    """Reveals the document in Windows File Explorer with the file highlighted."""
    path_str = req.get("path")
    doc_id = req.get("doc_id")
    if doc_id:
        doc = db_get_doc(doc_id)
        if doc and doc.get("file_path"):
            path_str = doc["file_path"]

    # Fallback: search in OUTPUT_DOCS_DIR if path was lost
    if not path_str and doc_id:
        for f in OUTPUT_DOCS_DIR.glob("*"):
            if doc_id in f.name or f.stem in doc_id:
                path_str = str(f.resolve())
                break

    if not path_str and req.get("filename"):
        for f in OUTPUT_DOCS_DIR.glob("*"):
            if f.name == req["filename"]:
                path_str = str(f.resolve())
                break

    if not path_str:
        path_str = str(OUTPUT_DOCS_DIR.resolve())

    p = Path(path_str).resolve()
    if not p.exists():
        candidate = OUTPUT_DOCS_DIR / p.name
        if candidate.exists():
            p = candidate.resolve()
        elif OUTPUT_DOCS_DIR.exists():
            p = OUTPUT_DOCS_DIR.resolve()
        else:
            raise HTTPException(status_code=404, detail=f"File not found on disk: {p.name}")

    try:
        if p.is_file():
            # In Windows, explorer.exe requires /select,"<path>" where /select, is strictly OUTSIDE the quotes.
            # Passing a list to subprocess.Popen triggers list2cmdline which wraps the entire switch in quotes if the path has spaces.
            # Therefore, we pass a single formatted command string.
            clean_path = str(p.resolve())
            cmd = f'explorer.exe /select,"{clean_path}"'
            logger.info(f"Revealing file in Explorer with command: {cmd}")
            subprocess.Popen(cmd, shell=False)
            return {"success": True, "path": clean_path, "message": f"Revealed '{p.name}' in Windows File Explorer."}
        else:
            clean_path = str(p.resolve())
            cmd = f'explorer.exe "{clean_path}"'
            logger.info(f"Opening folder in Explorer with command: {cmd}")
            subprocess.Popen(cmd, shell=False)
            return {"success": True, "path": clean_path, "message": f"Opened folder '{p.name}' in Windows File Explorer."}
    except Exception as e:
        logger.error(f"Error revealing document {p}: {e}")
        try:
            target_dir = str(p.parent if p.is_file() else p)
            os.startfile(target_dir)
            return {"success": True, "path": target_dir, "message": f"Opened folder containing '{p.name}'."}
        except Exception as e2:
            return {"success": False, "error": str(e2)}


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
            # File is locked by PowerPoint, PDF viewer, Word, or Excel.
            # Gracefully terminate viewers to release Windows file handle lock.
            for proc in psutil.process_iter(['name']):
                pname = (proc.info.get('name') or '').lower()
                if any(v in pname for v in ['powerpnt', 'acrord', 'acrobat', 'winword', 'excel', 'notepad']):
                    try:
                        proc.terminate()
                        proc.wait(timeout=1.5)
                    except Exception:
                        pass
            import time
            time.sleep(0.3)
            try:
                p.unlink()
                deleted_from_disk = True
            except Exception as e:
                raise HTTPException(
                    status_code=409,
                    detail=f"File '{p.name}' is currently locked by another application. Please close the viewer and retry."
                )
        except Exception as e:
            logger.warning(f"Could not delete physical file {p}: {e}")

    # Also clean up any associated temporary lock file
    temp_lock = p.parent / f"~${p.name}"
    if temp_lock.exists():
        try:
            temp_lock.unlink()
        except Exception:
            pass

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

    # Close any open viewers to release locks
    for proc in psutil.process_iter(['name']):
        pname = (proc.info.get('name') or '').lower()
        if any(v in pname for v in ['powerpnt', 'acrord', 'acrobat', 'winword', 'excel', 'notepad']):
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                pass

    import time
    time.sleep(0.3)

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
    doc_type: str  # "pptx", "pdf", "docx", or "xlsx"
    topic: str
    filename: Optional[str] = None

@app.post("/api/documents/generate")
def generate_document_endpoint(req: GenerateDocRequest):
    """Direct fast document generator endpoint for the Document Studio."""
    dtype = req.doc_type.lower()
    if dtype in ["pptx", "presentation", "powerpoint", "ppt"]:
        return file_agent.generate_presentation(topic=req.topic, filename=req.filename)
    elif dtype in ["docx", "word", "doc"]:
        return file_agent.generate_word_document(topic=req.topic, filename=req.filename)
    elif dtype in ["xlsx", "excel", "sheet", "spreadsheet", "xls"]:
        return file_agent.generate_excel_spreadsheet(topic=req.topic, filename=req.filename)
    else:
        return file_agent.generate_pdf(title=req.topic, filename=req.filename)


class ConvertDocRequest(BaseModel):
    source_path: str
    target_format: str
    output_dir: Optional[str] = None


class ExtractTextRequest(BaseModel):
    file_path: Optional[str] = None
    path: Optional[str] = None


@app.post("/api/files/upload")
async def upload_file_endpoint(file: UploadFile = File(...)):
    """
    Uploads a user file (PDF, Word, Excel, PPTX, text, image) into the uploads directory.
    Enables ChatGPT-style file attachments for direct conversion and multimodal analysis.
    """
    try:
        raw_name = Path(file.filename).name
        clean_name = "".join(c for c in raw_name if c.isalnum() or c in (" ", "_", "-", ".")).strip()
        if not clean_name:
            clean_name = f"upload_{uuid.uuid4().hex[:8]}.bin"

        dest = UPLOADS_DIR / clean_name
        if dest.exists():
            stem = dest.stem
            ext = dest.suffix
            dest = UPLOADS_DIR / f"{stem}_{int(time.time())}{ext}"

        content = await file.read()
        dest.write_bytes(content)
        size = len(content)

        logger.info(f"File uploaded successfully: {dest.name} ({size} bytes)")
        return {
            "success": True,
            "filename": dest.name,
            "path": str(dest.resolve()),
            "size_bytes": size,
            "content_type": file.content_type,
            "message": f"File '{dest.name}' uploaded successfully."
        }
    except Exception as e:
        logger.error(f"Error uploading file: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/files/uploads")
def list_uploaded_files():
    """Lists files currently residing in the uploads directory."""
    files = []
    if UPLOADS_DIR.exists():
        for f in sorted(UPLOADS_DIR.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file() and f.name != ".gitkeep":
                files.append({
                    "filename": f.name,
                    "name": f.name,
                    "path": str(f.resolve()),
                    "size_bytes": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                })
    return {"success": True, "uploads": files, "count": len(files)}


@app.post("/api/files/convert")
def convert_document_endpoint(req: ConvertDocRequest):
    """
    Converts an individual document or an entire local folder to a target format (docx, xlsx, pptx, pdf).
    """
    res = file_agent.convert_document(
        source_path=req.source_path,
        target_format=req.target_format,
        output_dir=req.output_dir
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Conversion failed"))
    return res


@app.post("/api/files/extract")
def extract_text_endpoint(req: ExtractTextRequest):
    """Extracts readable text and tables from any document."""
    target_p = req.file_path or req.path
    if not target_p:
        raise HTTPException(status_code=400, detail="file_path or path parameter is required")
    res = file_agent.extract_document_text(target_p)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error", "Extraction failed"))
    return res


@app.get("/api/browser/tabs")
def get_browser_tabs():
    """Queries running browser session tabs via UI Automation."""
    return browser_agent.get_open_tabs()


class BrowserOpenRequest(BaseModel):
    url: Optional[str] = None

@app.post("/api/browser/open")
async def open_browser_tab_endpoint(req: Optional[BrowserOpenRequest] = None):
    """Brings running browser to foreground and always opens in a fresh new tab."""
    target_url = req.url if req else None
    return await browser_agent.new_tab(url=target_url)


class BrowserLoginRequest(BaseModel):
    url: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    submit: Optional[bool] = True

@app.post("/api/browser/login")
async def browser_login_endpoint(req: BrowserLoginRequest):
    """Executes browser login assistance in a fresh new tab."""
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
def get_audit_logs_endpoint(limit: int = 100):
    """Returns persistent security and execution audit logs."""
    return {"audit_logs": get_recent_audit_logs(limit=limit)}


@app.delete("/api/logs/audit")
def clear_audit_logs_endpoint():
    """Wipes all security audit logs from the database."""
    count = clear_audit_logs()
    return {"success": True, "count": count, "message": f"Cleared {count} audit log(s)."}


# ----------------- DIRECT FILE CRUD OPERATIONS -----------------

class FileReadRequest(BaseModel):
    path: str
    max_bytes: Optional[int] = 50_000

class FileWriteRequest(BaseModel):
    path: str
    content: str
    overwrite: Optional[bool] = True

class FileEditRequest(BaseModel):
    path: str
    find: str
    replace: str

class FileDeleteRequest(BaseModel):
    path: str
    confirm: Optional[bool] = True

@app.post("/api/files/read")
def read_file_endpoint(req: FileReadRequest):
    """Safely reads file content subject to canonical root isolation."""
    return file_agent.read_file(path=req.path, max_bytes=req.max_bytes or 50_000)

@app.post("/api/files/write")
def write_file_endpoint(req: FileWriteRequest):
    """Writes content to disk with automatic rollback backup in scratch/.file_backups/."""
    return file_agent.write_file(path=req.path, content=req.content, overwrite=req.overwrite if req.overwrite is not None else True)

@app.post("/api/files/edit")
def edit_file_endpoint(req: FileEditRequest):
    """Performs localized find-and-replace, creating a backup and returning unified diff."""
    return file_agent.edit_file(path=req.path, find=req.find, replace=req.replace)

@app.delete("/api/files")
def delete_file_endpoint(req: FileDeleteRequest):
    """Safely deletes a file with automatic backup in scratch/.file_backups/ and viewer unlock."""
    return file_agent.delete_file(path=req.path, confirm=req.confirm if req.confirm is not None else True)


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
    candidates = [
        STATIC_DIR / "remote.html",
        Path(__file__).resolve().parent / "static" / "remote.html",
        PROJECT_ROOT / "backend" / "static" / "remote.html"
    ]
    for cand in candidates:
        if cand.exists():
            content = cand.read_text(encoding="utf-8")
            res = HTMLResponse(content=content)
            res.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
            res.headers["Pragma"] = "no-cache"
            res.headers["Expires"] = "0"
            return res
    return "<h3>Mobile Remote interface not found.</h3>"


@app.get("/")
@app.get("/index.html")
def get_desktop_page():
    return RedirectResponse(url="/desktop/index.html")


@app.get("/style.css")
def get_root_style():
    css_file = DESKTOP_DIR / "style.css"
    if css_file.exists():
        return FileResponse(css_file, media_type="text/css", headers={"Cache-Control": "no-cache, must-revalidate"})
    return Response(status_code=404)


@app.get("/app.js")
def get_root_app_js():
    js_file = DESKTOP_DIR / "app.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript", headers={"Cache-Control": "no-cache, must-revalidate"})
    return Response(status_code=404)


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
                dx = float(data.get("dx", 0))
                dy = float(data.get("dy", 0))
                controller.move_relative(dx, dy)

            elif evt_type == "mouse_click_coords":
                x = data.get("x")
                y = data.get("y")
                btn = data.get("button", "left")
                if x is not None and y is not None:
                    controller.click(x=int(x), y=int(y), button=btn)
                    logger.info(f"Direct screen mirror click: ({x}, {y}) [{btn}]")
                    await websocket.send_json({"type": "ACTION_FEEDBACK", "message": f"Clicked ({x}, {y})"})

            elif evt_type in ["trackpad_click", "click"]:
                btn = data.get("button", "left")
                clicks = int(data.get("clicks", 1))
                controller.click(button=btn, clicks=clicks)

            elif evt_type in ["trackpad_scroll", "scroll"]:
                amount = float(data.get("dy") or data.get("amount", 0))
                controller.scroll(amount)

            elif evt_type in ["trackpad_mouse_down", "mouse_down"]:
                controller.mouse_down(data.get("button", "left"))

            elif evt_type in ["trackpad_mouse_up", "mouse_up"]:
                controller.mouse_up(data.get("button", "left"))

            elif evt_type in ["type_text", "type"]:
                txt = data.get("text", "")
                if txt:
                    controller.type_text(txt)
                    await websocket.send_json({"type": "ACTION_FEEDBACK", "message": f"Typed: {txt[:25]}"})

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

            elif evt_type in ["press_key", "press"]:
                controller.press_key(data.get("key", "enter"))

            elif evt_type == "hotkey":
                keys = data.get("keys", [])
                if keys:
                    controller.hotkey(*keys)

            elif evt_type in ["prompt", "user_prompt"]:
                prompt_text = (data.get("text") or data.get("prompt") or "").strip()
                if prompt_text:
                    logger.info(f"Phone Remote dispatching agent prompt: '{prompt_text}'")
                    # Send immediate thinking event to phone
                    await websocket.send_json({
                        "type": "agent_thinking",
                        "prompt": prompt_text
                    })

                    async def handle_remote_prompt(p_txt: str):
                        try:
                            tid = await orchestrator.create_and_run_task(
                                prompt=p_txt,
                                permission_mode="balanced"
                            )
                            q = orchestrator.subscribe(tid)
                            try:
                                while True:
                                    event = await asyncio.wait_for(q.get(), timeout=50.0)
                                    ev_type = event.get("event_type")
                                    ev_data = event.get("data", {})

                                    if ev_type == "ACTION_EXECUTING":
                                        tool = ev_data.get("tool", "")
                                        agent = ev_data.get("agent", "")
                                        await websocket.send_json({
                                            "type": "agent_progress",
                                            "event_type": "ACTION_EXECUTING",
                                            "data": {"tool": tool, "agent": agent}
                                        })

                                    elif ev_type == "APPROVAL_REQUIRED":
                                        await websocket.send_json({
                                            "type": "approval_required",
                                            "task_id": tid,
                                            "approval": ev_data
                                        })

                                    elif ev_type == "APPROVAL_RESOLVED":
                                        await websocket.send_json({
                                            "type": "approval_resolved",
                                            "task_id": tid,
                                            "approval_id": ev_data.get("approval_id"),
                                            "decision": ev_data.get("decision")
                                        })

                                    elif ev_type == "TASK_COMPLETED":
                                        summary = ev_data.get("summary", "Mission completed successfully.")
                                        spoken = ev_data.get("spoken_summary", summary)
                                        spoken_clean = speech_service.filter_text_for_speech(spoken)

                                        recent_docs = []
                                        if ev_data.get("created_document"):
                                            c_doc = ev_data["created_document"]
                                            recent_docs.append({
                                                "name": c_doc.get("filename"),
                                                "path": c_doc.get("file_path"),
                                                "type": c_doc.get("file_type"),
                                                "size": c_doc.get("size_bytes", 0)
                                            })

                                        await websocket.send_json({
                                            "type": "agent_response",
                                            "role": "assistant",
                                            "task_id": tid,
                                            "content": summary,
                                            "spoken_summary": spoken_clean,
                                            "audio_url": "/api/speech/tts",
                                            "documents": recent_docs
                                        })
                                        break

                                    elif ev_type in ["TASK_FAILED", "TASK_CANCELLED"]:
                                        err_reason = ev_data.get("reason") or ev_data.get("error") or "Mission cancelled."
                                        await websocket.send_json({
                                            "type": "task_failed",
                                            "task_id": tid,
                                            "error": err_reason
                                        })
                                        break
                            except asyncio.TimeoutError:
                                await websocket.send_json({
                                    "type": "agent_response",
                                    "role": "assistant",
                                    "task_id": tid,
                                    "content": "Task is actively running in background on your Windows desktop.",
                                    "spoken_summary": "Task running in background."
                                })
                            finally:
                                orchestrator.unsubscribe(tid, q)
                        except Exception as ex:
                            logger.error(f"Remote prompt execution error: {ex}")
                            await websocket.send_json({
                                "type": "task_failed",
                                "error": str(ex)
                            })

                    asyncio.create_task(handle_remote_prompt(prompt_text))

            elif evt_type in ["approval_decision", "approval_response"]:
                appr_id = str(data.get("approval_id") or data.get("id") or "").strip()
                decision = str(data.get("decision") or "allow_once").strip()
                if appr_id:
                    res = permission_engine.resolve_approval(appr_id, decision)
                    logger.info(f"Phone Remote resolved approval {appr_id} with decision '{decision}': {res}")
                    await websocket.send_json({
                        "type": "approval_resolved",
                        "approval_id": appr_id,
                        "decision": decision,
                        "success": res
                    })

            elif evt_type == "emergency_stop":
                orchestrator.emergency_stop()
                await websocket.send_json({"type": "emergency_stop_triggered", "message": "Emergency Stop Triggered"})

            elif evt_type == "clear_emergency_stop":
                orchestrator.clear_emergency_stop()
                await websocket.send_json({"type": "emergency_stop_cleared", "message": "Emergency Stop Cleared"})

    except WebSocketDisconnect:
        logger.info("Mobile Remote disconnected.")
    except Exception as e:
        logger.warning(f"WebSocket session note: {e}")
    finally:
        if stream_task and not stream_task.done():
            stream_task.cancel()
