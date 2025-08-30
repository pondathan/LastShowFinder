#!/bin/bash

echo "🚀 Starting Last-Show Oracle (Local Hardened Version)"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo "📝 Please edit .env file with your configuration if needed."
fi

# Start the application
echo "🌐 Starting Last-Show Oracle on http://localhost:8000"
echo "📊 Health check: http://localhost:8000/health"
echo "✅ Ready check: http://localhost:8000/ready"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

uvicorn worker:app --host 0.0.0.0 --port 8000 --reload
