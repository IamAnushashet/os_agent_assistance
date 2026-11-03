"""
File Agent for AI-Native Windows OS Assistant.
Operates on real files subject to canonical path containment,
automatic rolling backups in scratch/.file_backups/, and unified diff previews.
"""

import os
import difflib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import BACKUPS_DIR, PROJECT_ROOT
from document_generator import doc_generator

logger = logging.getLogger("file_agent")
logger.setLevel(logging.INFO)


class FileAgent:
    def __init__(self, default_root: Optional[str] = None):
        self.default_root = Path(default_root or PROJECT_ROOT).resolve()
        self.last_search_results: List[Dict[str, Any]] = []

    def _resolve_safe_path(self, target: str, workspace_root: Optional[str] = None) -> Path:
        """Resolves canonical path and prevents directory traversal outside authorized bounds."""
        base = Path(workspace_root or self.default_root).resolve()
        candidate = Path(target)
        if not candidate.is_absolute():
            resolved = (base / candidate).resolve()
        else:
            resolved = candidate.resolve()

        # Prevent operating on critical Windows directories
        sys_str = str(resolved).lower()
        blocked_dirs = ["c:\\windows\\system32", "c:\\windows\\syswow64", "c:\\boot"]
        for b in blocked_dirs:
            if sys_str.startswith(b):
                raise PermissionError(f"Access to critical Windows system path '{resolved}' is strictly blocked.")

        return resolved

    def _create_backup(self, file_path: Path) -> Optional[Path]:
        """Creates a timestamped rollback backup in scratch/.file_backups/."""
        if not file_path.exists() or not file_path.is_file():
            return None
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{ts}_{file_path.name}"
            backup_file = BACKUPS_DIR / backup_name
            backup_file.write_bytes(file_path.read_bytes())
            logger.info(f"Created rollback backup: {backup_file}")
            return backup_file
        except Exception as e:
            logger.warning(f"Could not create backup for {file_path}: {e}")
            return None

    def search_files(self, query: str, search_dir: Optional[str] = None, max_results: int = 15) -> Dict[str, Any]:
        """Searches files by name or content match."""
        root = self._resolve_safe_path(search_dir or str(self.default_root))
        matches = []
        q_lower = query.lower()

        try:
            for r, dirs, files in os.walk(str(root)):
                # Skip heavy build/git directories
                dirs[:] = [d for d in dirs if d not in [".git", "venv", "__pycache__", "node_modules", ".file_backups"]]
                for f in files:
                    fp = Path(r) / f
                    if q_lower in f.lower():
                        matches.append({"name": f, "path": str(fp), "size": fp.stat().st_size})
                    elif len(matches) < max_results:
                        try:
                            if fp.stat().st_size < 1_000_000:
                                text = fp.read_text(encoding="utf-8", errors="ignore")
                                if q_lower in text.lower():
                                    matches.append({"name": f, "path": str(fp), "size": fp.stat().st_size, "content_match": True})
                        except Exception:
                            pass
                    if len(matches) >= max_results:
                        break
                if len(matches) >= max_results:
                    break

            self.last_search_results = matches
            return {"success": True, "query": query, "total_found": len(matches), "files": matches}
        except Exception as e:
            return {"success": False, "error": str(e), "files": []}

    def read_file(self, path: str, max_bytes: int = 50_000) -> Dict[str, Any]:
        try:
            p = self._resolve_safe_path(path)
            if not p.exists():
                return {"success": False, "error": f"File does not exist: {path}"}
            if not p.is_file():
                return {"success": False, "error": f"Path is not a file: {path}"}

            content = p.read_text(encoding="utf-8", errors="replace")
            truncated = len(content) > max_bytes
            return {
                "success": True,
                "path": str(p),
                "content": content[:max_bytes],
                "truncated": truncated,
                "total_chars": len(content)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, path: str, content: str, overwrite: bool = True) -> Dict[str, Any]:
        try:
            p = self._resolve_safe_path(path)
            if p.exists() and not overwrite:
                return {"success": False, "error": f"File '{path}' already exists and overwrite=False."}

            if p.exists():
                self._create_backup(p)

            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return {
                "success": True,
                "path": str(p),
                "bytes_written": len(content.encode("utf-8")),
                "message": f"Successfully written to {p.name}"
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def edit_file(self, path: str, find: str, replace: str) -> Dict[str, Any]:
        """Performs localized find-and-replace, creating a backup and returning unified diff."""
        try:
            p = self._resolve_safe_path(path)
            if not p.exists():
                return {"success": False, "error": f"File does not exist: {path}"}

            original = p.read_text(encoding="utf-8", errors="replace")
            if find not in original:
                return {"success": False, "error": f"Target substring not found in '{p.name}'."}

            backup = self._create_backup(p)
            updated = original.replace(find, replace, 1)
            p.write_text(updated, encoding="utf-8")

            diff = "".join(difflib.unified_diff(
                original.splitlines(keepends=True),
                updated.splitlines(keepends=True),
                fromfile=f"a/{p.name}",
                tofile=f"b/{p.name}"
            ))

            return {
                "success": True,
                "path": str(p),
                "backup_path": str(backup) if backup else None,
                "diff": diff,
                "message": f"Updated '{p.name}' with 1 modification."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def delete_file(self, path: str, confirm: bool = False) -> Dict[str, Any]:
        """Deletes file with safety backup; requires confirm=True."""
        if not confirm:
            return {"success": False, "error": "Deletion refused: confirm=True is required for file deletion."}
        try:
            import time
            import psutil
            p = self._resolve_safe_path(path)
            if not p.exists():
                return {"success": False, "error": f"File does not exist: {path}"}
            backup = self._create_backup(p)
            try:
                p.unlink()
            except PermissionError:
                # File is locked by an open application; gracefully close viewers to release lock
                for proc in psutil.process_iter(['name']):
                    pname = (proc.info.get('name') or '').lower()
                    if any(v in pname for v in ['powerpnt', 'acrord', 'acrobat', 'winword', 'excel', 'notepad']):
                        try:
                            proc.terminate()
                            proc.wait(timeout=1.0)
                        except Exception:
                            pass
                time.sleep(0.3)
                p.unlink()
            return {
                "success": True,
                "path": str(p),
                "backup_path": str(backup) if backup else None,
                "message": f"Safely deleted '{p.name}' (backup retained in scratch/)."
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def open_file(self, path: str) -> Dict[str, Any]:
        """Opens file in default Windows desktop application."""
        try:
            # Handle ordinal references (e.g. "the second one")
            if "second" in path.lower() and len(self.last_search_results) >= 2:
                p = Path(self.last_search_results[1]["path"])
            elif "first" in path.lower() and len(self.last_search_results) >= 1:
                p = Path(self.last_search_results[0]["path"])
            else:
                p = self._resolve_safe_path(path)

            if not p.exists():
                return {"success": False, "error": f"Path not found: {path}"}

            os.startfile(str(p))
            return {"success": True, "path": str(p), "message": f"Opened '{p.name}' in default Windows application."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_dir(self, path: Optional[str] = None) -> Dict[str, Any]:
        try:
            p = self._resolve_safe_path(path or str(self.default_root))
            if not p.exists() or not p.is_dir():
                return {"success": False, "error": f"Not a valid directory: {path}"}

            entries = []
            for item in p.iterdir():
                entries.append({
                    "name": item.name,
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else None
                })
            return {"success": True, "path": str(p), "entries": entries}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def generate_presentation(
        self,
        topic: str,
        filename: Optional[str] = None,
        slides_data: Optional[List[Dict[str, Any]]] = None,
        theme: str = "cyber_sapphire",
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates a professional PowerPoint presentation with structured multi-slide content."""
        try:
            return doc_generator.create_presentation(topic, filename, slides_data, theme, task_id=task_id)
        except Exception as e:
            logger.error(f"Failed to generate presentation: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def generate_pdf(
        self,
        title: str,
        filename: Optional[str] = None,
        sections: Optional[List[Dict[str, Any]]] = None,
        executive_summary: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates a publication-grade PDF report with executive summary and structured data."""
        try:
            return doc_generator.create_pdf_report(title, filename, sections, executive_summary, task_id=task_id)
        except Exception as e:
            logger.error(f"Failed to generate PDF: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def generate_word_document(
        self,
        topic: str,
        filename: Optional[str] = None,
        sections: Optional[List[Dict[str, Any]]] = None,
        theme: str = "enterprise",
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates a publication-grade Word document (.docx) with structured content and tables."""
        try:
            return doc_generator.create_word_document(topic, filename, sections, theme, task_id=task_id)
        except Exception as e:
            logger.error(f"Failed to generate Word document: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def generate_excel_spreadsheet(
        self,
        topic: str,
        filename: Optional[str] = None,
        sheets_data: Optional[List[Dict[str, Any]]] = None,
        theme: str = "modern_blue",
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generates a professional Excel workbook (.xlsx) with styled sheets and KPI formula data."""
        try:
            return doc_generator.create_excel_spreadsheet(topic, filename, sheets_data, theme, task_id=task_id)
        except Exception as e:
            logger.error(f"Failed to generate Excel spreadsheet: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def convert_document(
        self,
        source_path: str,
        target_format: str,
        output_dir: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Converts an individual document (PDF, Word, Excel, PPTX, Text) or an entire local
        folder of documents to a specified target format (docx, xlsx, pptx, pdf).
        """
        try:
            out_p = Path(output_dir).resolve() if output_dir else None
            return doc_generator.convert_batch(source_path, target_format, out_p, task_id=task_id)
        except Exception as e:
            logger.error(f"Failed to convert document(s): {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def extract_document_text(self, file_path: str) -> Dict[str, Any]:
        """Extracts readable text and tables from any PDF, Word, Excel, CSV, or Text file."""
        try:
            return doc_generator.extract_text(file_path)
        except Exception as e:
            logger.error(f"Failed to extract document text: {e}", exc_info=True)
            return {"success": False, "error": str(e)}


file_agent = FileAgent()
