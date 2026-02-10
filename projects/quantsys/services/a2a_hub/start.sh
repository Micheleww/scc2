#!/bin/bash

# Startup script for A2A Hub

# Change to script directory
cd "$(dirname "$0")"

# Create virtual environment if not exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
. venv/Scripts/activate

# Install dependencies
pip install -r requirements.txt

# Start A2A Hub
python main.py