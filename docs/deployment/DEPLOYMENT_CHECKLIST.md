# Last-Show Oracle: Deployment Checklist

## ✅ Pre-Deployment Hardening Verification

### 1. Code & Configuration
- [ ] Row-scoped Songkick parsing implemented ✓
- [ ] Year sanity check (1900 ≤ year ≤ current_year + 1) ✓
- [ ] Wayback fallback on 403/429 or robots disallow ✓
- [ ] Candidate dedup + evidence-or-bust snippets ✓
- [ ] Optional API key middleware (X-API-Key) ✓
- [ ] Shared HTTP client with timeout (env) ✓
- [ ] 1 retry on 5xx errors ✓
- [ ] Per-host concurrency cap ✓

### 2. Environment & Settings
- [ ] PORT=8000 ✓
- [ ] LOG_LEVEL=info ✓
- [ ] HTTP_TIMEOUT_SECONDS=10 ✓
- [ ] HTTP_MAX_PER_HOST=2 ✓
- [x] VENUE_WHITELISTS_PATH=config/venues.json ✓
- [x] ALIASES_PATH=config/aliases.json ✓
- [ ] API_KEY (configured for production) ✓

### 3. Local Smoke Test Results
- [ ] Start app locally (venv or Docker) ✓
- [ ] Re-run smoke set with 8 artists ✓
- [ ] Verify SF and NYC selections match baseline ✓
- [ ] Spot-check evidence URLs/snippets ✓
- [ ] Confirm no insane years ✓
- [ ] Confirm venue/city present for selected rows ✓

### 4. CI & Versioning
- [ ] GitHub Action runs pytest ✓
- [ ] GitHub Action builds Docker image ✓
- [ ] Tag repo v0.2.x for traceable artifact ✓

## 🚀 Deployment Steps

### 1. Local Testing
```bash
# Start the service
./scripts/start_local.sh

# Run smoke tests
python tools/local_smoke_test.py

# Run unit tests
pytest tests/ -v
```

### 2. Docker Testing
```bash
# Build image
docker build -t last-show-oracle:latest .

# Test locally
docker run -p 8000:8000 last-show-oracle:latest

# Test health endpoints
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

### 3. Production Deployment
```bash
# Set production environment variables
export API_KEY="your-production-api-key"
export LOG_LEVEL="info"
export ENV="prod"

# Deploy to Render/your platform
# Ensure all environment variables are set
```

## 🔍 Post-Deployment Verification

### 1. Health Checks
- [ ] `/health` endpoint responds 200
- [ ] `/ready` endpoint responds 200
- [ ] Protected endpoints require API key

### 2. Smoke Test on Production
- [ ] Run smoke test against production URL
- [ ] Verify all 8 artists return results
- [ ] Check SF/NYC selections are consistent

### 3. Monitoring
- [ ] Logs show proper startup sequence
- [ ] No critical errors in logs
- [ ] Health checks passing in monitoring system

## 🚨 Rollback Plan

If issues are detected:
1. Revert to previous version tag
2. Check logs for error patterns
3. Verify environment variables
4. Test locally before re-deploying

## 📊 Success Metrics

- [ ] All endpoints responding correctly
- [ ] Smoke tests passing consistently
- [ ] No insane dates in results
- [ ] Venue/city information present
- [ ] Evidence URLs accessible
- [ ] Performance within acceptable limits
