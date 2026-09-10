@echo off
REM =====================================================================
REM JARVIS Windows bootstrap — run this from cmd or PowerShell (NOT Git Bash)
REM Creates a Python 3.11 venv, installs deps, runs main.py.
REM =====================================================================
setlocal
cd /d %~dp0

echo ============================================================
echo JARVIS bootstrap (Windows)
echo ============================================================

REM ---- 1) Locate a usable Python 3.x ----
set "PY_CMD="
py -3.11 --version >nul 2>&1 && set "PY_CMD=py -3.11"
if not defined PY_CMD py -3  --version >nul 2>&1 && set "PY_CMD=py -3"
if not defined PY_CMD py     --version >nul 2>&1 && set "PY_CMD=py"
if not defined PY_CMD python --version >nul 2>&1 && set "PY_CMD=python"

if not defined PY_CMD (
  echo [ERROR] No Python interpreter found on PATH.
  echo Install Python 3.11 from https://www.python.org/downloads/
  echo and check ^"Add python.exe to PATH^" during install.
  pause
  exit /b 1
)
echo Using Python: %PY_CMD%
%PY_CMD% --version

REM ---- 2) Create venv (only if missing) ----
if not exist ".venv\Scripts\python.exe" (
  echo Creating .venv ...
  %PY_CMD% -m venv .venv || ( echo [ERROR] Failed to create venv. & pause & exit /b 1 )
)

echo Activating .venv ...
call .venv\Scripts\activate.bat

REM ---- 3) Install deps ----
echo Installing requirements ...
python -m pip install --quiet --upgrade pip
python -m pip install -r requirements.txt || echo [WARN] Some optional deps failed (LLM/GUI need extra installs).

REM ---- 4) Run ----
echo Running JARVIS ...
python main.py

pause
