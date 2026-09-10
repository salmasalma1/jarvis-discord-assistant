@echo off
REM ============================================================
REM JARVIS background launcher — runs the bot without a terminal.
REM Prefer pythonw (no console window) so it keeps running after
REM you close this launcher window.
REM ============================================================
cd /d "%~dp0"

REM Try pythonw from the venv, else fall back to plain pythonw.
if exist ".venv\Scripts\pythonw.exe" (
    start "" /B .venv\Scripts\pythonw.exe main.py
) else (
    start "" /B pythonw main.py
)

echo JARVIS launched in the background.
echo You can close this window — it keeps running.
timeout /t 5 >nul
