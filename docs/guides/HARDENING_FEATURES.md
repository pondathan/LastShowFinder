# Last-Show Oracle: Hardening Features

This document outlines the security and reliability features implemented in the Last-Show Oracle service.

## 🚨 Common Setup Issues & Solutions

### Python Version Compatibility
**Problem**: Package installation fails with Python 3.13+
**Solution**: 
- Use Python 3.11 or 3.12 for maximum compatibility
- Or upgrade packages: `pip install --upgrade pydantic pydantic-settings`
- See requirements.txt for detailed compatibility notes

### Virtual Environment Issues
**Problem**: Import errors or package conflicts
**Solution**:
```bash
# Always use virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Pydantic Version Conflicts
**Problem**: `pydantic-core` build failures
**Solution**:
```bash
# Clear cache and reinstall
pip cache purge
pip install --no-cache-dir -r requirements.txt
```

## 🔐 API Key Middleware

- **Optional Authentication**: API key protection can be enabled via `API_KEY` environment variable
- **Protected Endpoints**: All main endpoints require valid API key when configured
- **Exempt Endpoints**: `/health` and `/ready` endpoints are always accessible
- **Header Format**: Uses `Authorization: Bearer <API_KEY>` header

### Configuration
```bash
# Set in .env file
API_KEY=your-secret-api-key-here
```

## 🌐 HTTP Client Hardening

- **Timeout Protection**: Configurable timeout via `HTTP_TIMEOUT_SECONDS` (default: 10s)
- **Retry Logic**: Automatic retry on 5xx errors (configurable via `HTTP_MAX_RETRIES`)
- **Concurrency Limits**: Per-host connection limits via `HTTP_MAX_PER_HOST` (default: 2)
- **Shared Client**: Single HTTP client with connection pooling

### Configuration
```bash
HTTP_TIMEOUT_SECONDS=10
HTTP_MAX_RETRIES=1
HTTP_MAX_PER_HOST=2
```

## 📅 Data Validation

- **Year Sanity Check**: Dates must be between 1900 and current_year + 1
- **ISO Format Validation**: Strict ISO date format validation (YYYY-MM-DD)
- **Venue/City Presence**: Candidates must have either venue or city information
- **Evidence Snippets**: All selections include evidence URLs and text snippets

## 🔄 Wayback Fallback

- **Automatic Fallback**: Triggers on 403, 429, or 5xx errors
- **CDX Integration**: Uses Internet Archive's CDX API for snapshot discovery
- **Snapshot Parsing**: Parses historical snapshots when live pages fail
- **Source Marking**: Wayback-sourced candidates are clearly marked

## 🚫 Deduplication

- **Row-Scoped Parsing**: Songkick parsing extracts venue/city from same row as date
- **Candidate Dedup**: Removes duplicates based on date + venue + city + host
- **Evidence Preservation**: Maintains unique evidence for each candidate

## 🏥 Health Monitoring

- **Health Endpoint**: `/health` for basic service status
- **Ready Endpoint**: `/ready` for deployment readiness checks
- **Startup Validation**: Config file loading validation on startup
- **Graceful Shutdown**: Proper HTTP client cleanup on shutdown

## 🧪 Testing & CI

- **Unit Tests**: Basic functionality tests with pytest
- **GitHub Actions**: Automated testing and Docker build pipeline
- **Local Smoke Tests**: Script to verify hardening features locally
- **Docker Health Checks**: Container health monitoring

## 🚀 Local Development

### Quick Start
```bash
# Start the service
./start_local.sh

# Run smoke tests
python local_smoke_test.py

# Run unit tests
pytest tests/ -v
```

### Environment Setup
```bash
# Copy example config
cp .env.example .env

# Edit configuration
nano .env
```

## 📊 Monitoring & Logging

- **Structured Logging**: JSON-formatted logs with context
- **Error Tracking**: Detailed error logging with stack traces
- **Performance Metrics**: Request timing and candidate counts
- **Audit Trails**: Selection decision paths and reasoning

## 🔒 Security Considerations

- **Input Validation**: All user inputs are validated and sanitized
- **Rate Limiting**: Per-host HTTP concurrency limits
- **Error Handling**: Safe error responses without information leakage
- **Config Security**: Sensitive values via environment variables

## 🚨 Error Handling

- **Graceful Degradation**: Continues operation when non-critical services fail
- **Retry Mechanisms**: Automatic retry on transient failures
- **Fallback Strategies**: Wayback integration for failed page fetches
- **User Feedback**: Clear error messages with appropriate HTTP status codes
