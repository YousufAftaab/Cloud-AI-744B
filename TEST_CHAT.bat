@echo off
setlocal
title Colibri Test Chat
echo ===============================================================================
echo                      TESTING LOCAL COLIBRI INFERENCE
echo ===============================================================================
echo.

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

set "PYTHON_EXE=C:\Users\moham\AppData\Local\Programs\Python\Python312\python.exe"

"%PYTHON_EXE%" "%BASE_DIR%\test_chat.py"

echo.
pause
