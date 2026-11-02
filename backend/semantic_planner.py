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
            # Extract topic: e.g. "create powerpoint on pes" -> "pes", "generate presentation about AI" -> "AI"
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

        # Case 0B: PDF Document / Report Generation
        is_pdf = bool(re.search(r"\b(pdf|report|doc|document|docuement|dossier)\b", p_lower))
        if is_pdf:
            title_match = re.search(r"(?:on|about|for|named|titled)\s+([a-zA-Z0-9_\s\-]+)", prompt, flags=re.IGNORECASE)
            if title_match:
                doc_title = title_match.group(1).strip()
            else:
                doc_title = re.sub(r"^(?:please\s+)?(?:create|make|generate|build)\s+(?:a\s+|an\s+)?(?:pdf|report|document|docuement|doc)\s*(?:on|about|for|named|titled)?\s*", "", prompt, flags=re.IGNORECASE).strip() or "Operational Report"
            
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

        # Case 0C: Browser Login & Credentials
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

        # Case 1B: Browser Search or Web Application Query
        if any(k in p_lower for k in ["search", "google", "look up", "lookup", "web application", "web app", "find on web", "browse"]):
            clean_query = re.sub(r"^(?:please\s+)?(?:search(?:\s+for|\s+in\s+web\s+application|\s+on\s+web|\s+the\s+web)?|google|look\s*up|lookup|find\s+on\s+web|browse(?:\s+for)?)\s*", "", prompt, flags=re.IGNORECASE).strip()
            clean_query = re.sub(r"\s*(?:in\s+(?:web\s+application|web\s+app|browser|google)|on\s+(?:google|web|the\s+web))\s*$", "", clean_query, flags=re.IGNORECASE).strip()
            if not clean_query:
                clean_query = prompt.strip()

            tool = tool_registry.get("browser_search")
            steps.append(PlanStep(
                step_number=1,
                title=f"Search web application for '{clean_query}'",
                agent=tool.agent,
                tool_name=tool.name,
                params={"query": clean_query},
                category=tool.category,
                risk_level=tool.risk_level,
                reason="Execute web search and display results in active browser",
                expected_outcome=f"Search results for '{clean_query}' displayed in web application"
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

        # Case 4: Launch application
        if any(k in p_lower for k in ["open", "launch"]):
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

        # Catalog registered tools for the LLM
        tool_catalog = []
        for t in tool_registry.list_tools():
            tool_catalog.append({
                "name": t.name,
                "agent": t.agent,
                "description": t.description,
                "parameters": t.parameters
            })

        system_prompt = (
            "You are the Central Task Planner for an AI-Native Windows OS Assistant.\n"
            "Your job is to translate the user's objective into a structured, step-by-step plan "
            "using ONLY the tools available in the catalog.\n\n"
            f"TOOL CATALOG:\n{json.dumps(tool_catalog, indent=2)}\n\n"
            "RULES:\n"
            "1. Output ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "goal": "<concise goal>",\n'
            '  "strategy": "<1 sentence strategy>",\n'
            '  "steps": [\n'
            '    {\n'
            '      "step_number": 1,\n'
            '      "title": "<short title>",\n'
            '      "agent": "<Agent Name>",\n'
            '      "tool_name": "<exact_tool_name>",\n'
            '      "params": { ... },\n'
            '      "reason": "<why this step is required>",\n'
            '      "expected_outcome": "<verifiable outcome>"\n'
            '    }\n'
            '  ]\n'
            "}\n"
            "2. Never make up tool names not in the catalog.\n"
            "3. Keep plans concise (1 to 5 steps maximum).\n"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"User request: {prompt}"}
        ]

        res = await llm_gateway.chat_complete(messages=messages, json_mode=True, temperature=0.1)
        if res.get("success") and res.get("content"):
            try:
                raw_text = res["content"].strip()
                match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    valid_steps: List[PlanStep] = []
                    for idx, s in enumerate(data.get("steps", [])):
                        tname = s.get("tool_name", "")
                        tool = tool_registry.get(tname)
                        if tool:
                            valid_steps.append(PlanStep(
                                step_number=idx + 1,
                                title=s.get("title") or f"Execute {tname}",
                                agent=tool.agent,
                                tool_name=tool.name,
                                params=s.get("params", {}),
                                category=tool.category,
                                risk_level=tool.risk_level,
                                reason=s.get("reason", f"Execute {tname}"),
                                expected_outcome=s.get("expected_outcome", tool.completion_criterion)
                            ))
                    if valid_steps:
                        return SemanticPlan(
                            goal=data.get("goal") or prompt,
                            strategy=data.get("strategy") or "Automated Execution",
                            steps=valid_steps
                        )
            except Exception as e:
                logger.warning(f"Error parsing LLM plan: {e}")

        # Fallback to deterministic plan
        return self._rule_based_fallback(prompt)


semantic_planner = SemanticPlanner()
