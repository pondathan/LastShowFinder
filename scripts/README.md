# Scripts Directory

This directory contains startup and utility scripts for the Last-Show Oracle service.

## Startup Scripts
- `start_local.sh` - Start the service locally with virtual environment (macOS/Linux)
- `start.sh` - Start the service locally (macOS/Linux)
- `start.bat` - Start the service locally (Windows)

## Usage

### Local Development (Recommended)
```bash
# From project root
./scripts/start_local.sh
```

### Manual Startup
```bash
# From project root
./scripts/start.sh
```

### Windows
```cmd
# From project root
scripts\start.bat
```

## Notes
- `start_local.sh` automatically sets up virtual environment and installs dependencies
- `start.sh` and `start.bat` assume dependencies are already installed
- All scripts start the service on port 8000 with auto-reload enabled
