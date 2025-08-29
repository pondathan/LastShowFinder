# Last-Show Oracle: Production Hardening Implementation Plan

## Overview

This document outlines the implementation plan for hardening the Last-Show Oracle (LSO) service based on real-world testing with the **slenderbodies** artist. The goal is to make the service production-ready with resilient scraping, correct parsing, automatic fallbacks, and fully auditable selection logic.

## Context: Issues Discovered During Testing

### Test Case: slenderbodies
- **Test URL:** https://www.songkick.com/artists/9224649-slenderbodies/gigography
- **Artist:** slenderbodies
- **Results:** Successfully identified latest shows in SF (2024-11-01 at The Independent SF) and NYC (2024-10-11 at Irving Plaza)

### Key Issues Found
1. **Songkick slug handling unreliable** - Auto-slugging `slenderbodies` → `slenderbodies` failed, but `9224649-slenderbodies` worked
2. **Malformed dates** - Parsed dates like `"1015-08-29"` which are clearly invalid
3. **Venue site blocking** - Many venue websites return 403 Forbidden, but Wayback fallback wasn't automatic
4. **Limited auditability** - Selection worked but decision reasoning wasn't fully transparent

## Implementation Tasks

### 1. Songkick Slug Handling ✅ **HIGH PRIORITY**

**Current Issue:** Auto-slugging from display names is unreliable for Songkick URLs.

**Solution:** Accept either full artist URL or slug in `/scrape-songkick` body.

**Implementation:**
- If body has `url`, extract artist slug via regex:
  ```python
  r"https?://(?:www\.)?songkick\.com/artists/([^/]+)/?"
  ```
- Accept numeric-prefixed slugs like `9224649-slenderbodies`
- If only `artist` provided, attempt best-effort slug guess but log warning and return empty cleanly if 1st page 404s
- Build gigography pages from extracted slug; stop paging when page returns 404/empty or `max_pages` reached

**Test:** Given URL with `9224649-slenderbodies`, fetch page 1 and parse at least one candidate.

### 2. Date Parsing Correctness + Sanity Guards ✅ **CRITICAL**

**Current Issue:** Malformed dates like `"1015-08-29"` corrupting selection logic.

**Solution:** Implement robust date validation and parsing.

**Implementation:**
- **Prefer** `<time datetime="YYYY-MM-DD">` over text parsing
- Add **year sanity check**: `1900 <= year <= (current_year + 2)`
- If outside range, discard candidate and log at WARNING level
- Normalize all dates with `dateutil` and re-format to ISO
- Strip stray digits and validate date structure

**Test:** Reject malformed inputs that previously produced `1015-...` and ensure they are rejected.

### 3. Auto Wayback for Blocked Hosts ✅ **HIGH PRIORITY**

**Current Issue:** Venue sites return 403/429, but Wayback fallback isn't automatic.

**Solution:** Automatically trigger Wayback fallback on HTTP errors.

**Implementation:**
- In `/parse-generic`, if HTTP status is **403, 429, or 5xx**, automatically try **Wayback** (`/wayback-parse`)
- Include Wayback candidates in the same response instead of returning empty
- If `robots.txt` blocks, skip live fetch and go straight to Wayback
- Add INFO log: `live_status=403 -> wayback_fallback=true`
- Only call Wayback once per URL per request

**Test:** Simulate 403 and verify Wayback call made (mock httpx).

### 4. Robust HTTP Client Behavior ✅ **MEDIUM PRIORITY**

**Current Issue:** No rate limiting, potential for overwhelming hosts.

**Solution:** Implement production-grade HTTP client with limits and backoff.

**Implementation:**
- Add per-host concurrency limiter (2) and backoff on 5xx errors
- Respect configurable **timeout** (env: `HTTP_TIMEOUT_SECONDS`, default 10)
- Normalize headers with stable User-Agent and accept gzip/deflate
- Implement exponential backoff for retries

### 5. Candidate Hygiene ✅ **MEDIUM PRIORITY**

**Current Issue:** Some candidates have empty venue/city fields, potential duplicates.

**Solution:** Implement data quality controls and deduplication.

**Implementation:**
- Add `source_host` field (`urlparse(url).netloc`) for debugging
- Dedupe candidates by `(date_iso, normalized_venue, normalized_city, hostname)`
- Truncate `snippet` to 1000 chars
- Ensure snippet contains a date AND either a metro token OR venue name before emitting
- Validate required fields before creating Candidate objects

