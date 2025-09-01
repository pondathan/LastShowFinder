"""
Last-Show Oracle (LSO) - FastAPI service for parsing concert events and selecting latest shows.

This service integrates with Make.com to provide reliable last-show data for Alex's Talent Booker.
"""  # noqa: E501

import json
import logging
import re
from datetime import datetime, date
from typing import List, Optional, Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from setting import get_settings
from songkick_row_classification import extract_songkick_row_candidate

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    logger.info("Last-Show Oracle starting up...")

    # Load venue whitelists to validate config
    try:
        with open(settings.VENUE_WHITELISTS_PATH) as f:
            whitelists = json.load(f)
            logger.info(f"Loaded venue whitelists: {list(whitelists.keys())}")
            
            # Precompute lowercase sets for case-insensitive comparison
            global SF_VENUE_WHITELIST_LOWER, NYC_VENUE_WHITELIST_LOWER
            SF_VENUE_WHITELIST_LOWER = {venue.lower() for venue in whitelists.get("SF", [])}
            NYC_VENUE_WHITELIST_LOWER = {venue.lower() for venue in whitelists.get("NYC", [])}
    except Exception as e:
        logger.error(f"Failed to load venue whitelists: {e}")
        # Initialize empty sets as fallback
        SF_VENUE_WHITELIST_LOWER = set()
        NYC_VENUE_WHITELIST_LOWER = set()

    yield

    # Shutdown
    logger.info("Last-Show Oracle shutting down...")
    await http_client.aclose()


# Initialize FastAPI app
app = FastAPI(
    title="Last-Show Oracle",
    description="Find the last show an artist played in a specific metro area",
    version="1.0.0",
    lifespan=lifespan,
)

# Load settings
settings = get_settings()

# Global venue whitelist sets (initialized in lifespan)
SF_VENUE_WHITELIST_LOWER = set()
NYC_VENUE_WHITELIST_LOWER = set()

