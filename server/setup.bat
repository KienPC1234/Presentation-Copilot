@echo off
title Presentation Copilot Server - Quick Setup
cd /d "%~dp0"

echo ============================================================
echo   PRESENTATION COPILOT SERVER - AUTOMATIC SETUP
echo ============================================================

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH! Please install Python 3.10+.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo [*] Creating virtual environment (.venv)...
    python -m venv .venv
)

echo [*] Activating virtual environment...
call .venv\Scripts\activate.bat

echo [*] Installing requirements...
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist ".env" (
    echo [*] Generating .env from .env.example...
    copy .env.example .env
)

echo.
echo [*] Checking Ollama models...
where ollama >nul 2>nul
if %errorlevel% equ 0 (
    echo [*] Pulling Ollama LLM and embedding models...
    ollama pull qwen2.5:7b
    ollama pull nomic-embed-text
) else (
    echo [!] Ollama not found in PATH. Make sure Ollama is installed and running!
)

echo.
echo ============================================================
echo   SETUP COMPLETE!
echo   Run start.bat to launch the server and Web Dashboard.
echo ============================================================
pause

