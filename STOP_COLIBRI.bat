@echo off
setlocal enabledelayedexpansion
title Stop Colibri Server

echo ===============================================================================
echo                STOPPING COLIBRI LOCAL AI INFERENCE SERVER
echo ===============================================================================
echo.

echo [1/3] Terminating Colibri OLMoE engine processes...
taskkill /F /IM olmoe.exe >nul 2>&1
if errorlevel 0 (
    echo   olmoe.exe stopped.
) else (
    echo   No running olmoe.exe found.
)

echo.
echo [2/3] Checking for processes listening on port 8000...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo   Terminating process PID %%a on port 8000...
    taskkill /F /PID %%a >nul 2>&1
)

echo.
echo [3/3] Checking server port status...
netstat -aon | findstr ":8000" | findstr "LISTENING" >nul 2>&1
if errorlevel 1 (
    echo   Port 8000 is clean and released.
    echo.
    echo ===============================================================================
    echo                     COLIBRI SERVER HAS BEEN STOPPED CLEANLY
    echo ===============================================================================
) else (
    echo   [WARNING] Port 8000 still has an active listener.
)

echo.
pause
