@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
set "PATH=%~dp0node;%PATH%"

:: Enable ANSI colors on Windows 10+
reg add "HKCU\Console" /v VirtualTerminalLevel /t REG_DWORD /d 1 /f >nul 2>&1

:: Color codes (ANSI escape sequences)
set "GREEN=[32m"
set "RED=[31m"
set "YELLOW=[33m"
set "RESET=[0m"

echo %GREEN%=========================================%RESET%
echo %GREEN%        Discord Bot Launcher             %RESET%
echo %GREEN%=========================================%RESET%
echo.

:: 1. Check if .env exists
if not exist ".env" (
    echo %RED%[ERROR] .env file is missing!%RESET%
    echo %YELLOW%[INFO] Please copy .env.example to .env and configure your bot credentials.%RESET%
    echo.
    goto exit_pause
)

echo %GREEN%[OK] .env file found.%RESET%

:: 2. Check and activate virtual environment
set "VENV_DIR=.venv"
if exist ".venv\Scripts\activate.bat" (
    set "VENV_DIR=.venv"
) else if exist "venv\Scripts\activate.bat" (
    set "VENV_DIR=venv"
) else (
    echo %YELLOW%[INFO] Virtual environment not found. Creating .venv ...%RESET%
    python -m venv .venv
    if errorlevel 1 (
        echo %RED%[ERROR] Failed to create virtual environment. Is Python 3.11+ installed?%RESET%
        goto exit_pause
    )
    set "VENV_DIR=.venv"
)

echo %GREEN%[INFO] Activating virtual environment (%VENV_DIR%)...%RESET%
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo %RED%[ERROR] Failed to activate virtual environment.%RESET%
    goto exit_pause
)

:: 3. Install/verify requirements quietly
echo %GREEN%[INFO] Checking and installing dependencies...%RESET%
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo %RED%[ERROR] Failed to install package requirements.%RESET%
    goto exit_pause
)
echo %GREEN%[OK] Dependencies ready.%RESET%
echo.

:: 4. Start the bot directly
echo %GREEN%[INFO] Bot starting... (Ctrl+C to stop)%RESET%
echo.
python bot.py

echo.
if errorlevel 1 (
    echo %RED%[ERROR] Bot exited with an error. Check logs\errors.log for details.%RESET%
) else (
    echo %GREEN%[INFO] Bot stopped gracefully.%RESET%
)

:exit_pause
echo.
echo Press any key to exit...
pause >nul
endlocal
