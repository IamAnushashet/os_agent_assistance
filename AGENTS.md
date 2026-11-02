# AGENTS.md — Autonomous Multi-Agent Windows OS Assistant

## 1. Mission and Source of Truth
This repository builds a general-purpose, multimodal AI agent that operates the user's actual Windows computer. It is not primarily a coding agent, terminal chatbot, or UI mockup.

The user interacts through a desktop UI or a phone connected over the local network (LAN). The assistant accepts typed or spoken instructions, understands the user's intent and (when relevant) the current screen, chooses the appropriate specialized agent, performs authorized actions on the real machine, verifies outcomes, and reports what happened.

## 2. Non-Negotiable Product Requirements
- **Four specialized agents coordinated by one central orchestrator**:
  1. Browser Agent
  2. File Agent
  3. System Agent
  4. Vision Agent
- **Control the user's existing browser and actual Windows desktop**:
  - Browser automation must **not use Playwright** and must not depend on launching a separate automation browser.
  - Operates the user's already-running Chrome, Edge, or Brave session.
- **Dual targeting**: Semantic / accessibility-based UI targeting (UI Automation) combined with screenshot-based visual targeting.
- **Real file operations**: Modifies real files subject to explicit default-deny permission policies with automatic backups and diff previews.
- **Vision Agent**: Understands the current desktop screen, explains visible errors, and locates on-screen controls.
- **STT and TTS**: First-class speech-to-text (Whisper/Web Speech) and neural text-to-speech (Edge-TTS).
- **Phone Remote over LAN**: Shares the same backend, tasks, permissions, and context. Features live screen mirror, tactile mini trackpad, push-to-talk mic, and emergency stop.
- **Model Engine**: Powered by Google Gemini 2.0 Flash / Groq (Zero-Setup Free Cloud API) with full provider independence.
- **Security**: Default-deny security enforcement belongs in trusted local code, not in LLM instructions.
- **Honest Execution**: No fake progress, mock completion, or fabricated tool execution.

## 3. Architecture Overview
- **Presentation Layer**: Desktop UI (Dark-first layout with live step cards and PiP) + Mobile Remote PWA (LAN pairing, trackpad, screen mirror).
- **API & Real-time Layer**: FastAPI REST endpoints + Server-Sent Events (SSE) / WebSockets for live agent execution streams and remote input.
- **Orchestration Layer**: Central MultiAgentOrchestrator executing a Plan-Execute-Verify ReAct loop with dynamic recovery and SQLite WAL task persistence.
- **Specialized Agents**: Browser Agent (UIA + CDP), File Agent (safe diffs & backups), System Agent (telemetry & AST commands), Vision Agent (multimodal screen reasoning).
- **Security Engine**: Default-Deny permission checks with 6-choice human approvals (`Allow Once`, `Allow for Session`, `Allow for Project`, `Allow Full Access`, `Deny`, `Emergency Stop`).
