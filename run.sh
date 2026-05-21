#!/usr/bin/env bash
set -e

echo "Starting Paribus Bulk Processing System locally..."

# Activate the virtual environment
source venv/bin/activate

# Start the uvicorn server with hot-reload enabled
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
