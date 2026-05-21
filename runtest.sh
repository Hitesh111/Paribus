#!/usr/bin/env bash
# Quick helper to run our test suite locally.
# Feel free to pass pytest args, e.g.: ./runtest.sh -k test_resume
set -e

echo "=============================================="
echo "🧪  Running Paribus Bulk Processing Tests..."
echo "=============================================="

if [ -d "venv" ]; then
    echo "📦  Using local virtual environment (venv)..."
    venv/bin/pytest -v "$@"
else
    echo "⚠️   venv not found. Trying global pytest..."
    pytest -v "$@"
fi

