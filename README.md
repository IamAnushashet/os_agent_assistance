# 🖥️ AI-Native Autonomous Multi-Agent Windows OS Assistant

An autonomous, multimodal operating system assistant for Windows. It operates your computer through natural-language text and voice commands, understands the current desktop screen, interacts with your **already-running** browser without Playwright, manages real files with safety backups, performs validated system operations, and connects your mobile phone as a wireless trackpad over your local Wi-Fi network.

Built from scratch using **Option A: Google Gemini 2.0 Flash / Groq (Zero-Setup Free Cloud API)** for instantaneous, 100% free operation with zero local GPU requirements.

---

## 🌟 The 4 Specialized Agents

```
                        ┌────────────────────────────────────────┐
                        │    Central Multi-Agent Orchestrator    │
                        │  (ReAct Loop + Default-Deny Security)  │
                        └──────────────────┬─────────────────────┘
                                           │
         ┌──────────────────┬──────────────┴─────┬──────────────────┐
         │                  │                    │                  │
         ▼                  ▼                    ▼                  ▼
┌──────────────────┐┌──────────────────┐┌──────────────────┐┌──────────────────┐
│  Browser Agent   ││    File Agent    ││   System Agent   ││   Vision Agent   │
│ Controls EXISTING││ Real files, safe ││ Real-time CPU/RAM││ Multimodal screen│
│ Chrome / Edge    ││ paths, diffs &   ││ telemetry, apps, ││ understanding &  │
│ (NO Playwright!) ││ automatic backups││ process manager  ││ UI element locator│
└──────────────────┘└──────────────────┘└──────────────────┘└──────────────────┘
```

1. **🌐 Browser Agent (Strictly NO Playwright)**:
   - Operates your active Chrome, Edge, or Brave browser desktop session.
   - Discovers open tabs, lists active titles & URLs, switches tabs, navigates via omnibox address bar (`Ctrl+L`), and extracts visible page content.
2. **📁 File Agent**:
   - Operates on real files subject to strict canonical path containment.
   - Automatically creates rolling timestamped backups in `scratch/.file_backups/` before modifying any file.
   - Generates unified visual diff previews and enforces confirmation guards on file deletions.
3. **⚙️ System Agent**:
   - Collects real-time hardware telemetry: CPU %, RAM %, per-drive disk space, and battery status via `psutil`.
   - Diagnoses resource bottlenecks, lists active processes, and terminates hung processes safely.
   - Launches approved Windows applications (`notepad`, `calc`, `code`, `explorer`) and brings windows to the foreground.
4. **👁️ Vision Agent**:
   - High-resolution screen capture with Per-Monitor DPI V2 coordinate transformation.
   - Multimodal visual reasoning explaining on-screen error dialogs, application crashes, and terminal tracebacks.
   - Locates exact screen coordinates `(x, y)` for on-screen UI buttons and controls.

---

## 🛑 Security, Permissions & Emergency Stop

- **Default-Deny Policy**: All sensitive operations (file deletion, process termination, arbitrary shell commands) require human consent.
- **6-Choice Human Approval Gate**: `Allow Once`, `Allow for Session`, `Allow for Project`, `Allow Full Access`, `Deny`, and `Emergency Stop`.
- **Instant Emergency Stop**: Red button available on both Desktop and Mobile that halts all background workers in <50ms.

---

## 📱 Mobile Phone Remote (Over Local Wi-Fi)

- Open `http://<LAPTOP-IP>:8000/remote` in any mobile browser on the same Wi-Fi.
- Enter the 4-digit pairing PIN: `4826`.
- **Live Desktop Screen Mirror**: 15 FPS video stream of your laptop screen.
- **Haptic Mini-Trackpad**: 
  - 1-Finger drag = Move mouse cursor
  - 1-Finger tap = Left click
  - 2-Finger tap = Right click
  - 2-Finger drag = Smooth page scroll
  - Hold Drag button = Window move / text selection
- **Mobile Push-to-Talk Mic**: Speak commands from your phone to operate the laptop.

---

## 🚀 One-Click Getting Started

Double-click `run.bat` or run:
```bat
venv\Scripts\python.exe -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000
```
Then open:
- **Desktop Interface**: `http://localhost:8000/desktop/index.html`
- **Mobile Remote**: `http://<YOUR-LAN-IP>:8000/remote`

### Optional: Add Free Google Gemini API Key
Click **Settings (⚙️)** on the top right of the desktop app:
1. Provider: **Google Gemini**
2. Paste your free API key from [aistudio.google.com](https://aistudio.google.com) (no credit card needed).
3. Click **Save Settings**.

---

## 🎓 College Viva Demonstration Scenarios

1. **Browser Automation**: *"Open my browser, search for FastAPI documentation, and summarize the installation steps."*
2. **Autonomous File Operations**: *"Search for the configuration file in my project, create a backup, add an 'Approved' comment, and show me the diff."*
3. **Hardware Telemetry & App Launch**: *"Check my CPU and RAM usage, identify the top memory-consuming process, and launch Calculator."*
4. **Vision Error Diagnostics**: *"Look at my screen, explain the code error in this terminal, and suggest the exact command to fix it."*
