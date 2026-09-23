@echo off
setlocal
title Stop PC Assistant & Ollama

echo ===============================================================================
echo                STOPPING PC ASSISTANT & OLLAMA ENGINE
echo ===============================================================================
echo.

echo [1/2] Terminating Ollama engine processes...
taskkill /F /IM ollama.exe >nul 2>&1
taskkill /F /IM "ollama app.exe" >nul 2>&1

echo.
echo [2/2] Checking port 11434 status...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":11434" ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
)

netstat -aon | findstr ":11434" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo   Port 11434 is clean and released.
    echo   All local assistant processes stopped.
) else (
    echo   Port 11434 still has an active listener.
)

echo.
pause
