# Last-Show Oracle (LSO)

A FastAPI microservice that integrates with Make.com to provide reliable last-show data for Alex's Talent Booker. The service parses open-web pages and applies deterministic selection rules to return the most recent **already-played** show for a given metro (SF or NYC), with verifiable evidence.

## Features

- **Four core endpoints** for parsing and selection
- **Deterministic selection logic** with source precedence and tie-breakers
- **Metro filtering** for SF and NYC with venue whitelists
- **Wayback fallback** when live pages fail
- **Evidence-first approach** with URL + snippet for every result
- **Production-ready** with Docker, health checks, and structured logging

## Quick Start

### Local Development

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the service
uvicorn worker:app --host 0.0.0.0 --port 8000 --workers 2
```

### 🚨 Having Issues?

**Python 3.13+ compatibility problems?** See [Quick Troubleshooting](docs/guides/QUICK_TROUBLESHOOTING.md) or [Full Setup Guide](docs/guides/venv-setup-guide.md)

**Common quick fixes:**
```bash
# For pydantic build failures
pip install --upgrade pydantic pydantic-settings

# For import errors
which python  # Should show .venv/bin/python
pip install -r requirements.txt
```

### Docker

```bash
# Build and run
docker build -t last-show-oracle .
docker run -p 8000:8000 last-show-oracle
```

## API Endpoints

### 1. POST `/scrape-songkick`

Scrape Songkick gigography pages for an artist.

**Request:**
```json
{
  "artist": "Artist Name",
  "slug": "optional-hyphenated",
  "max_pages": 8
}
```

**Response:** Array of `Candidate` objects with `source_type="songkick"`

**Example:**
```bash
curl -X POST "http://localhost:8000/scrape-songkick" \
  -H "Content-Type: application/json" \
  -d '{"artist": "The Strokes", "max_pages": 3}'
```

### 2. POST `/parse-generic`

Parse arbitrary HTML/URLs into candidate events.

**Request:**
```json
{
  "url": "https://example.com/event-page",
  "html": "<optional raw HTML>",
  "artist": "<optional artist name>"
}
```

**Response:** Array of `Candidate` objects with inferred `source_type`

**Example:**
```bash
curl -X POST "http://localhost:8000/parse-generic" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://venue.com/past-shows"}'
```

### 3. GET `/wayback-parse`

Parse Internet Archive snapshots when live pages fail.

**Query Parameters:**
- `url`: Target URL
- `from_year`: Start year (default: 2023)
- `to_year`: End year (default: current year)
- `limit`: Max snapshots (default: 2, max: 5)

**Response:** Array of `Candidate` objects with `source_type="wayback_*"`

**Example:**
```bash
curl "http://localhost:8000/wayback-parse?url=https://example.com&from_year=2023&limit=2"
```

### 4. POST `/select-latest`

Apply deterministic rules to select the most recent show in SF/NYC.

**Request:**
```json
{
  "metro": "SF",
  "candidates": [
    {
      "date_iso": "2024-01-15",
      "city": "San Francisco, CA",
      "venue": "The Independent",
      "url": "https://...",
      "source_type": "venue",
      "snippet": "Show at The Independent in San Francisco",
      "canceled": false
    }
  ]
}
```

**Response (Success):**
```json
{
  "metro": "SF",
  "date_iso": "2024-01-15",
  "venue": "The Independent",
  "city": "San Francisco, CA",
  "evidence": [{"url": "...", "snippet": "..."}],
  "alternates": [{"url": "...", "snippet": "..."}],
  "notes": {"canceled": false, "multi_night_series": false},
  "audit": {"decision_path": ["latest_date", "precedence"], "candidates_considered": 1}
}
```

**Response (Unknown):**
```json
{
  "status": "unknown",
  "alternates": [{"url": "...", "snippet": "..."}],
  "audit": {"decision_path": ["no_valid_candidates"], "candidates_considered": 0}
}
```

### 5. GET `/health`

Health check endpoint for monitoring.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00"
}
```

## Data Models

