@echo off
cd /d "%~dp0"
echo Sending shutdown signal to bot...

:: Find bot.py process and send taskkill
:: Filters by python processes containing bot.py in command line isn't easily done in pure batch without wmic or powershell.
:: We can use taskkill /F /IM python.exe, but that kills all python processes.
:: Alternatively, find PID via wmic process where commandline matches bot.py
for /f "tokens=2 delims=," %%i in ('wmic process where "name='python.exe' and commandline like '%%bot.py%%'" get processid /format:csv 2^>nul ^| findstr /r "^[a-zA-Z0-9]"') do (
    set "PID=%%i"
    if not "!PID!"=="" (
        echo Killing Bot Process with PID !PID!
        taskkill /PID !PID! /T /F
    )
)

:: Fallback if wmic is restricted: kill python.exe running bot.py
powershell -Command "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe' AND CommandLine LIKE '%bot.py%'\" | Each-Object { Stop-Process -Id $_.ProcessId -Force }" 2>nul

echo Bot stopped.
timeout /t 2 /nobreak >nul
