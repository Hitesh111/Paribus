#!/usr/bin/env bash
set -e

echo "Setting up Paribus Bulk Processing System..."

# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -e '.[dev]'

echo "Setup complete! Run ./run.sh to start the server."
