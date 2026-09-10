#!/usr/bin/env bash
# =============================================================
# One-command launcher for JARVIS.
#   - creates a venv if needed
#   - installs deps (quietly)
#   - runs main.py (which imports the whole system)
# Usage:   bash run.sh
# Run on:  Git Bash / WSL / any POSIX shell (or run main.py directly).
# =============================================================
set -euo pipefail

cd "$(dirname "$0")"

# 1) venv
if [ ! -d ".venv" ]; then
  echo "Creating .venv ..."
  python3 -m venv .venv
fi
# activate (works on unix/bash; on Windows Git Bash this is fine)
source .venv/bin/activate

# 2) install deps
echo "Installing requirements (may take a moment) ..."
pip install -q -r requirements.txt || echo "Some optional deps failed (LLM/GUI need extra installs)."

# 3) run the system
echo "Running JARVIS ..."
python main.py
