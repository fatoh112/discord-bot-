@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

:: Color codes
set "GREEN=[32m"
set "RED=[31m"
set "YELLOW=[33m"
set "RESET=[0m"

:: Check Python version (must be 3.11+)
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python 3.11+.
    exit /b 1
)

:: Check .env exists
if not exist ".env" (
    echo ERROR: .env file not found. Copy .env.example to .env and configure.
    exit /b 1
)

:: Create virtual environment if missing (checking both .venv and venv)
set "VENV_DIR=.venv"
if not exist ".venv\" (
    if exist "venv\" (
        set "VENV_DIR=venv"
    ) else (
        echo Creating virtual environment...
        python -m venv .venv
        if errorlevel 1 (
            echo ERROR: Failed to create virtual environment.
            exit /b 1
        )
    )
)

:: Activate venv
call !VENV_DIR!\Scripts\activate.bat

:: Install dependencies
echo Installing dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    exit /b 1
)

:: Create directories if missing
if not exist "logs\" mkdir logs
if not exist "backups\daily\" mkdir backups\daily
if not exist "backups\weekly\" mkdir backups\weekly
if not exist "backups\monthly\" mkdir backups\monthly
if not exist "backups\checksums\" mkdir backups\checksums

:: Start bot with auto-restart
:restart
echo Starting Discord Bot...
python bot.py
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE% equ 0 (
    echo Bot stopped gracefully.
) else if %EXIT_CODE% equ 1 (
    echo Bot exited with error (code 1). Check logs for details.
    echo Waiting 10 seconds before restart...
    timeout /t 10 /nobreak >nul
    goto restart
) else (
    echo Bot crashed (code %EXIT_CODE%). Restarting in 5 seconds...
    timeout /t 5 /nobreak >nul
    goto restart
)

endlocal
