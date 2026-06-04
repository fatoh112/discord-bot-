@echo off
cd /d "%~dp0"
echo Checking for updates...

:: If using git (optional)
if exist ".git\" (
    git fetch
    git pull
    if errorlevel 1 (
        echo Warning: Git pull failed. Continuing anyway...
    )
)

:: Activate virtual environment
set "VENV_DIR=.venv"
if not exist ".venv\" (
    if exist "venv\" (
        set "VENV_DIR=venv"
    )
)

call !VENV_DIR!\Scripts\activate.bat

:: Reinstall dependencies (in case requirements.txt changed)
pip install -r requirements.txt --upgrade

:: Run database migrations
python -c "from database.db_manager import DatabaseManager; import asyncio; db = DatabaseManager('database.db'); asyncio.run(db.run_migrations())"

echo Update complete. Restarting bot...
call restart.bat
