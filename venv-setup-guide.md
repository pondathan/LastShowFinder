# Virtual Environment Setup for Last-Show Oracle

This guide will help you set up a Python virtual environment to run the Last-Show Oracle service locally on your machine.

## What is a Virtual Environment?

A virtual environment is an isolated Python environment that:
- Keeps your project dependencies separate from your system Python
- Prevents conflicts between different projects
- Makes it easy to manage package versions
- Can be easily recreated on other machines

## ⚠️ Important: Python Version Compatibility

**Recommended Python versions**: 3.11 or 3.12
**Known issues with Python 3.13+**: Some packages may have compatibility issues

If you encounter package installation problems:
1. **Use Python 3.11 or 3.12** (most stable)
2. **Or upgrade packages**: `pip install --upgrade pydantic pydantic-settings`
3. **Check requirements.txt** for detailed compatibility notes

## Quick Setup (Recommended)

### 1. Create Virtual Environment

```bash
# Navigate to your project directory
cd /path/to/ATB_Last_Show_Finder

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
# .venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Make sure virtual environment is activated (you'll see (.venv) in your prompt)
pip install -r requirements.txt
```

### 3. Run the Service

```bash
# Start the FastAPI service
uvicorn worker:app --host 0.0.0.0 --port 8000 --reload

# Or with specific settings
uvicorn worker:app --host 0.0.0.0 --port 8000 --workers 2
```

### 4. Test the Service

```bash
# In another terminal, test the health endpoint
curl http://localhost:8000/health

# Test Songkick scraping
curl -X POST "http://localhost:8000/scrape-songkick" \
  -H "Content-Type: application/json" \
  -d '{"artist": "The Strokes", "max_pages": 2}'
```

## Detailed Setup

### Prerequisites

- Python 3.8+ installed
- pip (usually comes with Python)
- Git (to clone the repository)

### Step-by-Step Instructions

#### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd ATB_Last_Show_Finder
```

#### 2. Create Virtual Environment

```bash
# Create the virtual environment
python3 -m venv .venv

# Verify it was created
ls -la .venv/
```

#### 3. Activate Virtual Environment

**macOS/Linux:**
```bash
source .venv/bin/activate
```

**Windows:**
```bash
.venv\Scripts\activate
```

**Verify activation:**
- Your prompt should show `(.venv)` at the beginning
- `which python` should point to `.venv/bin/python`

#### 4. Install Dependencies

```bash
# Upgrade pip first
pip install --upgrade pip

# Install project dependencies
pip install -r requirements.txt

# Verify installation
pip list
```

#### 5. Configure Environment (Optional)

```bash
# Create .env file for custom settings
cp .env.example .env  # if you have an example file
# Or create manually:
echo "ENV=dev" > .env
echo "LOG_LEVEL=debug" >> .env
echo "PORT=8000" >> .env
```

#### 6. Run the Service

```bash
# Development mode (with auto-reload)
uvicorn worker:app --host 0.0.0.0 --port 8000 --reload

# Production mode (with multiple workers)
uvicorn worker:app --host 0.0.0.0 --port 8000 --workers 2
```

## Virtual Environment Management

### Activating/Deactivating

```bash
# Activate
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Deactivate
deactivate
```

### Installing Additional Packages

```bash
# Make sure virtual environment is activated
pip install package-name

# Save to requirements.txt
pip freeze > requirements.txt
```

### Updating Dependencies

```bash
# Update all packages
pip install --upgrade -r requirements.txt

# Update specific package
pip install --upgrade package-name
```

### Recreating Virtual Environment

```bash
# Remove old environment
rm -rf .venv

# Create new one
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Troubleshooting

### Common Issues

#### 1. "Command not found: python3"
```bash
# Try these alternatives:
python -m venv .venv
python3.9 -m venv .venv  # if you have Python 3.9
```

#### 2. "Permission denied" on macOS/Linux
```bash
# Make sure you have write permissions
chmod +w .
python3 -m venv .venv
```

#### 3. "pip not found" after activation
```bash
# Reinstall pip in the virtual environment
curl https://bootstrap.pypa.io/get-pip.py | python
```

