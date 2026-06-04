@echo off
echo Stopping bot...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

echo Clearing Python cache...
for /d %%i in (__pycache__) do rmdir /s /q "%%i" 2>nul
for /d %%i in (cogs\__pycache__) do rmdir /s /q "%%i" 2>nul
for /d %%i in (database\__pycache__) do rmdir /s /q "%%i" 2>nul

echo Starting fresh...
call launch.bat
