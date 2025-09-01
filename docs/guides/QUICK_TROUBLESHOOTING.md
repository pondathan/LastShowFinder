# 🚨 Quick Troubleshooting Reference

## ⚡ Most Common Issues (Python 3.13+)

### 1. Pydantic Build Failures
```bash
# Quick fix - upgrade packages
pip install --upgrade pydantic pydantic-settings

# Alternative - use Python 3.11/3.12
python3.11 -m venv .venv
```

### 2. Import Errors
```bash
# Check virtual environment
which python  # Should show .venv/bin/python
echo $VIRTUAL_ENV  # Should show .venv path

# Reinstall if needed
pip install -r requirements.txt
```

### 3. Settings Validation Errors
```bash
# Look for conflicting env vars
env | grep HTTP_MAX_HOST_CONCURRENCY
unset HTTP_MAX_HOST_CONCURRENCY  # Remove if found
```

## 🔧 Quick Commands

### Virtual Environment
```bash
# Create new venv
python3 -m venv .venv

# Activate
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

# Deactivate
deactivate
```

### Package Management
```bash
# Install dependencies
pip install -r requirements.txt

# Upgrade all packages
pip install --upgrade -r requirements.txt

# Clear cache
pip cache purge
```

### Service Management
```bash
# Start service
uvicorn worker:app --host 0.0.0.0 --port 8000 --reload

# Check health
curl http://localhost:8000/health

# Kill process on port
lsof -i :8000
kill -9 <PID>
```

## 📋 Pre-Flight Checklist

Before starting development:
- [ ] Python 3.11+ installed
- [ ] Virtual environment created and activated
- [ ] Dependencies installed successfully
- [ ] No conflicting environment variables
- [ ] Port 8000 available

## 🆘 Still Having Issues?

1. **Check Python version**: `python --version`
2. **Verify venv activation**: `echo $VIRTUAL_ENV`
3. **Check installed packages**: `pip list`
4. **Look for error patterns** in the output
5. **Try the quick fixes** above
6. **Check the full troubleshooting guide** in `docs/guides/venv-setup-guide.md`

## 📞 Common Error Messages

| Error | Quick Fix |
|-------|-----------|
| `pydantic-core build failed` | Use Python 3.11/3.12 or upgrade packages |
| `ModuleNotFoundError` | Activate virtual environment |
| `Settings validation error` | Check for conflicting env vars |
| `Address already in use` | Use different port or kill existing process |
| `Permission denied` | Use port > 1024 |
