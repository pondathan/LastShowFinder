#!/bin/bash

# Last-Show Oracle Startup Script
# This script sets up and starts the service in a virtual environment

echo "🚀 Starting Last-Show Oracle..."

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source .venv/bin/activate

# Install/update dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Start the service
echo "▶️  Starting FastAPI service..."
echo "🌐 Service will be available at: http://localhost:8000"
echo "📖 API docs: http://localhost:8000/docs"
echo "🛑 Press Ctrl+C to stop"
echo ""

uvicorn worker:app --host 0.0.0.0 --port 8000 --reload