# API Key middleware
security = HTTPBearer(auto_error=False)


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify API key if configured."""
    if not settings.API_KEY:
        return True  # No API key required

    if not credentials:
        raise HTTPException(status_code=401, detail="API key required")

    if credentials.credentials != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return True


# Metro tokens for SF and NYC
METRO_TOKENS = {
    "SF": [
        "San Francisco",
        "SF",
        "Oakland",
        "Berkeley",
        "San Jose",
        "Palo Alto",
        "Mountain View",
        "Santa Clara",
        "Daly City",
    ],
    "NYC": [
        "New York",
        "NYC",
        "Manhattan",
        "Brooklyn",
        "Queens",
        "Bronx",
        "Staten Island",
    ],
}

# Source precedence order (higher = more trusted)
SOURCE_PRECEDENCE = {
    "venue": 7,
    "ticketing": 6,
    "artist": 5,
    "setlist": 4,
    "songkick": 3,
    "bandsintown": 2,
    "press": 1,
}

# HTTP client with timeouts, retries, and per-host concurrency limits
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(settings.HTTP_TIMEOUT_SECONDS),
    limits=httpx.Limits(
        max_connections=settings.HTTP_MAX_PER_HOST,
        max_keepalive_connections=settings.HTTP_MAX_PER_HOST,
    ),
)

# In-memory cache (simple dict for MVP)
cache = {}


# Pydantic models
class Candidate(BaseModel):
    date_iso: str
    city: str
    venue: str
    url: str
    source_type: str
    snippet: str
    canceled: bool = False
    source_host: Optional[str] = None  # NEW: For debugging and deduplication
    metro: Optional[str] = None  # NEW: Metro classification (NYC, SF, etc.)


class SongkickRequest(BaseModel):
    artist: Optional[str] = None  # Optional when URL is provided
    slug: Optional[str] = None
    url: Optional[str] = None  # NEW: Accept full URLs
    max_pages: int = Field(default=8, le=8)


class ParseRequest(BaseModel):
    url: str
    html: Optional[str] = None
    artist: Optional[str] = None


class WaybackRequest(BaseModel):
    url: str
    from_year: int = 2023
    to_year: Optional[int] = None
    limit: int = Field(default=2, le=5)


class SelectRequest(BaseModel):
    metro: str
    candidates: List[Candidate]


class Evidence(BaseModel):
    url: str
    snippet: str


class Notes(BaseModel):
    canceled: bool = False
    multi_night_series: bool = False


class Audit(BaseModel):
    decision_path: List[str]
    candidates_considered: int


class SelectionResponse(BaseModel):
    metro: str
    date_iso: str
    venue: str
    city: str
    evidence: List[Evidence]
    alternates: List[Evidence]
    notes: Notes
    audit: Audit


class UnknownResponse(BaseModel):
    status: str = "unknown"
    alternates: List[Evidence]
    audit: Audit


# Helper functions
def validate_date_sanity(date_iso: str) -> bool:
    """Enhanced date validation with stricter bounds and format checking."""
    try:
        # Handle ISO 8601 dates with timezone info (e.g., 2023-10-27T20:00:00-0400)
        # Extract just the date part (YYYY-MM-DD)
        date_match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", date_iso)
        if not date_match:
            return False

        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))

        current_year = datetime.now().year

        # Year bounds: 1900 to current + 2
        if not (1900 <= year <= (current_year + 2)):
            return False

        # Month bounds: 1-12
        if not (1 <= month <= 12):
            return False

        # Day bounds: 1-31 (basic check)
        if not (1 <= day <= 31):
            return False

        return True
    except (ValueError, IndexError):
        return False


# Address cleaning patterns for fallback date parsing
ADDRESS_SUFFIXES = r"(?:st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ct|court|ln|lane|way|terrace|ter|pl|place|pkwy|parkway)"  # noqa: E501
ADDRESS_RE = re.compile(
    rf"\b\d{{1,5}}\s+[A-Za-z0-9.\-']+(?:\s+[A-Za-z0-9.\-']+)*\s+{ADDRESS_SUFFIXES}\b\.?",  # noqa: E501
    re.IGNORECASE,
)
PHONE_RE = re.compile(r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b")
ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")


def clean_gig_item_text(text: str) -> str:
    """Strip street addresses, phone numbers, and zip codes from a block before date parsing."""  # noqa: E501
    t = ADDRESS_RE.sub("", text)
    t = PHONE_RE.sub("", t)
    t = ZIP_RE.sub("", t)
    # collapse extra whitespace
    return " ".join(t.split())


# Songkick row parsing patterns
VENUE_HREF_RE = re.compile(r"/venues/\d+")
METRO_HREF_RE = re.compile(r"/metro-areas/\d+")
LOCATION_CLASS_RE = re.compile(r"\blocation\b", re.I)


def nearest_row(time_tag) -> any:
    """Find the nearest row container that contains both time and venue/city info."""
    p = time_tag
    for _ in range(6):  # Look up to 6 levels up
        if not p:
            break
        # A "row" has the time tag and at least some links/text:
        if p.find("time") and (p.find("a") or p.find(class_=LOCATION_CLASS_RE)):
            return p
        p = p.parent
    return time_tag.parent or time_tag


def extract_row_candidate(
    time_tag, page_url: str, artist_name: Optional[str] = None
) -> Optional[dict]:
    """Extract a single candidate from a Songkick row, row-scoped only."""
    date_iso = time_tag.get("datetime")
    if not date_iso:
        # Prefer datetime; fallback to text only if needed
        txt = time_tag.get_text(" ", strip=True)
        if not txt:
            return None
        # Use the existing parse_date function for text dates
        date_iso = parse_date(txt)
        if not date_iso:
            return None

    row = nearest_row(time_tag)

    # Venue via href pattern
    venue = None
    for a in row.find_all("a", href=True):
        if VENUE_HREF_RE.search(a["href"]):
            venue = a.get_text(" ", strip=True)
            break

    # City/metro via href pattern, else .location text
    city = None
    metro_a = next(
        (a for a in row.find_all("a", href=True) if METRO_HREF_RE.search(a["href"])),
        None,
    )
    if metro_a:
        city = metro_a.get_text(" ", strip=True)
    else:
        loc = row.find(class_=LOCATION_CLASS_RE)
        if loc:
            city = loc.get_text(" ", strip=True)

    snippet = " ".join(row.get_text(" ", strip=True).split())
    host = urlparse(page_url).netloc

    # Skip rows with date but no city and no venue
    if not city and not venue:
        logger.debug(
            f"Skipping row with date {date_iso} but no city/venue: {snippet[:100]}"  # noqa: E501
        )
        return None

    return {
        "date_iso": date_iso,
        "city": city or "",
        "venue": venue or "",
        "url": page_url,
        "source_type": "songkick",
        "source_host": host,
        "snippet": snippet,
        "canceled": False,
    }


def parse_date(date_text: str) -> Optional[str]:
    """Parse various date formats to ISO string."""
    if not date_text:
        return None

    # Try to extract ISO date from datetime attribute first
    iso_match = re.search(r"(\d{4}-\d{2}-\d{2})", date_text)
    if iso_match:
        return iso_match.group(1)

    # Try to parse common date formats
    try:
        # Remove common prefixes/suffixes
        clean_text = re.sub(
            r"(on|at|playing|performed|shows?|concert)",
            "",
            date_text,
            flags=re.IGNORECASE,
        )
        clean_text = clean_text.strip()

        # Try parsing with dateutil
        parsed_date = date_parser.parse(clean_text, fuzzy=True)
        if parsed_date:
            # Validate that we have a complete date (not just year)
            # Check if the original text contains month/day indicators
            has_month = re.search(
                r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december|\d{1,2}/\d{1,2}|\d{1,2}-\d{1,2})",  # noqa: E501
                clean_text,
                re.IGNORECASE,
            )
            has_day = re.search(r"(\d{1,2}(?:st|nd|rd|th)?)", clean_text)
            has_year = re.search(r"\b\d{4}\b", clean_text)

            # If we only have a year (4 digits), reject it
            if re.match(r"^\d{4}$", clean_text.strip()):
                return None

            # If we have a year but no month/day indicators, reject it
            if re.match(r"^\d{4}$", clean_text.strip()) or (
                not has_month and not has_day
            ):
                return None

            # If we have month/day but no year, reject it
            if (has_month or has_day) and not has_year:
                return None

            return parsed_date.strftime("%Y-%m-%d")
    except Exception:
        pass

    return None


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
            urlparse(candidate.url).netloc,
        )

        if key not in seen:
            seen.add(key)
            unique.append(candidate)

    return unique


async def parse_generic_internal(url: str, html_content: str) -> List[Candidate]:
    """Internal version of parse_generic without HTTP fallback to avoid recursion."""
    candidates = []

    try:
        soup = BeautifulSoup(html_content, "html.parser")

        # Parse up to ~200 DOM nodes for dates
        date_elements = []

        # Look for time elements with datetime attributes
        time_elements = soup.find_all("time", attrs={"datetime": True})
        date_elements.extend(time_elements)

        # Look for elements containing dates
        text_elements = soup.find_all(
            ["span", "div", "p", "li"], string=re.compile(r"\d{4}")
        )
        date_elements.extend(text_elements[:100])  # Limit to avoid too many

        # Look for elements with date-like classes
        date_class_elements = soup.find_all(class_=re.compile(r"date|time|event"))
        date_elements.extend(date_class_elements[:50])

        # Remove duplicates while preserving order
        seen = set()
        unique_elements = []
        for elem in date_elements:
            elem_id = id(elem)
            if elem_id not in seen:
                seen.add(elem_id)
                unique_elements.append(elem)

        # Limit to ~200 elements total
        unique_elements = unique_elements[:200]

        for elem in unique_elements:
            try:
                # Extract date
                date_iso = None

                # Try datetime attribute first
                if elem.name == "time" and elem.get("datetime"):
                    date_iso = elem["datetime"][:10]
                else:
                    # Parse text content
                    date_text = elem.get_text()
                    date_iso = parse_date(date_text)

                # Validate date sanity
                if not date_iso or not validate_date_sanity(date_iso):
                    if date_iso:
                        logger.warning(f"Rejecting insane date: {date_iso}")
                    continue

                # Extract city and venue
                city = ""
                venue = ""

                # Look for city in nearby text
                parent_text = elem.parent.get_text() if elem.parent else ""
                grandparent_text = (
                    elem.parent.parent.get_text()
                    if elem.parent and elem.parent.parent
                    else ""
                )

                # Check for metro tokens
                for metro, tokens in METRO_TOKENS.items():
                    for token in tokens:
                        if (
                            token.lower() in parent_text.lower()
                            or token.lower() in grandparent_text.lower()
                        ):
                            city = token
                            break
                    if city:
                        break

                # Extract venue
                venue = extract_venue_from_snippet(
                    parent_text
                ) or extract_venue_from_snippet(grandparent_text)

                # Check for canceled/postponed
                canceled = False
                snippet_text = parent_text or grandparent_text
                if any(
                    word in snippet_text.lower()
                    for word in ["canceled", "cancelled", "postponed", "rescheduled"]
                ):
                    canceled = True

                # Create candidate if we have enough info
                if date_iso and (city or venue):
                    candidate = Candidate(
                        date_iso=date_iso,
                        city=city,
                        venue=venue,
                        url=url,
                        source_type="generic",
                        snippet=snippet_text[:200],
                        canceled=canceled,
                    )
                    candidates.append(candidate)

            except Exception as e:
                logger.debug(f"Error parsing element: {e}")
                continue

    except Exception:
        pass

    return candidates


async def http_get_with_retry(url: str, max_retries: int = 1) -> httpx.Response:
    """HTTP GET with retry logic for 5xx errors."""
    for attempt in range(max_retries + 1):
        try:
            response = await http_client.get(url)
            if response.status_code < 500 or attempt == max_retries:
                return response
            logger.warning(f"5xx error on attempt {attempt + 1}, retrying...")
        except Exception as e:
            if attempt == max_retries:
                raise e
            logger.warning(f"HTTP error on attempt {attempt + 1}, retrying...")

    raise HTTPException(status_code=500, detail="Max retries exceeded")


async def wayback_parse_internal(
    url: str, from_year: int = 2023, limit: int = 2
) -> List[Candidate]:
    """Internal function for Wayback fallback during parse-generic."""
    try:
        # CDX query to get snapshots
        cdx_url = "http://web.archive.org/cdx/search/cdx"
        params = {
            "url": url,
            "from": str(from_year),
            "to": str(datetime.now().year),
            "output": "json",
            "limit": str(limit),
        }

        response = await http_get_with_retry(
            cdx_url, params=params, max_retries=settings.HTTP_MAX_RETRIES
        )
        response.raise_for_status()

        snapshot_data = response.json()
        if not snapshot_data or len(snapshot_data) <= 1:  # First row is headers
            return []

        # Get the latest snapshots
        snapshots = snapshot_data[1 : limit + 1]  # Skip header row
        candidates = []

        for snapshot in snapshots:
            try:
                if len(snapshot) >= 3:
                    timestamp = snapshot[1]  # YYYYMMDDHHMMSS
                    snapshot_url = f"http://web.archive.org/web/{timestamp}/{url}"

                    # Fetch the snapshot
                    snapshot_response = await http_get_with_retry(
                        snapshot_url, max_retries=settings.HTTP_MAX_RETRIES
                    )
                    snapshot_response.raise_for_status()

                    # Parse like generic parser but with internal call
                    snapshot_candidates = await parse_generic_internal(
                        snapshot_url, snapshot_response.text
                    )

                    # Mark as from Wayback
                    for candidate in snapshot_candidates:
                        candidate.source_type = f"wayback_{candidate.source_type}"
                        candidate.url = snapshot_url
                        candidate.source_host = urlparse(url).netloc

                    candidates.extend(snapshot_candidates)

            except Exception as e:
                logger.warning(f"Failed to parse snapshot: {e}")
                continue

        logger.info(
            f"Wayback fallback parsed {len(candidates)} candidates from {len(snapshots)} snapshots"  # noqa: E501
        )
        return candidates

    except Exception as e:
        logger.warning(f"Wayback fallback failed: {e}")
        return []


def belongs_to_metro(city: str, venue: str, metro: str) -> bool:
    """Check if a candidate belongs to the specified metro area."""
    if not city and not venue:
        return False

    tokens = METRO_TOKENS.get(metro, [])

    # Check city against metro tokens
    if city:
        city_lower = city.lower()
        for token in tokens:
            if token.lower() in city_lower:
                return True

    # Check venue against whitelist
    if venue:
        try:
            with open(settings.VENUE_WHITELISTS_PATH) as f:
                whitelists = json.load(f)
                venue_whitelist = whitelists.get(metro, [])
                if venue in venue_whitelist:
                    return True
        except Exception as e:
            logger.warning(f"Failed to load venue whitelist: {e}")

    return False


def infer_source_type(url: str) -> str:
    """Infer source type from URL hostname."""
    hostname = urlparse(url).netloc.lower()

    if "songkick.com" in hostname:
        return "songkick"
    elif "bandsintown.com" in hostname:
        return "bandsintown"
    elif any(
        ticketing in hostname
        for ticketing in ["ticketmaster.com", "axs.com", "eventbrite.com", "dice.fm"]
    ):
        return "ticketing"
    elif "setlist.fm" in hostname:
        return "setlist"
    elif any(
        venue in hostname
        for venue in [
            "theindependent.com",
            "thefillmore.com",
            "greatamericanmusichall.com",
        ]
    ):
        return "venue"
    else:
        return "press"


def extract_venue_from_snippet(snippet: str) -> Optional[str]:
    """Extract venue name from snippet text."""
    # Common patterns
    patterns = [
        r"at\s+([^,\n]+?)(?:\s+in|\s*[,]|\s*$)",
        r"—\s*([^,\n]+?)(?:\s*[,]|\s*$)",
        r"@\s+([^,\n]+?)(?:\s*[,]|\s*$)",
        r"venue[:\s]+([^,\n]+?)(?:\s*[,]|\s*$)",
    ]

    for pattern in patterns:
        match = re.search(pattern, snippet, re.IGNORECASE)
        if match:
            venue = match.group(1).strip()
            if len(venue) > 3 and len(venue) < 100:  # Reasonable venue name length
                return venue

    return None


def is_valid_candidate(candidate: Candidate, metro: str) -> bool:
    """Check if a candidate is valid for selection."""
    # Must have a past date
    try:
        candidate_date = datetime.strptime(candidate.date_iso, "%Y-%m-%d").date()
        if candidate_date > date.today():
            return False
    except Exception:
        return False

    # Must not be canceled
    if candidate.canceled:
        return False

    # Must belong to metro
    return belongs_to_metro(candidate.city, candidate.venue, metro)


def select_latest_candidates(
    candidates: List[Candidate], metro: str
) -> tuple[Optional[Candidate], List[Candidate], List[str]]:
    """Apply deterministic selection rules to find the latest valid candidate."""
    # Filter valid candidates
    valid_candidates = [c for c in candidates if is_valid_candidate(c, metro)]

    if not valid_candidates:
        return None, [], ["no_valid_candidates"]

    # Sort by date (latest first)
    valid_candidates.sort(key=lambda x: x.date_iso, reverse=True)

    # Get the latest date
    latest_date = valid_candidates[0].date_iso
    latest_candidates = [c for c in valid_candidates if c.date_iso == latest_date]

    if len(latest_candidates) == 1:
        # Check if we have other candidates within ±3 days for near-tie consideration
        near_tie_candidates = [latest_candidates[0]]  # Start with the latest
        for candidate in valid_candidates[1:]:  # Check other candidates
            try:
                candidate_date = datetime.strptime(
                    candidate.date_iso, "%Y-%m-%d"
                ).date()
                latest_date_obj = datetime.strptime(latest_date, "%Y-%m-%d").date()
                days_diff = abs((candidate_date - latest_date_obj).days)

                if days_diff <= 3:  # Within 3 days
                    near_tie_candidates.append(candidate)
            except Exception:
                continue

        # If we have multiple candidates in the near-tie window, apply precedence
        if len(near_tie_candidates) > 1:
            near_tie_candidates.sort(
                key=lambda x: SOURCE_PRECEDENCE.get(x.source_type, 0), reverse=True
            )
            winner = near_tie_candidates[0]
            alternates = [c for c in valid_candidates[:4] if c != winner]
            return winner, alternates, ["latest_date", "near_tie_precedence"]

        # Single candidate at latest date
        return latest_candidates[0], valid_candidates[1:4], ["latest_date"]

    # Multiple candidates at latest date - apply precedence
    latest_candidates.sort(
        key=lambda x: SOURCE_PRECEDENCE.get(x.source_type, 0), reverse=True
    )

    # Final tie-breaker: venue in snippet (for same-date candidates)
    for candidate in latest_candidates:
        if candidate.venue and candidate.venue.lower() in candidate.snippet.lower():
            alternates = [c for c in valid_candidates[:4] if c != candidate]
            return (
                candidate,
                alternates,
                ["latest_date", "precedence", "venue_tiebreaker"],
            )

    # Return highest precedence at latest date
    winner = latest_candidates[0]
    alternates = [c for c in valid_candidates[:4] if c != winner]
    return winner, alternates, ["latest_date", "precedence"]


# API endpoints
@app.post("/scrape-songkick", response_model=List[Candidate])
async def scrape_songkick(request: SongkickRequest, _: bool = Depends(verify_api_key)):
    """Scrape Songkick gigography pages for an artist."""
    candidates = []

    # Extract slug from URL if provided
    if request.url:
        slug_match = re.search(
            r"https?://(?:www\.)?songkick\.com/artists/([^/]+)/?", request.url
        )
        if slug_match:
            slug = slug_match.group(1)
            logger.info(f"Extracted slug '{slug}' from URL: {request.url}")
        else:
            raise HTTPException(status_code=400, detail="Invalid Songkick URL format")
    elif request.slug:
        slug = request.slug
    else:
        # Fallback to current auto-slugging with warning
        if not request.artist:
            raise HTTPException(
                status_code=400, detail="Either artist, slug, or url must be provided"
            )
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", request.artist.lower()).strip("-")
        logger.warning(
            f"Auto-generated slug '{slug}' for artist '{request.artist}' - may not work"
        )

    try:
        for page in range(1, min(request.max_pages + 1, 9)):
            url = f"https://www.songkick.com/artists/{slug}/gigography?page={page}"

            try:
                response = await http_get_with_retry(
                    url, max_retries=settings.HTTP_MAX_RETRIES
                )
                response.raise_for_status()

                soup = BeautifulSoup(response.text, "html.parser")

                # Row-scoped parsing: find all <time datetime> tags and extract from their rows  # noqa: E501
                time_tags = soup.find_all("time", attrs={"datetime": True})

                for time_tag in time_tags:
                    try:
                        # Extract candidate from this specific row only using improved classifier
                        try:
                            candidate_data = extract_songkick_row_candidate(
                                time_tag, url, SF_VENUE_WHITELIST_LOWER, NYC_VENUE_WHITELIST_LOWER, logger
                            )
                            
                            # If new classifier fails or returns None, fall back to old logic
                            if not candidate_data:
                                logger.debug("New classifier returned None, falling back to old logic")
                                candidate_data = extract_row_candidate(time_tag, url, request.artist)
                                if candidate_data:
                                    candidate_data["metro"] = None  # Old logic doesn't classify metro
                                else:
                                    continue
                        except Exception as e:
                            logger.warning(f"New classifier failed, falling back to old logic: {e}")
                            candidate_data = extract_row_candidate(time_tag, url, request.artist)
                            if candidate_data:
                                candidate_data["metro"] = None  # Old logic doesn't classify metro
                            else:
                                continue

                        # Validate date sanity
                        if not validate_date_sanity(candidate_data["date_iso"]):
                            logger.warning(
                                f"Rejecting insane date: {candidate_data['date_iso']}"  # noqa: E501
                            )
                            continue

                        # Check for canceled/postponed
                        canceled = any(
                            word in candidate_data["snippet"].lower()
                            for word in [
                                "canceled",
                                "cancelled",
                                "postponed",
                                "rescheduled",
                            ]
                        )

                        # Check for upcoming/presale
                        if any(
                            word in candidate_data["snippet"].lower()
                            for word in ["upcoming", "on sale", "presale", "tickets"]
                        ):
                            continue

                        # Build candidate
                        candidate = Candidate(
                            date_iso=candidate_data["date_iso"],
                            city=candidate_data["city"] or "",  # Ensure city is never None
                            venue=candidate_data["venue"] or "",  # Ensure venue is never None
                            url=candidate_data["url"],
                            source_type=candidate_data["source_type"],
                            snippet=candidate_data["snippet"],
                            canceled=canceled,
                            source_host=candidate_data["source_host"],
                            metro=candidate_data.get("metro"),
                        )

                        # Log per-candidate data at DEBUG level
                        logger.debug(
                            "Candidate parsed",
                            extra={
                                "host": candidate.source_host,
                                "date_iso": candidate.date_iso,
                                "venue": candidate.venue,
                                "city": candidate.city,
                                "url": candidate.url,
                                "metro": candidate.metro,
                            },
                        )

                        candidates.append(candidate)

                    except Exception as e:
                        logger.warning(f"Failed to parse time tag: {e}")
                        continue

                # Fallback: only if no time tags found, try minimal text parsing (demoted)  # noqa: E501
                if not time_tags:
                    # Look for elements with dates, but be more selective to avoid street addresses  # noqa: E501
                    date_elements = []

                    # Look for time elements with datetime attributes (most reliable)
                    time_elements = soup.find_all("time", attrs={"datetime": True})
                    date_elements.extend(time_elements)

                    # Look for elements with date-like classes or IDs
                    date_class_elements = soup.find_all(
                        class_=re.compile(r"date|time|event|gig")
                    )
                    date_elements.extend(date_class_elements[:10])

                    # Look for elements with date-like text patterns (more selective)
                    for elem in soup.find_all(["span", "div", "p"]):
                        # Skip elements that are explicitly address-related
                        if any(
                            cls in (elem.get("class") or [])
                            for cls in [
                                "street-address",
                                "addr",
                                "address",
                                "postal-address",
                            ]
                        ):
                            continue

                        text = elem.get_text().strip()
                        # Only consider elements that look like they contain dates, not addresses  # noqa: E501
                        if re.search(
                            r"\b(?:on|at|playing|performed|shows?|concert|date)\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",  # noqa: E501
                            text,
                            re.IGNORECASE,
                        ) or re.search(
                            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text
                        ):  # noqa: E501
                            # Avoid elements that look like addresses
                            if not re.search(
                                r"\b\d{4}\s+[A-Za-z]+\s+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road)\b",  # noqa: E501
                                text,
                                re.IGNORECASE,
                            ):
                                date_elements.append(elem)
                                if len(date_elements) >= 20:  # Limit to first 20
                                    break

                    # Process the selected elements
                    for elem in date_elements:
                        try:
                            # Extract date from the element
                            date_iso = None
                            if elem.name == "time" and elem.get("datetime"):
                                date_iso = elem["datetime"][:10]
                            else:
                                # Try to parse text content for dates
                                text = elem.get_text()
                                date_iso = parse_date(text)

                            if date_iso and validate_date_sanity(date_iso):
                                # Try to find nearby city/venue info
                                parent = elem.parent
                                if parent:
                                    text = parent.get_text()
                                    city = ""
                                    venue = ""

                                    # Simple city/venue extraction
                                    for token in METRO_TOKENS.get(
                                        "SF", []
                                    ) + METRO_TOKENS.get("NYC", []):
                                        if token.lower() in text.lower():
                                            city = token
                                            break

                                    candidate = Candidate(
                                        date_iso=date_iso,
                                        city=city,
                                        venue=venue,
                                        url=url,
                                        source_type="songkick",
                                        snippet=text[:500],
                                        canceled=False,
                                        source_host=urlparse(url).netloc,
                                        metro=None,  # Fallback parsing doesn't classify metro
                                    )
                                    candidates.append(candidate)
                        except Exception as e:
                            logger.debug(f"Error processing element: {e}")
                            continue

            except Exception as e:
                logger.warning(f"Failed to fetch page {page}: {e}")
                continue

    except Exception as e:
        logger.error(f"Songkick scraping failed: {e}")
        raise HTTPException(
            status_code=500, detail=f"Songkick scraping failed: {str(e)}"  # noqa: E501
        )

    # Deduplicate candidates before returning
    candidates = dedupe_candidates(candidates)

    logger.info(
        f"Scraped {len(candidates)} unique candidates from Songkick for {request.artist}"  # noqa: E501
    )
    return candidates


@app.post("/parse-generic", response_model=List[Candidate])
async def parse_generic(request: ParseRequest, _: bool = Depends(verify_api_key)):
    """Parse arbitrary HTML/URLs into candidate events."""
    candidates = []

    try:
        if request.html:
            html_content = request.html
            source_url = request.url
        else:
            # Fetch the URL with auto-Wayback fallback and retry logic
            try:
                response = await http_get_with_retry(
                    request.url, max_retries=settings.HTTP_MAX_RETRIES
                )
                response.raise_for_status()
                html_content = response.text
                source_url = request.url
            except httpx.HTTPStatusError as e:
                if (
                    e.response.status_code in [403, 429]
                    or e.response.status_code >= 500
                ):
                    logger.info(
                        f"Live fetch failed with {e.response.status_code}, trying Wayback fallback"  # noqa: E501
                    )
                    # Try Wayback fallback
                    wayback_candidates = await wayback_parse_internal(request.url)
                    if wayback_candidates:
                        logger.info(
                            f"Wayback fallback successful, returning {len(wayback_candidates)} candidates"  # noqa: E501
                        )
                        return wayback_candidates

                # Re-raise the error if we can't handle it
                raise HTTPException(
                    status_code=e.response.status_code,
                    detail=f"HTTP {e.response.status_code}: {str(e)}",
                )
            except Exception as e:
                logger.error(f"Unexpected error during live fetch: {e}")
                raise HTTPException(status_code=500, detail=f"Fetch failed: {str(e)}")

        soup = BeautifulSoup(html_content, "html.parser")

        # Parse up to ~200 DOM nodes for dates
        date_elements = []

        # Look for time elements with datetime attributes
        time_elements = soup.find_all("time", attrs={"datetime": True})
        date_elements.extend(time_elements)

        # Look for elements containing dates
        text_elements = soup.find_all(
            ["span", "div", "p", "li"], string=re.compile(r"\d{4}")
        )
        date_elements.extend(text_elements[:100])  # Limit to avoid too many

        # Look for elements with date-like classes
        date_class_elements = soup.find_all(class_=re.compile(r"date|time|event"))
        date_elements.extend(date_class_elements[:50])

        # Remove duplicates while preserving order
        seen = set()
        unique_elements = []
        for elem in date_elements:
            elem_id = id(elem)
            if elem_id not in seen:
                seen.add(elem_id)
                unique_elements.append(elem)

        # Limit to ~200 elements total
        unique_elements = unique_elements[:200]

        for elem in unique_elements:
            try:
                # Extract date - prefer datetime attribute over text parsing
                date_iso = None

                # Try datetime attribute first
                if elem.name == "time" and elem.get("datetime"):
                    date_iso = elem["datetime"][:10]
                else:
                    # Parse text content
                    date_text = elem.get_text()
                    date_iso = parse_date(date_text)

                # Validate date sanity
                if not date_iso or not validate_date_sanity(date_iso):
                    if date_iso:
                        logger.warning(f"Rejecting insane date: {date_iso}")
                    continue

                # Extract city and venue
                city = ""
                venue = ""

                # Look for city in nearby text
                parent_text = elem.parent.get_text() if elem.parent else ""
                grandparent_text = (
                    elem.parent.parent.get_text()
                    if elem.parent and elem.parent.parent
                    else ""
                )

                # Check for metro tokens
                for metro, tokens in METRO_TOKENS.items():
                    for token in tokens:
                        if (
                            token.lower() in parent_text.lower()
                            or token.lower() in grandparent_text.lower()
                        ):
                            city = token
                            break
                    if city:
                        break

                # Extract venue
                venue = extract_venue_from_snippet(
                    parent_text
                ) or extract_venue_from_snippet(grandparent_text)

                # Check for canceled/postponed
                text_content = parent_text + " " + grandparent_text
                canceled = any(
                    word in text_content.lower()
                    for word in ["canceled", "cancelled", "postponed", "rescheduled"]
                )

                # Check for upcoming/presale (skip these)
                if any(
                    word in text_content.lower()
                    for word in ["upcoming", "on sale", "presale", "tickets available"]
                ):
                    continue

                # Create snippet
                snippet = parent_text[:500] if parent_text else elem.get_text()[:500]

                # Infer source type
                source_type = infer_source_type(source_url)

                candidate = Candidate(
                    date_iso=date_iso,
                    city=city,
                    venue=venue,
                    url=source_url,
                    source_type=source_type,
                    snippet=snippet,
                    canceled=canceled,
                    source_host=urlparse(source_url).netloc,
                )

                candidates.append(candidate)

            except Exception as e:
                logger.warning(f"Failed to parse element: {e}")
                continue

        # Deduplicate candidates using the helper function
        candidates = dedupe_candidates(candidates)

        logger.info(f"Parsed {len(candidates)} unique candidates from {source_url}")
        return candidates

    except Exception as e:
        logger.error(f"Generic parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Generic parsing failed: {str(e)}")


@app.get("/wayback-parse", response_model=List[Candidate])
async def wayback_parse(
    url: str,
    from_year: int = 2023,
    to_year: Optional[int] = None,
    limit: int = 2,
    _: bool = Depends(verify_api_key),
):
    """Parse Internet Archive snapshots when live pages fail."""
    if not to_year:
        to_year = datetime.now().year

    candidates = []

    try:
        # CDX query to get snapshots
        cdx_url = "http://web.archive.org/cdx/search/cdx"
        params = {
            "url": url,
            "from": str(from_year),
            "to": str(to_year),
            "output": "json",
            "limit": str(limit),
        }

        response = await http_get_with_retry(
            cdx_url, params=params, max_retries=settings.HTTP_MAX_RETRIES
        )
        response.raise_for_status()

        snapshot_data = response.json()
        if not snapshot_data or len(snapshot_data) <= 1:  # First row is headers
            return []

        # Get the latest snapshots
        snapshots = snapshot_data[1 : limit + 1]  # Skip header row

        for snapshot in snapshots:
            try:
                if len(snapshot) >= 3:
                    timestamp = snapshot[1]  # YYYYMMDDHHMMSS
                    snapshot_url = f"http://web.archive.org/web/{timestamp}/{url}"

                    # Fetch the snapshot
                    snapshot_response = await http_get_with_retry(
                        snapshot_url, max_retries=settings.HTTP_MAX_RETRIES
                    )
                    snapshot_response.raise_for_status()
                    # Parse like generic parser
                    snapshot_candidates = await parse_generic(
                        ParseRequest(url=snapshot_url, html=snapshot_response.text)
                    )

                    # Mark as from Wayback
                    for candidate in snapshot_candidates:
                        candidate.source_type = f"wayback_{candidate.source_type}"
                        candidate.url = snapshot_url

                    candidates.extend(snapshot_candidates)

            except Exception as e:
                logger.warning(f"Failed to parse snapshot: {e}")
                continue

        logger.info(
            f"Parsed {len(candidates)} candidates from {len(snapshots)} Wayback snapshots"  # noqa: E501
        )
        return candidates

    except Exception as e:
        logger.error(f"Wayback parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Wayback parsing failed: {str(e)}")


@app.post("/select-latest", response_model=Any)
async def select_latest(request: SelectRequest, _: bool = Depends(verify_api_key)):
    """Apply deterministic rules to select the most recent show in SF/NYC."""
    if request.metro not in ["SF", "NYC"]:
        raise HTTPException(status_code=400, detail="Metro must be 'SF' or 'NYC'")

    try:
        winner, alternates, decision_path = select_latest_candidates(
            request.candidates, request.metro
        )

        if not winner:
            # No valid candidates found
            alternates_evidence = []
            for alt in request.candidates[:3]:
                alternates_evidence.append(
                    Evidence(
                        url=alt.url, snippet=alt.snippet[:200]  # Limit snippet length
                    )
                )

            # Determine reason for no selection
            if not request.candidates:
                reason = "no_candidates_provided"
            elif not any(c.city or c.venue for c in request.candidates):
                reason = "no_metro_candidates"
            else:
                reason = "no_valid_dates"

            return UnknownResponse(
                alternates=alternates_evidence,
                audit=Audit(
                    decision_path=[reason],
                    candidates_considered=len(request.candidates),
                ),
            )

        # Create evidence from winner
        evidence = [Evidence(url=winner.url, snippet=winner.snippet[:200])]

        # Create alternates evidence
        alternates_evidence = []
        for alt in alternates:
            alternates_evidence.append(Evidence(url=alt.url, snippet=alt.snippet[:200]))

        # Create notes
        notes = Notes(
            canceled=winner.canceled,
            multi_night_series=False,  # Could be enhanced later
        )

        # Create enhanced audit trail
        audit = Audit(
            decision_path=decision_path, candidates_considered=len(request.candidates)
        )

        # Log detailed selection information
        logger.info(
            f"Selection for {request.metro}: decision_path={decision_path}, "  # noqa: E501
            f"candidates_considered={len(request.candidates)}, "  # noqa: E501
            f"best_source_type={winner.source_type}, best_url={winner.url}"  # noqa: E501
        )

        logger.info(
            f"Selected winner for {request.metro}: {winner.venue} on {winner.date_iso}"
        )

        return SelectionResponse(
            metro=request.metro,
            date_iso=winner.date_iso,
            venue=winner.venue,
            city=winner.city,
            evidence=evidence,
            alternates=alternates_evidence,
            notes=notes,
            audit=audit,
        )

    except Exception as e:
        logger.error(f"Selection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Selection failed: {str(e)}")


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/ready")
async def ready_check():
    """Readiness check endpoint for deployment."""
    return {"status": "ready", "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
