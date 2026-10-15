@echo off
title Presentation Copilot Server
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

echo ============================================================
echo   STARTING PRESENTATION COPILOT SERVER
echo   Web Dashboard: http://localhost:8765
echo   WebSocket:     ws://localhost:8765/ws
echo ============================================================

uvicorn main:app --host 127.0.0.1 --port 8765
pause

