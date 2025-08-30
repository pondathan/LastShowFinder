@echo off
REM Last-Show Oracle Startup Script for Windows
REM This script sets up and starts the service in a virtual environment

echo 🚀 Starting Last-Show Oracle...

REM Check if virtual environment exists
if not exist ".venv" (
    echo 📦 Creating virtual environment...
    python -m venv .venv
)

REM Activate virtual environment
echo 🔌 Activating virtual environment...
call .venv\Scripts\activate.bat

REM Install/update dependencies
echo 📥 Installing dependencies...
pip install -r requirements.txt

REM Start the service
echo ▶️  Starting FastAPI service...
echo 🌐 Service will be available at: http://localhost:8000
echo 📖 API docs: http://localhost:8000/docs
echo 🛑 Press Ctrl+C to stop
echo.

uvicorn worker:app --host 0.0.0.0 --port 8000 --reload
