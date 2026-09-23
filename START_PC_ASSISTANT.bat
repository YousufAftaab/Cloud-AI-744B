@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title Qwen 2.5 Coder 7B - Local PC Assistant

echo ===============================================================================
echo          QWEN 2.5 CODER 7B — AUTONOMOUS 100%% OFFLINE PC ASSISTANT
echo ===============================================================================
echo.

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

set "OLLAMA_EXE=C:\Users\moham\AppData\Local\Programs\Ollama\ollama.exe"
set "PYTHON_EXE=C:\Users\moham\AppData\Local\Programs\Python\Python312\python.exe"

:: 1. Check if Ollama service is already listening on port 11434
netstat -aon | findstr ":11434" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Starting Ollama local engine in background...
    start /min "" "%OLLAMA_EXE%" serve
    
    :: Wait up to 10 seconds for Ollama to initialize
    for /l %%i in (1,1,10) do (
        netstat -aon | findstr ":11434" | findstr "LISTENING" >nul 2>&1
        if not errorlevel 1 goto :ready
        timeout /t 1 /nobreak >nul
    )
)

:ready
echo [INFO] Ollama engine is active on http://127.0.0.1:11434
echo.

:: 2. Launch the Autonomous PC Assistant
"%PYTHON_EXE%" "%BASE_DIR%\pc_assistant.py"

if errorlevel 1 (
    echo.
    echo [ERROR] Assistant exited with code %ERRORLEVEL%.
    pause
)
