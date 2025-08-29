Here’s a single, high-level **Master Context** for the entire system — Alex’s Talent Booker (ATB) plus the Last-Show Oracle (LSO). It’s written so engineers, automation builders (Make), and Alex all share one mental model.

---

# Alex’s Talent Booker — Master Context

## 1) Purpose

Automate venue-fit booking research for Alex. Given a **Spotify artist URL**, ATB gathers the core signals needed to decide whether to pursue a booking, then logs the result to a Google Sheet. The **Last-Show Oracle (LSO)** is a sub-system that determines the most recent **already-played** show for the artist in **San Francisco** and **New York**, with verifiable proof. This signal is decisive for “right time / right size” fit.

## 2) Primary Outcomes

* **Fast triage:** 1 click → reliable data row with evidence links.
* **Venue/recency fit:** If an artist played the target market recently or at too large a room, auto-flag “Do not pursue now.”
* **Auditability:** Every claim, especially last show, has a URL + snippet.
* **Repeatability:** Same inputs produce same decisions.

## 3) Users & Roles

* **Alex (Booker):** Initiates checks, reviews result, makes pursue/skip choice.
* **Automation Builder (Make):** Owns orchestration, credentials, and sheet wiring.
* **Service Owner (Code):** Owns LSO worker and parsing/selection reliability.

## 4) Scope (what ATB does)

* Input: Spotify artist URL (front end).
* Fetch: Spotify artist profile (name, ID, followers, genres, images).
* Enrich: Instagram handle + follower count, agent name + contact, **last show SF**, **last show NYC**.
* Write: Append a normalized row to Google Sheet.
* Decision helper: Compute “fit flags” (recent play, venue size).
* Provide links: Evidence for last shows; artist, social, and agent sources.

Out of scope (for now): outreach emails, CRM sync, contract flow, hold calendars.

---

## 5) System Overview

### 5.1 Front End (FE)

* Minimal UI: input field for Spotify URL → displays fetched profile → “Validate & Run” button.
* On click → **webhook** to Make with `{ artistId, artistName, spotifyUrl }`.

### 5.2 Make Scenario (Orchestrator)

Responsible for:

* Spotify API enrichment (followers, genres).
* Instagram enrichment (handle + followers).
* Agent discovery (simple heuristics or directory/API if available).
* **Last-Show** lookups (via LSO).
* Decision flags.
* Google Sheets write.

### 5.3 Last-Show Oracle (LSO) — Code Service

* FastAPI worker with four endpoints:

  * `POST /scrape-songkick` — Songkick gigography pages 1–8 → candidates
  * `POST /parse-generic` — parse arbitrary URLs (or HTML) → candidates
  * `GET /wayback-parse` — Internet Archive snapshots for disappeared pages
  * `POST /select-latest` — deterministic selection for SF/NYC
* Deterministic, evidence-first, no paid aggregator APIs.

---

## 6) Data Flow (happy path)

1. **FE → Make (webhook)**
   Payload: `{ artistId, artistName, spotifyUrl }`

2. **Make: Spotify enrichment**

   * Get artist profile: `name, followers_total, genres, images`
   * (Optional) get listener metrics if available.

3. **Make: Instagram enrichment**

   * Derive handle (Spotify external URLs, search, or mapping).
   * Resolve follower count (API or scraping vendor you configure).

4. **Make: Agent enrichment**

   * Try known sources (roster pages, prior mapping, contact DB).
   * If none, leave blank.

5. **Make: Last-Show (SF & NYC)**

   * Build `urls[]` via Perplexity (rich + simple) for each metro.
   * Call LSO:

     * `POST /scrape-songkick` (once per artist) → candidates
     * Iterate `urls[]`: `POST /parse-generic` → candidates
     * On failure/empty: `GET /wayback-parse` → candidates
     * `POST /select-latest` with `{ metro, candidates }` → **winner** + alternates.

6. **Make: Decision flags**

   * `recently_played_SF`: true if last SF show ≤ configured window (e.g., 90 days).
   * `recently_played_NYC`: same for NYC.
   * `venue_too_large`: true if venue matches list above Alex’s typical capacity.
   * `fit_recommendation`: “Pursue” | “Defer: Recent” | “Defer: Too Large” | “Unknown”.

7. **Make → Google Sheets**
   Append row with normalized columns (see 7.1).

8. **Make → FE (optional callback)**
   Return the compiled record for on-screen confirmation.

---

## 7) Interfaces & Schemas

### 7.1 Google Sheet Columns (append in this order)

1. Timestamp (ISO)
2. Artist Name
3. Spotify URL
4. Spotify ID
5. Spotify Followers
6. Genres (joined by `;`)
7. Instagram Handle
8. Instagram Followers
9. Agent Name
10. Agent Contact
11. Last Show SF Date (YYYY-MM-DD)
12. Last Show SF Venue
13. Last Show SF City
14. Last Show SF Evidence URL
15. Last Show NYC Date
16. Last Show NYC Venue
17. Last Show NYC City
18. Last Show NYC Evidence URL
19. Recently Played SF? (true/false)
20. Recently Played NYC? (true/false)
21. Venue Too Large? (true/false)
22. Fit Recommendation
23. Notes

