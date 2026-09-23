@echo off
setlocal enabledelayedexpansion
title Colibri Local AI Inference Server

echo ===============================================================================
echo                COLIBRI LOCAL AI INFERENCE SYSTEM (Windows x86_64)
echo                        Engine: OLMoE-1B-7B-Instruct
echo ===============================================================================
echo.

set "BASE_DIR=%~dp0"
if "%BASE_DIR:~-1%"=="\" set "BASE_DIR=%BASE_DIR:~0,-1%"

set "COLIBRI_DIR=%BASE_DIR%\colibri\c"
set "MODEL_DIR=%BASE_DIR%\models\olmoe_merged"

:: 1. Locate Python 3.12
set "PYTHON_EXE=C:\Users\moham\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYTHON_EXE%" (
    where py >nul 2>&1 && set "PYTHON_EXE=py -3"
)
if not exist "%PYTHON_EXE%" (
    where python >nul 2>&1 && set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" -c "import sys; sys.exit(0 if sys.version_info[0]==3 else 1)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3 was not found!
    echo Please install Python 3.10+ and add it to PATH.
    echo.
    pause
    exit /b 1
)

:: 2. Check Colibri engine binary
if not exist "%COLIBRI_DIR%\olmoe.exe" (
    echo [ERROR] Colibri OLMoE engine binary not found at:
    echo "%COLIBRI_DIR%\olmoe.exe"
    echo.
    pause
    exit /b 1
)

:: 3. Check Model Directory and Configuration
if not exist "%MODEL_DIR%\config.json" (
    echo [ERROR] Model directory or config.json missing at:
    echo "%MODEL_DIR%"
    echo.
    echo Run the setup/conversion script first to create the model.
    pause
    exit /b 1
)

:: 4. Set Tuned Hardware Environment Variables (Core i3-1215U: 6 cores, 16 GB RAM)
:: OpenMP: 6 physical-core threads (2 P-cores + 4 E-cores)
set "OMP_NUM_THREADS=6"
:: Context length: 2048 tokens
set "CTX=2048"
:: MoE LRU cache: 64 experts/layer (all experts resident per layer, avoids disk thrashing)
set "CACHE=64"
:: Pilot lookahead prefetcher: 0 (disabled on 6-core chip to avoid CPU thread contention)
set "PILOT=0"
:: Sampling parameters
set "COLI_TEMP=0.7"
set "NUCLEUS=0.95"

:: Server host and port
set "HOST=127.0.0.1"
set "PORT=8000"

echo [CONFIGURATION]
echo   CPU Threads       : %OMP_NUM_THREADS% physical cores
echo   Context Window    : %CTX% tokens
echo   MoE Cache per Lyr : %CACHE% experts
echo   Prefetch Pilot    : %PILOT% (disabled for low CPU overhead)
echo   Model Directory   : %MODEL_DIR%
echo   API Endpoint      : http://%HOST%:%PORT%/v1
echo   Web Dashboard     : http://%HOST%:%PORT%/
echo.
echo Starting Colibri OpenAI-Compatible API Server...
echo Press Ctrl+C to stop the server or run STOP_COLIBRI.bat from another window.
echo.

cd /d "%COLIBRI_DIR%"
"%PYTHON_EXE%" openai_server.py --model "%MODEL_DIR%" --host %HOST% --port %PORT%

if errorlevel 1 (
    echo.
    echo [SERVER STOPPED] Server exited with code %ERRORLEVEL%.
    pause
)