### Candidate Object
```json
{
  "date_iso": "YYYY-MM-DD",
  "city": "San Francisco, CA",
  "venue": "The Independent",
  "url": "https://...",
  "source_type": "songkick|bandsintown|venue|ticketing|artist|setlist|press",
  "snippet": "verbatim text containing date and city/venue",
  "canceled": false
}
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Service port |
| `WORKERS` | `2` | Uvicorn workers |
| `ENV` | `dev` | Environment (dev/staging/prod) |
| `LOG_LEVEL` | `info` | Logging level |
| `HTTP_TIMEOUT_SECONDS` | `10` | HTTP request timeout |
| `HTTP_MAX_RETRIES` | `1` | HTTP retry attempts |
| `HTTP_MAX_HOST_CONCURRENCY` | `2` | Max concurrent connections per host |
| `CACHE_TTL_DAYS` | `7` | Cache TTL in days |
| `VENUE_WHITELISTS_PATH` | `config/venues.json` | Venue whitelist file path |
| `ALIASES_PATH` | `config/aliases.json` | Artist aliases file path |

### Configuration Files

#### `config/venues.json`
Contains SF/NYC venue whitelists for metro validation.

#### `config/aliases.json`
Optional artist name variants mapping.

## Selection Logic

The service applies deterministic rules in this order:

1. **Filter:** Past date (≤ today), not canceled, belongs to metro
2. **Latest date wins:** Select candidate with most recent date
3. **Source precedence:** `venue > ticketing > artist > setlist > songkick > bandsintown > press`
4. **Tie-breaker:** Snippet contains venue string
5. **Near-tie correction:** ±3 days window prefers higher precedence
6. **Fallback:** Return `status:"unknown"` with top 3 alternates

## Metro Tokens

### San Francisco
- San Francisco, SF, Oakland, Berkeley, San Jose, Palo Alto, Mountain View, Santa Clara, Daly City

### New York City
- New York, NYC, Manhattan, Brooklyn, Queens, Bronx, Staten Island

## Testing

Run the test suite:

```bash
# Install pytest
pip install pytest

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_dates.py

# Run with coverage
pytest --cov=worker tests/
```

## Integration with Make.com

### Workflow Steps

1. **Perplexity Search:** Generate URLs for artist + metro combinations
2. **Songkick Scraping:** Call `/scrape-songkick` once per artist
3. **URL Parsing:** For each URL, call `/parse-generic`
4. **Wayback Fallback:** If parsing fails, call `/wayback-parse`
5. **Selection:** Call `/select-latest` with collected candidates for each metro
6. **Sheet Write:** Log results to Google Sheets with evidence URLs

### Example Make Scenario

```
Spotify Artist URL → 
Perplexity (rich + simple) → 
HTTP: /scrape-songkick → 
For each URL: HTTP: /parse-generic → 
If empty: HTTP: /wayback-parse → 
HTTP: /select-latest (SF) → 
HTTP: /select-latest (NYC) → 
Google Sheets: Append Row
```

## Error Handling

- **Timeouts:** 10s per request with 1 retry on 5xx errors
- **Empty results:** Return empty arrays, don't crash
- **Robots blocked:** Auto-attempt Wayback snapshots
- **All sources empty:** Return `status:"unknown"` with alternates

## Observability

- **Structured logging:** Per-candidate and decision-path logging
- **Health monitoring:** `/health` endpoint for uptime checks
- **Audit trails:** Decision path and candidate counts in responses
- **Error tracking:** Comprehensive error logging with context

## Deployment

### Local Development (Recommended)

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the service (recommended)
./scripts/start_local.sh

# Or manually
uvicorn worker:app --host 0.0.0.0 --port 8000 --reload
```

### Docker (Alternative)

```bash
# Build and run
docker build -t last-show-oracle .
docker run -p 8000:8000 last-show-oracle
```

## Maintenance

- **Venue whitelists:** Update `config/venues.json` as new venues appear
- **Artist aliases:** Add variants to `config/aliases.json`
- **Parser updates:** Capture HTML fixtures when parsing fails
- **Regression testing:** Weekly batch runs on 20 artists

## 📚 Documentation

### Setup & Development
- **[Virtual Environment Setup](docs/guides/venv-setup-guide.md)** - Complete setup guide
- **[Quick Troubleshooting](docs/guides/QUICK_TROUBLESHOOTING.md)** - Common issues & fixes
- **[Hardening Features](docs/guides/HARDENING_FEATURES.md)** - Security & reliability features
- **[Venue Whitelist Info](docs/guides/venuse_whitelist_path.md)** - Configuration details

### Deployment
- **[Deployment Checklist](docs/deployment/DEPLOYMENT_CHECKLIST.md)** - Pre-deployment verification

### Testing & Tools
- **[Smoke Test Results](smoke_test/)** - Previous test results and baselines
- **[Local Testing Tools](tools/)** - Smoke test scripts and candidate data
- **[Test Suite](tests/)** - Unit tests and fixtures
- **[GitHub Actions](.github/workflows/)** - CI/CD pipeline

### Configuration
- **[Environment Variables](.env.example)** - Configuration template
- **[Venue Whitelists](config/venues.json)** - Metro-specific venue lists
- **[Artist Aliases](config/aliases.json)** - Name variations and mappings

### Project Structure
- `scripts/` - Startup and utility scripts
- `tools/` - Testing tools and candidate data
- `docs/` - Comprehensive documentation

## License

Internal use for Alex's Talent Booker project.
