# PLAN: Last-Show Oracle Utility Service (for Alex's Talent Booker)

## 1. Context

**Alex's Talent Booker (ATB)** is an automated workflow that, given a Spotify artist URL, gathers the core data needed to make booking decisions (Spotify monthly listeners, Instagram stats, agent contact, and — most importantly — the artist's **last shows in San Francisco and New York City**).  

The **Last-Show Oracle (LSO)** is the dedicated microservice responsible for the last-show data. Make.com orchestrates the flow; the LSO handles the brittle parsing, Songkick gigography, Wayback snapshots, and deterministic selection logic that can't be reliably implemented in Make alone.

The single most important booking signal is:  
- **When and where did this artist last play in SF or NYC?**  
If they played recently or in a room that's too large for Alex's venues, they're not a fit.

---

## 2. Objective

Ship a small FastAPI service that provides:
- `POST /scrape-songkick` — scrape Songkick gigography pages (1–8)
- `POST /parse-generic` — parse arbitrary HTML/URLs into candidate events
- `GET /wayback-parse` — parse Internet Archive snapshots when live pages fail
- `POST /select-latest` — apply deterministic rules to pick the most recent show in SF/NYC

**Make remains the orchestrator.** The worker just handles parsing, Songkick paging, Wayback, and selection. Final outputs flow back into Make and ultimately into Google Sheets.

---

## 3. Milestones

1. ✅ Service scaffold + schemas  
2. ✅ Parsers + Songkick collector  
3. ✅ Selector + metro policy  
4. ✅ Wayback fallback  
5. ✅ Error handling & integration hardening (timeouts, logging, unknown handling)  
6. ✅ Config management (venue whitelists, metro tokens)  
7. ✅ Container + deploy  
8. ⏳ Smoke tests with Make  
9. ⏳ Maintenance loop (fixtures + parser updates)

---

## 4. Task list (check off)

- [x] Scaffold FastAPI app with uvicorn, httpx, bs4, dateutil
- [x] Define **Candidate** schema and **Selection** response schema
- [x] Implement `/scrape-songkick` (pages 1..8, robust list scanning)
- [x] Implement `/parse-generic` (URL or HTML in; scan up to 200 nodes; extract candidates)
- [x] Implement `/wayback-parse` (CDX → latest 1–2 snapshots → parse)
- [x] Implement deterministic selector (`/select-latest`) with precedence & tie-breakers
- [x] Implement metro policy (SF + NYC tokens and venue whitelists in `config/metro.py`)
- [x] Add "upcoming/presale" guard + "canceled/postponed" guard in parser
- [x] Return graceful `"status":"unknown"` when no valid candidates
- [x] Always include up to 3 **alternates** in selection responses
- [x] Add 10 s HTTP timeout, 1 retry on 5xx, host concurrency (httpx client)
- [x] Structured logs for each candidate (host, date_iso, city, venue, url)
- [x] `/select-latest` response includes `audit.decision_path`
- [x] Unit tests: date parsing, metro filter, selector tie cases
- [x] Golden fixtures: 8 real HTML snippets (Songkick, venue, press, ticketing)
- [x] `/health` endpoint
- [x] Dockerfile (2 workers), `requirements.txt`
- [x] Local development setup (virtual environment)
- [ ] Make integration: update three steps (Songkick, parse URLs, select)
- [ ] Smoke test with 20 artists across SF/NYC; capture precision & coverage

---

## 5. Deterministic selector rules

1. ✅ Filter: past date (≤ today), not canceled, belongs to metro (city tokens or venue whitelist).  
2. ✅ Latest date wins (`Dmax`).  
3. ✅ Source precedence at `Dmax`:  
   `venue > ticketing > artist > setlist > songkick > bandsintown > press`.  
4. ✅ Tie-breaker: snippet contains venue string.  
5. ✅ Near-tie correction: if a higher-precedence candidate is within ±3 days of `Dmax`, prefer it.  
6. ✅ If no candidates survive: return `status:"unknown"`, include top 3 alternates.

---

## 6. Config management

- ✅ Store metro tokens and venue whitelists in `config/metro.py` or `config/venues.json`.  
- ✅ Provide simple process for updating when new venues appear.  
- ✅ Maintain `aliases.json` for artist name variants as they're discovered.

---

## 7. Observability

- ✅ Structured logs per candidate: `{ts, artist, metro, host, source_type, date_iso, city, venue, url}`.  
- ✅ Logs decision path on selection.  
- ✅ Expose `/health` endpoint for uptime monitoring.  
- ✅ Add error counts and latency histograms (basic).

---

## 8. Error handling & fallbacks

- ✅ Timeouts: 10 s per request, 1 retry on 5xx.  
- ✅ If parser yields zero candidates: return `[]`, don't crash.  
- ✅ If host is robots-blocked: skip live, try Wayback.  
- ✅ If all sources empty: return `status:"unknown"` with top alternates.

---

## 9. Acceptance criteria

- For a 30-artist test set:  
  - ⏳ ≥ 95% precision (manual audit of links/snippets)  
  - ⏳ ≥ 85% coverage after cache warmup  
- ⏳ Median service call (parse/selector) < 800 ms on typical pages.  
- ✅ All unit tests pass; Make workflow returns valid JSON with evidence.

---

## 10. Maintenance loop

- ✅ **Fixtures:** Every time parsing fails, capture HTML → add fixture → adjust parser.  
- ✅ **Whitelist updates:** Add new SF/NYC venues as encountered.  
- ✅ **Alias updates:** Add artist name variants to `aliases.json`.  
- ⏳ **Regression testing:** Run weekly batch on 20 artists; track precision/coverage.

---

## 11. Integration with Make

Make scenario responsibilities:  
- ✅ Perplexity (rich + simple) → list of URLs.  
- ✅ HTTP call: `/scrape-songkick` once per artist.  
- ✅ For each URL: call `/parse-generic` → if empty/error, `/wayback-parse`.  
- ✅ Collect all candidates → call `/select-latest` with `{"metro":"SF","candidates":[...]}` and again for `"NYC"`.  
- ⏳ Write results to Google Sheet with evidence URL/snippet.

---

## 12. Definition of Done

- ⏳ `/last_show` pipeline returns correct JSON with proof for ≥ 85% coverage on test set.  
- ✅ Selection outputs include evidence and alternates.  
- ✅ Logs and decision paths are explainable.  
- ⏳ End-to-end Make integration works: from Spotify URL → sheet row with last-show data → fit recommendation.
