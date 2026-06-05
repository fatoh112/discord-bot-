@echo off
cd /d "%~dp0"
call stop.bat
ping 127.0.0.1 -n 3 >nul
call start.bat
