@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

:: Read port from .port file (default 8080)
set PORT=8080
if exist ".port" (
    set /p PORT=<.port
)

:: Query health endpoint
curl -s -o nul -w "%%{http_code}" http://localhost:!PORT!/health > temp_status.txt
set /p STATUS_CODE=<temp_status.txt
del temp_status.txt

if "!STATUS_CODE!"=="200" (
    echo Health check PASSED (HTTP !STATUS_CODE!)
    exit /b 0
) else (
    echo Health check FAILED (HTTP !STATUS_CODE!)
    :: Send alert to Discord webhook if configured (optional)
    exit /b 1
)

endlocal
