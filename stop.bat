@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
echo Sending shutdown signal to bot...

:: Find bot.py process and send taskkill
for /f "tokens=2 delims=," %%i in ('wmic process where "name='python.exe' and commandline like '%%bot.py%%'" get processid /format:csv 2^>nul ^| findstr /r "^[a-zA-Z0-9]"') do (
    set "PID=%%i"
    if not "!PID!"=="" (
        echo Killing Bot Process with PID !PID!
        taskkill /PID !PID! /T /F
    )
)

:: Fallback if wmic is restricted: kill python.exe running bot.py
powershell -Command "Stop-Process -Id (Get-CimInstance Win32_Process | Where-Object CommandLine -like '*bot.py*').ProcessId -Force" 2>nul

echo Bot stopped.
ping 127.0.0.1 -n 3 >nul
endlocal
