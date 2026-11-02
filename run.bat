@echo off
title Autonomous Multi-Agent Windows OS Assistant
cd /d "%~dp0"

echo ======================================================================
echo    Starting AI-Native Autonomous Windows OS Assistant (Option A)
echo    Powered by Google Gemini 2.0 Flash / Groq (Zero-Setup Free API)
echo ======================================================================

set PYTHON_EXE=venv\Scripts\python.exe

if not exist "%PYTHON_EXE%" (
    echo [!] Virtual environment not detected. Creating venv...
    python -m venv venv
    call venv\Scripts\pip.exe install -r requirements.txt
)

echo [*] Starting Assistant Server on Port 8000...
start "" http://localhost:8000/desktop/index.html

"%PYTHON_EXE%" -m uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8000
pause