#### 4. Port already in use
```bash
# Find what's using the port
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use a different port
uvicorn worker:app --host 0.0.0.0 --port 8001 --reload
```

#### 5. Import errors
```bash
# Make sure virtual environment is activated
which python
pip list

# Reinstall dependencies
pip install -r requirements.txt
```

### Verification Commands

```bash
# Check Python version
python --version

# Check pip version
pip --version

# Check installed packages
pip list

# Check virtual environment location
which python

# Check if virtual environment is active
echo $VIRTUAL_ENV
```

## Development Workflow

### 1. Start Development Session

```bash
# Navigate to project
cd /path/to/ATB_Last_Show_Finder

# Activate virtual environment
source .venv/bin/activate

# Start service
uvicorn worker:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Make Changes

- Edit `worker.py` or other files
- Service will auto-reload (if using `--reload` flag)
- Test changes via API endpoints

### 3. End Development Session

```bash
# Stop service (Ctrl+C)
# Deactivate virtual environment
deactivate
```

## Integration with Make.com

Once running locally, your Make.com scenario can use:
- **Local URL:** `http://localhost:8000`
- **Endpoints:** 
  - `http://localhost:8000/scrape-songkick`
  - `http://localhost:8000/parse-generic`
  - `http://localhost:8000/wayback-parse`
  - `http://localhost:8000/select-latest`
  - `http://localhost:8000/health`

## 🚨 Troubleshooting Common Issues

### Package Installation Problems

#### Pydantic Build Failures
```bash
# Problem: pydantic-core build errors on Python 3.13+
# Solution 1: Use Python 3.11 or 3.12 (recommended)
python3.11 -m venv .venv

# Solution 2: Upgrade packages
pip install --upgrade pydantic pydantic-settings

# Solution 3: Clear cache and reinstall
pip cache purge
pip install --no-cache-dir -r requirements.txt
```

#### Version Conflicts
```bash
# Problem: Package version conflicts
# Solution: Use exact versions or upgrade all
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

### Import Errors

#### Module Not Found
```bash
# Problem: Can't import worker or other modules
# Solution: Check virtual environment activation
which python  # Should show .venv/bin/python
echo $VIRTUAL_ENV  # Should show path to .venv

# Reinstall if needed
pip install -r requirements.txt
```

#### Settings Import Issues
```bash
# Problem: Settings validation errors
# Solution: Check for conflicting environment variables
env | grep HTTP  # Look for old HTTP_MAX_HOST_CONCURRENCY
unset HTTP_MAX_HOST_CONCURRENCY  # Remove if found
```

### Service Startup Issues

#### Port Already in Use
```bash
# Problem: Port 8000 is occupied
# Solution: Find and kill process, or use different port
lsof -i :8000
kill -9 <PID>
# Or use different port
uvicorn worker:app --host 0.0.0.0 --port 8001 --reload
```

#### Permission Denied
```bash
# Problem: Can't bind to port
# Solution: Use higher port number or check permissions
uvicorn worker:app --host 0.0.0.0 --port 8080 --reload
```

### Performance Issues

#### Slow Package Installation
```bash
# Problem: pip is slow
# Solution: Use faster mirrors or cache
pip install -i https://pypi.org/simple/ -r requirements.txt
pip install --cache-dir ~/.pip-cache -r requirements.txt
```

#### Memory Issues
```bash
# Problem: Out of memory during build
# Solution: Limit parallel builds
pip install --no-cache-dir --no-build-isolation -r requirements.txt
```

## Next Steps

1. **Set up virtual environment** using the quick setup above
2. **Test the service** with the health endpoint
3. **Update Make.com** to use `http://localhost:8000`
4. **Develop and test** your integration
5. **Deploy to production** when ready (using the VM guide if needed)

## Tips

- **Always activate** the virtual environment before working on the project
- **Use `--reload`** during development for auto-restart on file changes
- **Keep requirements.txt updated** when adding new packages
- **Commit `.venv/` to .gitignore** (don't commit the virtual environment)
- **Use different ports** if you have multiple services running