### 6. Selector Auditability ✅ **HIGH PRIORITY**

**Current Issue:** Selection works but decision reasoning isn't fully transparent.

**Solution:** Always provide complete audit trail and alternatives.

**Implementation:**
- Ensure `/select-latest` always returns `audit.decision_path` and `candidates_considered`
- If returning `status:"unknown"`, include top 3 alternates with URLs/snippets
- Clear reason in `audit.decision_path` (e.g., `"no_metro_candidates"` or `"no_valid_dates"`)
- Decision path should include at least `["latest_date","precedence"]` or failure reason

**Test:** Decision_path included, alternates present.

### 7. Config & Tokens ✅ **LOW PRIORITY**

**Current Issue:** Need to ensure comprehensive metro coverage and venue data.

**Solution:** Verify existing token lists and add venue placeholders.

**Implementation:**
- Verify SF/NYC token lists include boroughs and common abbreviations
- Add **too-large venue** lists placeholders in `config/venues.json` (commented or separate key)
- Ensure all major venues in each metro are covered

### 8. Logging Upgrades ✅ **LOW PRIORITY**

**Current Issue:** Limited visibility into parsing and selection decisions.

**Solution:** Implement structured logging for operational visibility.

**Implementation:**
- On each candidate: log JSON line `{host, source_type, date_iso, city, venue, url}` at DEBUG
- On selection: log `{decision_path, dmax, best_source_type, best_url}` at INFO
- Structured logging for easier parsing and monitoring

### 9. Tests ✅ **MEDIUM PRIORITY**

**Current Issue:** Limited test coverage for edge cases.

**Solution:** Comprehensive test suite covering all improvements.

**Implementation:**
- `test_songkick_slug_from_url()` → extracts numeric slug and parses page 1
- `test_reject_insane_years()` → rejects 1015/3015
- `test_wayback_on_403()` → simulate 403 and verify Wayback call made (mock httpx)
- `test_selector_audit()` → decision_path included, alternates present

### 10. Documentation Updates ✅ **LOW PRIORITY**

**Current Issue:** README doesn't reflect new capabilities.

**Solution:** Update documentation with new features and examples.

**Implementation:**
- Update `README.md`:
  - `/scrape-songkick` now accepts `{"url": "..."}`
  - Describe automatic Wayback fallback on 403/429/robots
  - Show example curl commands with real Songkick artist URL

## Implementation Priority Order

### Phase 1: Critical Fixes (Week 1)
1. Songkick slug handling
2. Date parsing sanity guards
3. Auto Wayback for blocked hosts

### Phase 2: Core Improvements (Week 2)
4. Robust HTTP client behavior
5. Candidate hygiene
6. Selector auditability

### Phase 3: Polish & Testing (Week 3)
7. Config & tokens verification
8. Logging upgrades
9. Comprehensive tests
10. Documentation updates

## Concrete Code Changes

### 1. `/scrape-songkick` Endpoint
```python
# Update SongkickRequest model
class SongkickRequest(BaseModel):
    artist: str
    slug: Optional[str] = None
    url: Optional[str] = None  # NEW: Accept full URLs
    max_pages: int = Field(default=8, le=8)

# Extract slug from URL if provided
if request.url:
    slug_match = re.search(r"https?://(?:www\.)?songkick\.com/artists/([^/]+)/?", request.url)
    if slug_match:
        slug = slug_match.group(1)
    else:
        raise HTTPException(status_code=400, detail="Invalid Songkick URL format")
elif not request.slug:
    # Fallback to current auto-slugging with warning
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', request.artist.lower()).strip('-')
    logger.warning(f"Auto-generated slug '{slug}' for artist '{request.artist}' - may not work")
```

### 2. Date Sanity Validation
```python
def validate_date_sanity(date_iso: str) -> bool:
    """Validate that date is within reasonable bounds."""
    try:
        year = int(date_iso[:4])
        current_year = datetime.now().year
        return 1900 <= year <= (current_year + 2)
    except (ValueError, IndexError):
        return False

# In date parsing logic
if not validate_date_sanity(date_iso):
    logger.warning(f"Rejecting insane date: {date_iso}")
    continue
```