### 7.2 FE → Make Webhook (request)

```json
{
  "artistId": "spotify:artist:123",
  "artistName": "Artist Name",
  "spotifyUrl": "https://open.spotify.com/artist/..."
}
```

### 7.3 Make → LSO `/select-latest` (request)

```json
{
  "metro": "SF",
  "candidates": [
    {
      "date_iso": "YYYY-MM-DD",
      "city": "San Francisco, CA",
      "venue": "The Independent",
      "url": "https://...",
      "source_type": "songkick|bandsintown|venue|ticketing|artist|setlist|press",
      "snippet": "verbatim line with date + city or venue",
      "canceled": false
    }
  ]
}
```

### 7.4 LSO → Make `/select-latest` (response)

```json
{
  "metro": "SF",
  "date_iso": "YYYY-MM-DD",
  "venue": "...",
  "city": "...",
  "evidence": [{ "url": "...", "snippet": "..." }],
  "alternates": [{ "url": "...", "snippet": "..." }],
  "notes": { "canceled": false, "multi_night_series": false },
  "audit": { "decision_path": ["latest_date","precedence"], "candidates_considered": 9 }
}
```

---

## 8) Decision Logic (Fit Recommendation)

Configurable constants:

* `RECENT_WINDOW_DAYS = 90` (example)
* `TOO_LARGE_VENUES_SF = [...]`
* `TOO_LARGE_VENUES_NYC = [...]`

Pseudocode:

```
recent_SF  = lastShowSF.date && days_since(lastShowSF.date) <= RECENT_WINDOW_DAYS
recent_NYC = lastShowNYC.date && days_since(lastShowNYC.date) <= RECENT_WINDOW_DAYS

too_large_SF  = lastShowSF.venue in TOO_LARGE_VENUES_SF
too_large_NYC = lastShowNYC.venue in TOO_LARGE_VENUES_NYC

if recent_SF or recent_NYC:           recommend = "Defer: Recent"
else if too_large_SF or too_large_NYC: recommend = "Defer: Too Large"
else if !lastShowSF.date && !lastShowNYC.date: recommend = "Unknown"
else                                     recommend = "Pursue"
```

---

## 9) Non-Functional Requirements

* **Precision over recall:** Any returned last-show must include URL + snippet with date and city/venue.
* **Latency:** End-to-end run (FE click → sheet row) typically ≤ 20 s.
* **Resilience:** On transient failures, continue and fill what’s available; never block sheet write.
* **Cost:** Prefer open-web and cached results; avoid paid aggregator APIs.
* **Compliance:** Respect robots.txt; use Wayback when live fetch is disallowed.

---

## 10) Observability & Logging

* **Make:** log each step status; capture list of fetched URLs; record alternates for last-show.
* **LSO:** structured logs per candidate `{host, date_iso, city, venue, url}` and final `decision_path`.
* **Sheet:** include evidence URLs for human audit.

---

## 11) Errors & Fallbacks

* If Spotify/IG/agent data fails: write sheet row with blanks + `notes="partial"`.
* If Last-Show returns unknown: write `Unknown` last-show fields; still compute recommendation (likely “Unknown”).
* If robots-blocked: auto-attempt Wayback snapshot; if none, mark unknown.

---

## 12) Security & Keys

* Store API keys (Spotify, Perplexity, IG vendor) in Make connections / vault.
* LSO deployed with its own key (if you gate it); Make uses it via header.
* No PII storage beyond business contact info Alex already sources.

---

## 13) Acceptance Criteria (System)

* From a Spotify artist URL, ATB appends a complete row in one click with:

  * Spotify followers, genres
  * IG handle + followers (if resolvable)
  * Agent name/contact (if resolvable)
  * Last show SF (date/venue/city/evidence) or Unknown
  * Last show NYC (date/venue/city/evidence) or Unknown
  * Fit recommendation populated
* ≥ 95% precision on last-show answers (manual audit of a 30-artist set).
* ≥ 85% coverage non-unknown for last-show after cache warm.
* Median run ≤ 20 s on that set.

---

## 14) Milestones & Ownership

* **Week 1:** FE webhook + Make orchestration stub + Google Sheet write \[Owner: Make]
* **Week 1:** LSO endpoints online with basic parsing & selection \[Owner: Code]
* **Week 2:** IG + Agent enrichment and decision flags \[Owner: Make]
* **Week 2:** Evaluation run on 30-artist set; tune venue lists and metro tokens \[Both]
* **Week 3:** Hardening (timeouts, retries, logging), small UI polish \[Both]

---

## 15) Glossary

* **Candidate (LSO):** A parsed event `{date_iso, city, venue, url, source_type, snippet}`.
* **Evidence:** The URL + verbatim page text containing the date and city/venue.
* **Metro tokens:** City/borough strings used to determine SF/NYC membership.
* **Precedence:** Source trust ladder used for tie-breaking at the same date.

---

## 16) Attachments (pointers)

* LSO API contracts (already defined above).
* Make scenario steps (three code-service touchpoints).
* Venue whitelists and metro tokens (kept in config, editable).

---

This master context captures **what** ATB + LSO do, **why** they exist, and **how** they fit together — with precise interfaces so you can keep building the Make scenario and the code worker in lockstep.
