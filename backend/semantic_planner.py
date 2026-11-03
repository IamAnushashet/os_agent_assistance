"""
Semantic Planner for AI-Native Windows OS Assistant.
Translates arbitrary natural language commands into verified tool sequences from ToolRegistry.
Uses Google Gemini 2.0 Flash / Groq with structured JSON outputs and deterministic fallback.
"""

import json
import re
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

from tool_registry import tool_registry
from permission_engine import ActionCategory, RiskLevel
from llm_gateway import llm_gateway
from config import settings

logger = logging.getLogger("semantic_planner")
logger.setLevel(logging.INFO)


@dataclass
class PlanStep:
    step_number: int
    title: str
    agent: str
    tool_name: str
    params: Dict[str, Any]
    category: str
    risk_level: str
    reason: str
    expected_outcome: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_number": self.step_number,
            "title": self.title,
            "agent": self.agent,
            "tool_name": self.tool_name,
            "params": self.params,
            "category": self.category,
            "risk_level": self.risk_level,
            "reason": self.reason,
            "expected_outcome": self.expected_outcome
        }


@dataclass
class SemanticPlan:
    goal: str
    strategy: str
    steps: List[PlanStep]
    is_conversational: bool = False
    conversational_response: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "strategy": self.strategy,
            "is_conversational": self.is_conversational,
            "conversational_response": self.conversational_response,
            "steps": [s.to_dict() for s in self.steps]
        }


