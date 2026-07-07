@echo off
REM Weekly competitor-intelligence job (run by Windows Task Scheduler).
REM Portable: resolves its own folder, so it works from any path.
setlocal
cd /d "%~dp0"
echo ===== weekly run: %date% %time% ===== >> data\weekly.log
python main.py weekly >> data\weekly.log 2>&1
echo. >> data\weekly.log
endlocal