### 3. Auto Wayback Fallback
```python
# In /parse-generic endpoint
try:
    response = await http_client.get(request.url)
    response.raise_for_status()
    html_content = response.text
    source_url = request.url
    wayback_fallback = False
except httpx.HTTPStatusError as e:
    if e.response.status_code in [403, 429] or e.response.status_code >= 500:
        logger.info(f"Live fetch failed with {e.response.status_code}, trying Wayback fallback")
        wayback_candidates = await wayback_parse_internal(request.url)
        if wayback_candidates:
            return wayback_candidates
        wayback_fallback = True
    raise HTTPException(status_code=e.response.status_code, detail=str(e))
```

### 4. Candidate Deduplication
```python
def dedupe_candidates(candidates: List[Candidate]) -> List[Candidate]:
    """Remove duplicate candidates based on key fields."""
    seen = set()
    unique = []
    
    for candidate in candidates:
        # Create deduplication key
        key = (
            candidate.date_iso,
            candidate.venue.lower().strip() if candidate.venue else "",
            candidate.city.lower().strip() if candidate.city else "",
            urlparse(candidate.url).netloc
        )
        
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    
    return unique
```

### 5. Enhanced Selection Audit
```python
# Ensure audit always includes decision path
if not candidates:
    return {
        "status": "unknown",
        "metro": metro,
        "reason": "no_candidates_found",
        "alternates": [],
        "audit": {
            "decision_path": ["no_candidates"],
            "candidates_considered": 0,
            "reason": "No candidates provided for selection"
        }
    }

# Always include decision path in successful selections
return {
    "metro": metro,
    "date_iso": best_candidate.date_iso,
    "venue": best_candidate.venue,
    "city": best_candidate.city,
    "evidence": [{"url": best_candidate.url, "snippet": best_candidate.snippet}],
    "alternates": alternates,
    "notes": notes,
    "audit": {
        "decision_path": ["latest_date", "precedence"],
        "candidates_considered": len(candidates),
        "best_source_type": best_candidate.source_type,
        "best_url": best_candidate.url
    }
}
```

## Testing Strategy

### Local Testing Commands
```bash
# Start server
uvicorn worker:app --host 0.0.0.0 --port 8000 --reload

# Test Songkick slug extraction
curl -X POST "http://localhost:8000/scrape-songkick" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.songkick.com/artists/9224649-slenderbodies/gigography"}'

# Test date sanity (should reject malformed dates)
curl -X POST "http://localhost:8000/parse-generic" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "html": "<div>1015-08-29</div>"}'

# Test auto-Wayback fallback (mock 403 response)
# This will require test infrastructure setup
```

### Validation Criteria
- [ ] Songkick URLs with numeric slugs parse correctly
- [ ] Malformed dates (1015, 3015) are rejected
- [ ] 403 responses automatically trigger Wayback fallback
- [ ] Selection always includes audit.decision_path
- [ ] Candidates are deduplicated by key fields
- [ ] HTTP client respects rate limits and timeouts

## Success Metrics

### Functional Requirements
- ✅ Songkick scraping works with both URLs and slugs
- ✅ Date parsing rejects invalid years
- ✅ Automatic fallback to Wayback on blocked hosts
- ✅ Selection logic fully auditable
- ✅ No duplicate candidates in results

### Performance Requirements
- ✅ HTTP requests respect rate limits (2 per host)
- ✅ Timeout handling (10s default)
- ✅ Graceful degradation on errors

### Operational Requirements
- ✅ Structured logging for monitoring
- ✅ Comprehensive test coverage
- ✅ Clear error messages and fallback behavior

## Risk Mitigation

### High-Risk Areas
1. **Date parsing changes** - Could break existing working cases
2. **HTTP client modifications** - Could affect all external requests
3. **Selection logic updates** - Could change results for existing queries

### Mitigation Strategies
1. **Comprehensive testing** with real URLs before deployment
2. **Feature flags** for major changes (if needed)
3. **Rollback plan** to previous version if issues arise
4. **Monitoring** of error rates and response times post-deployment

## Post-Implementation Validation

### Immediate Testing
- [ ] All existing endpoints return same results for same inputs
- [ ] New features work as designed
- [ ] Error handling graceful and informative
- [ ] Performance within acceptable bounds

### Production Monitoring
- [ ] Error rates remain low
- [ ] Response times stable
- [ ] Wayback fallback usage reasonable
- [ ] User satisfaction with improved reliability

---

*This plan addresses the real issues discovered during testing while maintaining the evidence-first, deterministic approach that makes the LSO valuable for production use.*