class SemanticPlanner:
    def __init__(self):
        pass

    def _is_greeting(self, text: str) -> Optional[str]:
        cleaned = text.strip().lower()
        if cleaned in ["hi", "hello", "hey", "good morning", "good evening", "who are you", "what can you do"]:
            return (
                "Hello! I am your AI-Native Autonomous Windows OS Assistant. "
                "I can operate your browser, manage local files, check CPU/RAM telemetry, launch desktop apps, "
                "and explain screen errors. You can also connect your phone over LAN to use it as a wireless trackpad. "
                "How can I help you today?"
            )
        return None

    def _rule_based_fallback(self, prompt: str) -> SemanticPlan:
        """Deterministic fallback planner when LLM API key is not configured or offline."""
        p_lower = prompt.lower()
        steps: List[PlanStep] = []

        # Case 0A: PowerPoint Presentation Generation
        is_pptx = bool(re.search(r"\b(ppt|pptx|powerpoint|presentation|slides|deck)\b", p_lower))
        if is_pptx:
            topic_match = re.search(r"(?:on|about|for|named|titled)\s+([a-zA-Z0-9_\s\-]+)", prompt, flags=re.IGNORECASE)
            if topic_match:
                topic = topic_match.group(1).strip()
            else:
                topic = re.sub(r"^(?:please\s+)?(?:create|make|generate|build)\s+(?:a\s+|an\s+)?(?:powerpoint|presentation|slides|pptx|ppt|deck)\s*(?:on|about|for|named|titled)?\s*", "", prompt, flags=re.IGNORECASE).strip() or "Executive Summary"
            
            clean_filename = f"{topic.replace(' ', '_')[:30]}_Presentation.pptx"
            tool = tool_registry.get("file_generate_presentation")
            steps.append(PlanStep(
                step_number=1,
                title=f"Generate PowerPoint Presentation: '{topic}'",
                agent=tool.agent,
                tool_name=tool.name,
                params={"topic": topic, "filename": clean_filename},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Create multi-slide widescreen presentation deck with structured cards and themes",
                expected_outcome=f"Presentation '{clean_filename}' generated on disk"
            ))
            return SemanticPlan(goal=f"Create presentation on {topic}", strategy="Document Generation", steps=steps)

        # Case 0B: Microsoft Word Document Generation
        is_docx = bool(re.search(r"\b(docx|word|word doc|word document)\b", p_lower))
        if is_docx:
            topic_match = re.search(r"(?:on|about|for|named|titled)\s+([a-zA-Z0-9_\s\-]+)", prompt, flags=re.IGNORECASE)
            if topic_match:
                topic = topic_match.group(1).strip()
            else:
                topic = re.sub(r"^(?:please\s+)?(?:create|make|generate|build)\s+(?:a\s+|an\s+)?(?:docx|word document|word doc|word file|doc)\s*(?:on|about|for|named|titled)?\s*", "", prompt, flags=re.IGNORECASE).strip() or "Executive Summary"
            
            clean_filename = f"{topic.replace(' ', '_')[:30]}_Document.docx"
            tool = tool_registry.get("file_generate_docx")
            steps.append(PlanStep(
                step_number=1,
                title=f"Generate Word Document: '{topic}'",
                agent=tool.agent,
                tool_name=tool.name,
                params={"topic": topic, "filename": clean_filename},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Generate styled Microsoft Word document with executive summary and structured tables",
                expected_outcome=f"Word document '{clean_filename}' created on disk"
            ))
            return SemanticPlan(goal=f"Create Word document on {topic}", strategy="Document Generation", steps=steps)

        # Case 0C: Microsoft Excel Spreadsheet Generation
        is_xlsx = bool(re.search(r"\b(xlsx|excel|sheet|spreadsheet|workbook)\b", p_lower))
        if is_xlsx:
            topic_match = re.search(r"(?:on|about|for|named|titled)\s+([a-zA-Z0-9_\s\-]+)", prompt, flags=re.IGNORECASE)
            if topic_match:
                topic = topic_match.group(1).strip()
            else:
                topic = re.sub(r"^(?:please\s+)?(?:create|make|generate|build)\s+(?:a\s+|an\s+)?(?:xlsx|excel sheet|excel spreadsheet|sheet|spreadsheet|workbook)\s*(?:on|about|for|named|titled)?\s*", "", prompt, flags=re.IGNORECASE).strip() or "Financial and KPI Model"
            
            clean_filename = f"{topic.replace(' ', '_')[:30]}_Spreadsheet.xlsx"
            tool = tool_registry.get("file_generate_xlsx")
            steps.append(PlanStep(
                step_number=1,
                title=f"Generate Excel Spreadsheet: '{topic}'",
                agent=tool.agent,
                tool_name=tool.name,
                params={"topic": topic, "filename": clean_filename},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Generate professional multi-sheet Excel workbook with formatted KPI tables and formulas",
                expected_outcome=f"Excel workbook '{clean_filename}' created on disk"
            ))
            return SemanticPlan(goal=f"Create Excel spreadsheet on {topic}", strategy="Document Generation", steps=steps)

        # Case 0D: PDF Document / Report Generation
        is_pdf = bool(re.search(r"\b(pdf|report|docuement|document|dossier)\b", p_lower))
        if is_pdf:
            title_match = re.search(r"(?:on|about|for|named|titled)\s+([a-zA-Z0-9_\s\-]+)", prompt, flags=re.IGNORECASE)
            if title_match:
                doc_title = title_match.group(1).strip()
            else:
                doc_title = re.sub(r"^(?:please\s+)?(?:create|make|generate|build)\s+(?:a\s+|an\s+)?(?:pdf|report|document|docuement)\s*(?:on|about|for|named|titled)?\s*", "", prompt, flags=re.IGNORECASE).strip() or "Operational Report"
            
            clean_filename = f"{doc_title.replace(' ', '_')[:30]}_Report.pdf"
            tool = tool_registry.get("file_generate_pdf")
            steps.append(PlanStep(
                step_number=1,
                title=f"Generate Executive PDF Report: '{doc_title}'",
                agent=tool.agent,
                tool_name=tool.name,
                params={"title": doc_title, "filename": clean_filename},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Generate publication-grade PDF report with executive summary and structured benchmarks",
                expected_outcome=f"PDF report '{clean_filename}' created on disk"
            ))
            return SemanticPlan(goal=f"Generate PDF report on {doc_title}", strategy="Document Generation", steps=steps)

        # Case 0E: File Edit / Modification
        if any(w in p_lower for w in ["modify", "edit", "replace", "update"]) and "file" in p_lower:
            file_match = re.search(r"(?:file|in)\s+([a-zA-Z0-9_.\-\\\/]+)", prompt, flags=re.IGNORECASE)
            target_path = file_match.group(1).strip() if file_match else "notes.txt"
            tool = tool_registry.get("file_edit")
            steps.append(PlanStep(
                step_number=1,
                title=f"Modify file '{target_path}'",
                agent=tool.agent,
                tool_name=tool.name,
                params={"path": target_path, "find": "TODO", "replace": "DONE"},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Apply localized modifications with rollback backup",
                expected_outcome="File modified safely with unified diff preview"
            ))
            return SemanticPlan(goal=f"Modify file {target_path}", strategy="Safe File Editing", steps=steps)

        # Case 0F: File Deletion with Explicit Permission
        if any(w in p_lower for w in ["delete", "remove", "erase", "unlink"]) and ("file" in p_lower or any(p_lower.endswith(ext) for ext in [".txt", ".pdf", ".pptx", ".docx", ".xlsx", ".json", ".log"])):
            file_match = re.search(r"(?:file|named)\s+([a-zA-Z0-9_.\-\\\/]+)", prompt, flags=re.IGNORECASE)
            if file_match:
                target_path = file_match.group(1).strip()
            else:
                target_path = re.sub(r"^(?:please\s+)?(?:delete|remove|erase|unlink)\s+(?:the\s+)?(?:file\s+)?", "", prompt, flags=re.IGNORECASE).strip()
            tool = tool_registry.get("file_delete")
            steps.append(PlanStep(
                step_number=1,
                title=f"Safely delete file '{target_path}'",
                agent=tool.agent,
                tool_name=tool.name,
                params={"path": target_path, "confirm": True},
                category=tool.category,
                risk_level=tool.risk_level,
                reason=f"Safely delete file '{target_path}' after creating rollback backup in scratch/.file_backups/",
                expected_outcome=f"File '{target_path}' safely deleted"
            ))
            return SemanticPlan(goal=f"Delete file {target_path}", strategy="Filesystem Modification", steps=steps)

        # Case 0G: File Read
        if any(w in p_lower for w in ["read", "view", "inspect", "show"]) and "file" in p_lower:
            file_match = re.search(r"(?:file|at)\s+([a-zA-Z0-9_.\-\\\/]+)", prompt, flags=re.IGNORECASE)
            target_path = file_match.group(1).strip() if file_match else "README.md"
            tool = tool_registry.get("file_read")
            steps.append(PlanStep(
                step_number=1,
                title=f"Read file '{target_path}'",
                agent=tool.agent,
                tool_name=tool.name,
                params={"path": target_path},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Read file content safely within authorized boundaries",
                expected_outcome="File content returned"
            ))
            return SemanticPlan(goal=f"Read file {target_path}", strategy="File Inspection", steps=steps)

        # Case 0H: Browser Login & Credentials
        if any(k in p_lower for k in ["login", "log in", "sign in", "credentials", "authenticate"]):
            tool = tool_registry.get("browser_login")
            steps.append(PlanStep(
                step_number=1,
                title="Assist with browser login and credentials",
                agent=tool.agent,
                tool_name=tool.name,
                params={"submit": True},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Focus browser form and submit credentials with password masking",
                expected_outcome="Credentials submitted to active browser login form"
            ))
            return SemanticPlan(goal="Browser Login Assistance", strategy="Browser Automation", steps=steps)

        # Case 1A: Direct URL Navigation
        if re.search(r"^(?:https?:\/\/|[a-zA-Z0-9\-]+\.(?:com|org|net|edu|gov|io|ai|dev|co))", p_lower) or any(d in p_lower for d in ["youtube.com", "google.com", "github.com", "reddit.com", "wikipedia.org"]):
            url_match = re.search(r"(?:https?:\/\/[^\s]+|[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:\/[^\s]*)?)", prompt)
            target_url = url_match.group(0) if url_match else prompt.strip()
            tool = tool_registry.get("browser_navigate")
            steps.append(PlanStep(
                step_number=1,
                title=f"Navigate browser to '{target_url}'",
                agent=tool.agent,
                tool_name=tool.name,
                params={"url": target_url},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Direct navigation to web address",
                expected_outcome="Target web page loaded in browser"
            ))
            return SemanticPlan(goal=f"Navigate to {target_url}", strategy="Browser Automation", steps=steps)

        # Case 1B: Focus / Open Browser in New Tab (Checked BEFORE search so 'open browser' isn't misidentified as search)
        if any(k in p_lower for k in ["open", "launch", "focus"]) and any(b in p_lower for b in ["browser", "chrome", "edge", "brave", "new tab", "tab"]):
            tool = tool_registry.get("browser_new_tab")
            steps.append(PlanStep(
                step_number=1,
                title="Open fresh browser tab",
                agent=tool.agent,
                tool_name=tool.name,
                params={},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Focus running browser and open a fresh new tab (Ctrl+T) to preserve existing session",
                expected_outcome="New browser tab opened"
            ))
            return SemanticPlan(goal="Open browser in new tab", strategy="Browser Automation", steps=steps)

        # Case 1C: Browser Search or Web Application Query (in new tab)
        is_search = bool(re.search(r"\b(search|google|look\s*up|lookup|find\s+on\s+web)\b", p_lower)) or "browse for" in p_lower or "web app" in p_lower or "web application" in p_lower
        if is_search:
            clean_query = re.sub(r"^(?:please\s+)?(?:search(?:\s+for|\s+in\s+web\s+application|\s+on\s+web|\s+the\s+web)?|google|look\s*up|lookup|find\s+on\s+web|browse\s+for)\s*", "", prompt, flags=re.IGNORECASE).strip()
            clean_query = re.sub(r"\s*(?:in\s+(?:web\s+application|web\s+app|browser|google)|on\s+(?:google|web|the\s+web))\s*$", "", clean_query, flags=re.IGNORECASE).strip()
            if not clean_query:
                clean_query = prompt.strip()

            tool = tool_registry.get("browser_search")
            steps.append(PlanStep(
                step_number=1,
                title=f"Search web application for '{clean_query}' in new tab",
                agent=tool.agent,
                tool_name=tool.name,
                params={"query": clean_query},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Execute web search and display results in fresh browser tab",
                expected_outcome=f"Search results for '{clean_query}' displayed in new browser tab"
            ))
            return SemanticPlan(goal=f"Web search for {clean_query}", strategy="Browser Automation", steps=steps)

        # Case 2: Browser tabs
        if any(k in p_lower for k in ["list tabs", "open tabs", "show tabs"]):
            tool = tool_registry.get("browser_list_tabs")
            steps.append(PlanStep(
                step_number=1,
                title="Enumerate running browser tabs",
                agent=tool.agent,
                tool_name=tool.name,
                params={},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Inspect active Chrome/Edge tabs via UI Automation",
                expected_outcome="Tab list returned"
            ))
            return SemanticPlan(goal="List browser tabs", strategy="Browser Automation", steps=steps)

        # Case 3: Telemetry & diagnostics
        if any(k in p_lower for k in ["telemetry", "cpu", "ram", "memory", "battery", "system check", "specs"]):
            tool = tool_registry.get("system_telemetry")
            steps.append(PlanStep(
                step_number=1,
                title="Read real-time hardware telemetry",
                agent=tool.agent,
                tool_name=tool.name,
                params={},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Gather CPU, RAM, disk, and battery statistics",
                expected_outcome="Hardware metrics returned"
            ))
            return SemanticPlan(goal="System Telemetry Check", strategy="System Introspection", steps=steps)

        # Case 4: Launch application / browser open in new tab
        if any(k in p_lower for k in ["open", "launch", "focus"]):
            # Check if this is a browser open or focus request:
            if any(b in p_lower for b in ["browser", "chrome", "edge", "brave", "new tab", "web tab"]):
                tool = tool_registry.get("browser_new_tab")
                steps.append(PlanStep(
                    step_number=1,
                    title="Open fresh browser tab",
                    agent=tool.agent,
                    tool_name=tool.name,
                    params={},
                    category=tool.category,
                    risk_level=tool.risk_level,
                    reason="Focus running browser and open a fresh new tab (Ctrl+T) to preserve existing session",
                    expected_outcome="New browser tab opened"
                ))
                return SemanticPlan(goal="Open browser in new tab", strategy="Browser Automation", steps=steps)

            match = re.search(r"(?:open|launch)\s+([a-zA-Z0-9_\s]+)", p_lower)
            app = match.group(1).strip() if match else "notepad"
            tool = tool_registry.get("system_launch_app")
            steps.append(PlanStep(
                step_number=1,
                title=f"Launch application '{app}'",
                agent=tool.agent,
                tool_name=tool.name,
                params={"app_name": app},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Start approved desktop application",
                expected_outcome="Application window opened"
            ))
            return SemanticPlan(goal=f"Launch {app}", strategy="Application Execution", steps=steps)

        # Case 5: Vision analyze screen
        if any(k in p_lower for k in ["screen", "what is on my screen", "explain error", "look at my screen"]):
            tool = tool_registry.get("vision_analyze_screen")
            steps.append(PlanStep(
                step_number=1,
                title="Analyze active desktop screen",
                agent=tool.agent,
                tool_name=tool.name,
                params={"prompt": prompt},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Inspect screen state and open windows",
                expected_outcome="Multimodal visual summary generated"
            ))
            return SemanticPlan(goal="Analyze Desktop Screen", strategy="Visual Reasoning", steps=steps)

        # Case 6: File search
        tool = tool_registry.get("file_search")
        steps.append(PlanStep(
            step_number=1,
            title=f"Search files for '{prompt}'",
            agent=tool.agent,
            tool_name=tool.name,
            params={"query": prompt},
            category=tool.category,
            risk_level=tool.risk_level,
            reason="Search authorized workspace",
            expected_outcome="Matching files found"
        ))
        return SemanticPlan(goal=f"File Search: {prompt}", strategy="Filesystem Inspection", steps=steps)

    async def formulate_plan(self, prompt: str, chat_history: Optional[List[Dict[str, Any]]] = None) -> SemanticPlan:
        # Check conversational greeting
        greet = self._is_greeting(prompt)
        if greet:
            return SemanticPlan(
                goal="Casual Greeting",
                strategy="Direct conversational reply",
                steps=[],
                is_conversational=True,
                conversational_response=greet
            )

        has_api_key = bool(settings.effective_api_key)

        # 1. Primary: Use Google Gemini / LLM Gateway when API key is configured
        if has_api_key:
            logger.info(f"Gemini AI Gateway ({settings.LLM_MODEL}) formulating dynamic plan for: '{prompt}'")
            tool_catalog = []
            for t in tool_registry.list_tools():
                tool_catalog.append({
                    "name": t.name,
                    "agent": t.agent,
                    "description": t.description,
                    "parameters": t.parameters
                })

            system_prompt = (
                "You are the Central Task Planner and Intelligent Assistant for an AI-Native Windows OS Assistant.\n"
                "You have access to specialized local agents: Browser Agent, File Agent, System Agent, Vision Agent.\n\n"
                f"AVAILABLE OS TOOLS:\n{json.dumps(tool_catalog, indent=2)}\n\n"
                "RULES:\n"
                "1. If the user request requires taking actions on Windows (creating PowerPoint, Word, Excel, or PDF documents; "
                "operating the browser/searching tabs; reading/editing/deleting files; checking system telemetry; inspecting the screen):\n"
                "   Output valid JSON matching this schema:\n"
                "   {\n"
                '     "goal": "<concise summary of objective>",\n'
                '     "strategy": "<1-sentence execution strategy>",\n'
                '     "is_conversational": false,\n'
                '     "steps": [\n'
                '       {\n'
                '         "step_number": 1,\n'
                '         "title": "<short title>",\n'
                '         "agent": "<Agent Name>",\n'
                '         "tool_name": "<exact_tool_name from catalog>",\n'
                '         "params": { ... },\n'
                '         "reason": "<why this step is required>",\n'
                '         "expected_outcome": "<verifiable outcome>"\n'
                '       }\n'
                '     ]\n'
                "   }\n"
                "2. If the user asks a general question, explanation, coding help, or greeting (no Windows OS actions needed):\n"
                "   Output valid JSON matching this schema:\n"
                "   {\n"
                '     "goal": "<user topic>",\n'
                '     "strategy": "Conversational Response",\n'
                '     "is_conversational": true,\n'
                '     "conversational_response": "<detailed, helpful, well-formatted markdown response>",\n'
                '     "steps": []\n'
                "   }\n"
                "3. Never invent tool names not in the catalog. Keep plans concise (1 to 5 steps maximum).\n"
                "4. Output JSON ONLY.\n"
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"User request: {prompt}"}
            ]

            try:
                res = await llm_gateway.chat_complete(messages=messages, json_mode=True, temperature=0.1)
                if res.get("success") and res.get("content"):
                    raw_text = res["content"].strip()
                    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(0))

                        # Handle Conversational Response
                        if data.get("is_conversational") and data.get("conversational_response"):
                            logger.info(f"Gemini AI provided conversational answer for: '{prompt}'")
                            return SemanticPlan(
                                goal=data.get("goal") or data.get("task_summary") or prompt,
                                strategy="Direct conversational reply",
                                steps=[],
                                is_conversational=True,
                                conversational_response=data.get("conversational_response")
                            )

                        # Handle Tool Action Steps
                        raw_steps = data.get("steps") or data.get("plan") or []
                        valid_steps: List[PlanStep] = []
                        for idx, s in enumerate(raw_steps):
                            if isinstance(s, dict):
                                tname = s.get("tool_name", "")
                                tool = tool_registry.get(tname)
                                if tool:
                                    params = s.get("params") or s.get("parameters") or {}
                                    valid_steps.append(PlanStep(
                                        step_number=idx + 1,
                                        title=s.get("title") or f"Execute {tname}",
                                        agent=tool.agent,
                                        tool_name=tool.name,
                                        params=params,
                                        category=tool.category,
                                        risk_level=tool.risk_level,
                                        reason=s.get("reason", f"Execute {tname}"),
                                        expected_outcome=s.get("expected_outcome", tool.completion_criterion)
                                    ))

                        if valid_steps:
                            logger.info(f"Gemini AI generated valid plan with {len(valid_steps)} steps for: '{prompt}'")
                            return SemanticPlan(
                                goal=data.get("goal") or data.get("task_description") or prompt,
                                strategy=data.get("strategy") or "Automated Execution",
                                steps=valid_steps
                            )
            except Exception as e:
                logger.warning(f"Error during Gemini LLM planning: {e}. Falling back to deterministic planner.")

        # 2. Fallback to deterministic rule-based planner (offline or if LLM fails)
        logger.info(f"Using rule-based planner fallback for prompt: '{prompt}'")
        return self._rule_based_fallback(prompt)


semantic_planner = SemanticPlanner()
