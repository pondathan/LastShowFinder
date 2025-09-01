import re
from typing import Optional, Tuple
from bs4 import BeautifulSoup, Tag

# Metro slugs (anchor/most-reliable)
NYC_METRO_SLUG_RE = re.compile(r"/metro-areas/\d+-(?:us-)?new-york-ny\b", re.I)
SF_METRO_SLUG_RE = re.compile(
    r"/metro-areas/\d+-(?:us-)?san-francisco-bay-area\b", re.I
)

# "City, ST" fallback
CITY_STATE_RE = re.compile(
    r"\b(?P<city>[A-Za-z][A-Za-z .'\-]+?),\s*(?P<state>NY|CA)\b(?:,\s*(?:US|USA))?",
    re.I,
)

# Borough + token sets
NYC_BORO = {
    "new york",
    "manhattan",
    "brooklyn",
    "bklyn",
    "queens",
    "bronx",
    "staten island",
}
NYC_FREE = {"nyc"}  # soft signal; only trust with nearby " NY "
SF_CITIES = {
    "san francisco",
    "oakland",
    "berkeley",
    "san jose",
    "palo alto",
    "mountain view",
    "santa clara",
    "daly city",
}


def extract_venue_specific_text(row: Tag, venue: str) -> Optional[str]:
    """Extract text specific to a venue, avoiding text from other shows in the same row."""
    if not venue:
        return None

    # Get the full row text
    full_text = row.get_text(" ", strip=True)

    # Look for the venue name in the text
    venue_lower = venue.lower()
    venue_index = full_text.lower().find(venue_lower)

    if venue_index == -1:
        return None

    # Extract a window of text around the venue (before and after)
    # This should contain the specific show's information
    start = max(0, venue_index - 100)  # 100 chars before venue
    end = min(len(full_text), venue_index + len(venue) + 100)  # 100 chars after venue

    # Extract the window
    venue_text = full_text[start:end]

    # Look for city/state patterns in this window
    city_state_match = CITY_STATE_RE.search(venue_text)
    if city_state_match:
        # Extend the window to include the city/state info
        city_start = city_state_match.start()
        city_end = city_state_match.end()

        # Adjust window to include city/state
        start = max(0, start + city_start - 50)
        end = min(len(full_text), start + city_end + 50)
        venue_text = full_text[start:end]

    return venue_text.strip()


def nearest_row(node: Tag) -> Tag:
    """Find the nearest row container that contains both time and venue/city info."""
    p = node
    for _ in range(6):  # Look up to 6 levels up
        if not p:
            break
        # A "row" has the time tag and at least some links/text:
        if p.find("time") and (
            p.find("a") or p.find(class_=re.compile(r"\blocation\b", re.I))
        ):
            return p
        p = p.parent
    return node.parent or node


def resolve_songkick_metro(row: Tag) -> Tuple[Optional[str], Optional[str]]:
    """Resolve metro from Songkick row using metro slug patterns."""
    for a in row.find_all("a", href=True):
        href = a["href"]
        if NYC_METRO_SLUG_RE.search(href):
            return "NYC", a.get_text(" ", strip=True)
        elif SF_METRO_SLUG_RE.search(href):
            return "SF", a.get_text(" ", strip=True)
    return None, None


def classify_city_state_from_text(txt: str) -> Tuple[Optional[str], Optional[str]]:
    """Classify metro from "City, ST" pattern in text."""
    match = CITY_STATE_RE.search(txt)
    if not match:
        return None, None

    city = match.group("city").strip()
    state = match.group("state").upper()

    if state == "NY":
        # Check if it's a NYC borough/city
        city_lower = city.lower()
        if city_lower in NYC_BORO:
            return "NYC", f"{city}, {state}"
        # Don't classify upstate NY cities as NYC
        return None, f"{city}, {state}"
    elif state == "CA":
        # Check if it's an SF metro city
        city_lower = city.lower()
        if city_lower in SF_CITIES:
            return "SF", f"{city}, {state}"
        return None, f"{city}, {state}"

    return None, None


