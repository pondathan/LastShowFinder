# CONTEXT: Utility Service for Make Integration

## What success looks like
Make calls a small HTTP service to get:
- Reliable Songkick candidates
- Robust parsing from arbitrary URLs (and Wayback if needed)
- A deterministic final selection for SF/NYC

## Non-negotiables
- No paid aggregator APIs. Respect robots.txt.
- Evidence-or-bust: each candidate includes a snippet containing a **past date** and either **city** or **venue**.
- Deterministic selection (no ML weights).

## Contracts

### Candidate (service output)
```json
{
  "date_iso": "YYYY-MM-DD",
  "city": "San Francisco, CA",
  "venue": "The Independent",
  "url": "https://...",
  "source_type": "songkick|bandsintown|venue|ticketing|artist|setlist|press",
  "snippet": "verbatim line from page showing date + city/venue",
  "canceled": false
}
