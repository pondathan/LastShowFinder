Here’s a crisp **overview of the Last-Show Oracle (LSO)** you can keep as a standalone doc or the “executive summary” section of its PRD:

---

# Last-Show Oracle (LSO) — Overview

## What it is

The **Last-Show Oracle** is a microservice + automation step that answers one very specific but critical question:

> *“When and where did this artist last play in San Francisco or New York City?”*

It takes an **artist name** (from Spotify URL → parsed in ATB) and a **metro** (SF or NYC) and returns a structured, verifiable record of the most recent already-played show:

```json
{
  "date_iso": "YYYY-MM-DD",
  "venue": "The Independent",
  "city": "San Francisco, CA",
  "evidence": [{ "url": "...", "snippet": "..." }]
}
```

The Oracle fans out across sources (Songkick gigography, Bandsintown, Perplexity-harvested links, archived snapshots) and applies **deterministic rules** (latest date, metro token filter, source precedence) to select a single “winner” with proof.

It plugs into **Alex’s Talent Booker** Make scenario as the definitive source of truth for “last show in SF” and “last show in NYC.”

---

## Why this is a problem worth solving

* **No single canonical database.** Venues delete past shows, ticketing pages vanish, and artists rarely maintain accurate tour histories.
* **Incomplete aggregators.** Songkick/Bandsintown are useful but not comprehensive; setlist.fm only covers some genres; blogs and local press are noisy.
* **Inconsistent formatting.** Dates appear as ISO attributes, US text (“July 18, 2025”), EU text (“18 Jul 2025”), or images in flyers. Cities are written as “SF,” “San Francisco,” or “Oakland.”
* **Booking depends on it.** For Alex, knowing if an artist has already played SF/NY recently is the **#1 factor**:

  * If they just played, they can’t sell again soon.
  * If they played a much larger venue, they’re not a fit for Alex’s room size.
  * If they haven’t played recently or only at the right tier, they’re viable.
* **Manual search is slow and error-prone.** It requires Googling, scanning venue calendars, and often guessing. It doesn’t scale when looking at dozens of artists.

**Without a reliable last-show signal, every other data point (Spotify listeners, Instagram followers, agent contact) risks leading to the wrong booking decision.**

---

## What success looks like

* **Evidence-first answers:** Every response includes a verifiable URL and snippet showing the date and city/venue in text.
* **High precision:** ≥ 95% of answers are correct on manual audit across a 30-artist test set.
* **Solid coverage:** ≥ 85% of queries return a non-unknown result after cache warmup.
* **Deterministic & explainable:** Selection is rule-based (latest date + precedence order), never opaque or “guessed.” Each result comes with an audit trail (“decision\_path”).
* **Fast enough:** Typical end-to-end lookup completes in < 10 s so that the entire ATB flow (Spotify → Google Sheet row) remains under 20 s.
* **Operational simplicity:** Small FastAPI worker integrated with Make; easy to maintain venue whitelists and metro tokens; cache results for 7 days.
* **Direct booking impact:** Alex can look at a row in the Google Sheet, see last SF/NY shows with evidence, and immediately decide: “Pursue” vs “Defer.”

---

👉 In short: The **Last-Show Oracle** turns a fuzzy, manual, error-prone research task into a **trustworthy, automated, auditable signal** — the single most important piece of booking intelligence in Alex’s Talent Booker.