def fallback_tokens_to_metro(txt: str) -> Optional[str]:
    """Fallback classification using token patterns."""
    txt_lower = txt.lower()

    # NYC tokens
    if any(boro in txt_lower for boro in NYC_BORO):
        return "NYC"

    # NYC soft signal - only trust when " NY " also appears
    if "nyc" in txt_lower and " ny " in txt_lower:
        return "NYC"

    # NYC abbreviation
    if "nyc" in txt_lower:
        return "NYC"

    # SF tokens
    if any(city in txt_lower for city in SF_CITIES):
        return "SF"

    # Bay Area only when San Francisco is present
    if "bay area" in txt_lower and "san francisco" in txt_lower:
        return "SF"

    return None


def extract_songkick_row_candidate(
    time_tag: Tag,
    page_url: str,
    sf_venue_whitelist_lower: set[str],
    nyc_venue_whitelist_lower: set[str],
    logger=None,
) -> Optional[dict]:
    """Extract candidate from Songkick row with improved metro classification."""
    date_iso = time_tag.get("datetime")
    if not date_iso:
        return None

    # Extract just the date part from ISO 8601 datetime (e.g., 2023-10-27T20:00:00-0400 -> 2023-10-27)
    if "T" in date_iso:
        date_iso = date_iso.split("T")[0]

    row = nearest_row(time_tag)

    # Extract venue first (we need this for scoped classification)
    venue = ""
    for a in row.find_all("a", href=True):
        if "/venues/" in a["href"]:
            venue = a.get_text(" ", strip=True)
            break

    # Extract city from the specific show's information, not the entire row
    city = None

    # 1. Metro via slug (most reliable)
    metro, metro_text = resolve_songkick_metro(row)

    # 2. City/state parsing if no metro slug - scope to venue-specific text
    if not metro:
        # Look for city info near the venue or in the specific show's text
        venue_specific_text = extract_venue_specific_text(row, venue)
        if venue_specific_text:
            metro, city = classify_city_state_from_text(venue_specific_text)

    # 3. Token fallback if still unknown - scope to venue-specific text
    if not metro:
        venue_specific_text = extract_venue_specific_text(row, venue)
        if venue_specific_text:
            metro = fallback_tokens_to_metro(venue_specific_text)

    # 4. Venue whitelist rescue
    if not metro and venue:
        venue_lower = venue.lower()
        if venue_lower in nyc_venue_whitelist_lower:
            metro = "NYC"
        elif venue_lower in sf_venue_whitelist_lower:
            metro = "SF"

    # Debug logging for NY tokens that didn't classify as NYC
    if logger and metro != "NYC":
        txt = extract_venue_specific_text(row, venue) or row.get_text(" ", strip=True)
        if any(
            token in txt.lower()
            for token in ["ny", "new york", "brooklyn", "manhattan", "queens", "bronx"]
        ):
            # Get venue text for logging - ensure it's always initialized
            venue_text_for_log = venue or ""

            logger.debug(
                "songkick_row_debug",
                extra={
                    "fn": "songkick_row_debug",
                    "reason": "NY tokens seen but metro!=NYC",
                    "txt": txt[:300],
                    "venue": venue_text_for_log,
                    "page": page_url,
                    "metro": metro,
                },
            )

    # Set default city based on metro if we have one
    if metro == "NYC" and not city:
        city = "New York, NY"
    elif metro == "SF" and not city:
        city = "San Francisco, CA"

    # Ensure city and venue are never None
    if city is None:
        city = ""
    if venue is None:
        venue = ""

    # Build candidate with scoped snippet
    snippet = extract_venue_specific_text(row, venue) or " ".join(
        row.get_text(" ", strip=True).split()
    )

    return {
        "date_iso": date_iso,
        "metro": metro,
        "city": city,
        "venue": venue,
        "snippet": snippet,
        "source_type": "songkick",
        "source_host": "www.songkick.com",
        "url": page_url,
        "notes": "",
    }
