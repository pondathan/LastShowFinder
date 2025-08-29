"""
Last-Show Oracle (LSO) - FastAPI service for parsing concert events and selecting latest shows.

This service integrates with Make.com to provide reliable last-show data for Alex's Talent Booker.
"""

import json
import logging
import re
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from setting import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Last-Show Oracle",
    description="Microservice for parsing concert events and selecting latest shows in SF/NYC",
    version="1.0.0"
)

# Load settings
settings = get_settings()

# Metro tokens for SF and NYC
METRO_TOKENS = {
    "SF": ["San Francisco", "SF", "Oakland", "Berkeley", "San Jose", "Palo Alto", 
            "Mountain View", "Santa Clara", "Daly City"],
    "NYC": ["New York", "NYC", "Manhattan", "Brooklyn", "Queens", "Bronx", "Staten Island"]
}

# Source precedence order (higher = more trusted)
SOURCE_PRECEDENCE = {
    "venue": 7,
    "ticketing": 6,
    "artist": 5,
    "setlist": 4,
    "songkick": 3,
    "bandsintown": 2,
    "press": 1
}

# HTTP client with timeouts and retries
http_client = httpx.AsyncClient(
    timeout=settings.HTTP_TIMEOUT_SECONDS,
    limits=httpx.Limits(max_keepalive_connections=settings.HTTP_MAX_HOST_CONCURRENCY)
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

class SongkickRequest(BaseModel):
    artist: str
    slug: Optional[str] = None
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
def parse_date(date_text: str) -> Optional[str]:
    """Parse various date formats to ISO string."""
    if not date_text:
        return None
    
    # Try to extract ISO date from datetime attribute first
    iso_match = re.search(r'(\d{4}-\d{2}-\d{2})', date_text)
    if iso_match:
        return iso_match.group(1)
    
    # Try to parse common date formats
    try:
        # Remove common prefixes/suffixes
        clean_text = re.sub(r'(on|at|playing|performed|shows?|concert)', '', date_text, flags=re.IGNORECASE)
        clean_text = clean_text.strip()
        
        # Try parsing with dateutil
        parsed_date = date_parser.parse(clean_text, fuzzy=True)
        if parsed_date:
            return parsed_date.strftime("%Y-%m-%d")
    except:
        pass
    
    return None

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
    elif any(ticketing in hostname for ticketing in ["ticketmaster.com", "axs.com", "eventbrite.com", "dice.fm"]):
        return "ticketing"
    elif "setlist.fm" in hostname:
        return "setlist"
    elif any(venue in hostname for venue in ["theindependent.com", "thefillmore.com", "greatamericanmusichall.com"]):
        return "venue"
    else:
        return "press"

def extract_venue_from_snippet(snippet: str) -> Optional[str]:
    """Extract venue name from snippet text."""
    # Common patterns
    patterns = [
        r'at\s+([^,\n]+?)(?:\s+in|\s*[,]|\s*$)',
        r'—\s*([^,\n]+?)(?:\s*[,]|\s*$)',
        r'@\s+([^,\n]+?)(?:\s*[,]|\s*$)',
        r'venue[:\s]+([^,\n]+?)(?:\s*[,]|\s*$)'
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
    except:
        return False
    
    # Must not be canceled
    if candidate.canceled:
        return False
    
    # Must belong to metro
    return belongs_to_metro(candidate.city, candidate.venue, metro)

def select_latest_candidates(candidates: List[Candidate], metro: str) -> tuple[Optional[Candidate], List[Candidate], List[str]]:
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
        return latest_candidates[0], valid_candidates[1:4], ["latest_date"]
    
    # Multiple candidates at latest date - apply precedence
    latest_candidates.sort(key=lambda x: SOURCE_PRECEDENCE.get(x.source_type, 0), reverse=True)
    
    # Check for near-tie window (±3 days)
    near_tie_candidates = []
    for candidate in valid_candidates:
        try:
            candidate_date = datetime.strptime(candidate.date_iso, "%Y-%m-%d").date()
            latest_date_obj = datetime.strptime(latest_date, "%Y-%m-%d").date()
            days_diff = abs((candidate_date - latest_date_obj).days)
            
            if days_diff <= 3:
                near_tie_candidates.append(candidate)
        except:
            continue
    
    # Prefer higher precedence within near-tie window
    if near_tie_candidates:
        near_tie_candidates.sort(key=lambda x: SOURCE_PRECEDENCE.get(x.source_type, 0), reverse=True)
        winner = near_tie_candidates[0]
        alternates = [c for c in valid_candidates[:4] if c != winner]
        return winner, alternates, ["latest_date", "near_tie_precedence"]
    
    # Final tie-breaker: venue in snippet
    for candidate in latest_candidates:
        if candidate.venue and candidate.venue.lower() in candidate.snippet.lower():
            alternates = [c for c in valid_candidates[:4] if c != candidate]
            return candidate, alternates, ["latest_date", "precedence", "venue_tiebreaker"]
    
    # Return highest precedence at latest date
    winner = latest_candidates[0]
    alternates = [c for c in valid_candidates[:4] if c != winner]
    return winner, alternates, ["latest_date", "precedence"]

# API endpoints
@app.post("/scrape-songkick", response_model=List[Candidate])
async def scrape_songkick(request: SongkickRequest):
    """Scrape Songkick gigography pages for an artist."""
    candidates = []
    
    # Generate slug if not provided
    if not request.slug:
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', request.artist.lower()).strip('-')
    else:
        slug = request.slug
    
    try:
        for page in range(1, min(request.max_pages + 1, 9)):
            url = f"https://www.songkick.com/artists/{slug}/gigography?page={page}"
            
            try:
                response = await http_client.get(url)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Look for gig items
                gig_items = soup.find_all('li', class_='gig-item') or soup.find_all('div', class_='gig-item')
                
                for item in gig_items:
                    try:
                        # Extract date
                        date_elem = item.find('time', attrs={'datetime': True})
                        if date_elem:
                            date_iso = date_elem['datetime'][:10]  # YYYY-MM-DD
                        else:
                            # Try to find date in text
                            date_text = item.get_text()
                            date_iso = parse_date(date_text)
                            if not date_iso:
                                continue
                        
                        # Extract city and venue
                        city_elem = item.find('span', class_='city') or item.find('a', class_='city')
                        city = city_elem.get_text().strip() if city_elem else ""
                        
                        venue_elem = item.find('span', class_='venue') or item.find('a', class_='venue')
                        venue = venue_elem.get_text().strip() if venue_elem else ""
                        
                        # Extract URL
                        link_elem = item.find('a', href=True)
                        url = f"https://www.songkick.com{link_elem['href']}" if link_elem else ""
                        
                        # Extract snippet
                        snippet = item.get_text()[:500]  # Limit snippet length
                        
                        # Check for canceled/postponed
                        canceled = any(word in snippet.lower() for word in ['canceled', 'cancelled', 'postponed', 'rescheduled'])
                        
                        # Check for upcoming/presale
                        if any(word in snippet.lower() for word in ['upcoming', 'on sale', 'presale', 'tickets']):
                            continue
                        
                        candidate = Candidate(
                            date_iso=date_iso,
                            city=city,
                            venue=venue,
                            url=url,
                            source_type="songkick",
                            snippet=snippet,
                            canceled=canceled
                        )
                        
                        candidates.append(candidate)
                        
                    except Exception as e:
                        logger.warning(f"Failed to parse gig item: {e}")
                        continue
                
                # If no gig items found, try alternative selectors
                if not gig_items:
                    # Look for any elements with dates
                    date_elements = soup.find_all(['time', 'span', 'div'], string=re.compile(r'\d{4}'))
                    for elem in date_elements[:20]:  # Limit to first 20
                        try:
                            date_text = elem.get_text()
                            date_iso = parse_date(date_text)
                            if date_iso:
                                # Try to find nearby city/venue info
                                parent = elem.parent
                                if parent:
                                    text = parent.get_text()
                                    city = ""
                                    venue = ""
                                    
                                    # Simple city/venue extraction
                                    for token in METRO_TOKENS.get("SF", []) + METRO_TOKENS.get("NYC", []):
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
                                        canceled=False
                                    )
                                    candidates.append(candidate)
                        except:
                            continue
                
            except Exception as e:
                logger.warning(f"Failed to fetch page {page}: {e}")
                continue
                
    except Exception as e:
        logger.error(f"Songkick scraping failed: {e}")
        raise HTTPException(status_code=500, detail=f"Songkick scraping failed: {str(e)}")
    
    logger.info(f"Scraped {len(candidates)} candidates from Songkick for {request.artist}")
    return candidates

@app.post("/parse-generic", response_model=List[Candidate])
async def parse_generic(request: ParseRequest):
    """Parse arbitrary HTML/URLs into candidate events."""
    candidates = []
    
    try:
        if request.html:
            html_content = request.html
            source_url = request.url
        else:
            # Fetch the URL
            response = await http_client.get(request.url)
            response.raise_for_status()
            html_content = response.text
            source_url = request.url
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Parse up to ~200 DOM nodes for dates
        date_elements = []
        
        # Look for time elements with datetime attributes
        time_elements = soup.find_all('time', attrs={'datetime': True})
        date_elements.extend(time_elements)
        
        # Look for elements containing dates
        text_elements = soup.find_all(['span', 'div', 'p', 'li'], string=re.compile(r'\d{4}'))
        date_elements.extend(text_elements[:100])  # Limit to avoid too many
        
        # Look for elements with date-like classes
        date_class_elements = soup.find_all(class_=re.compile(r'date|time|event'))
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
                if elem.name == 'time' and elem.get('datetime'):
                    date_iso = elem['datetime'][:10]
                else:
                    # Parse text content
                    date_text = elem.get_text()
                    date_iso = parse_date(date_text)
                
                if not date_iso:
                    continue
                
                # Extract city and venue
                city = ""
                venue = ""
                
                # Look for city in nearby text
                parent_text = elem.parent.get_text() if elem.parent else ""
                grandparent_text = elem.parent.parent.get_text() if elem.parent and elem.parent.parent else ""
                
                # Check for metro tokens
                for metro, tokens in METRO_TOKENS.items():
                    for token in tokens:
                        if token.lower() in parent_text.lower() or token.lower() in grandparent_text.lower():
                            city = token
                            break
                    if city:
                        break
                
                # Extract venue
                venue = extract_venue_from_snippet(parent_text) or extract_venue_from_snippet(grandparent_text)
                
                # Check for canceled/postponed
                text_content = parent_text + " " + grandparent_text
                canceled = any(word in text_content.lower() for word in ['canceled', 'cancelled', 'postponed', 'rescheduled'])
                
                # Check for upcoming/presale (skip these)
                if any(word in text_content.lower() for word in ['upcoming', 'on sale', 'presale', 'tickets available']):
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
                    canceled=canceled
                )
                
                candidates.append(candidate)
                
            except Exception as e:
                logger.warning(f"Failed to parse element: {e}")
                continue
        
        # Remove duplicates based on date + city + venue
        unique_candidates = []
        seen_combinations = set()
        for candidate in candidates:
            combo = (candidate.date_iso, candidate.city, candidate.venue)
            if combo not in seen_combinations:
                seen_combinations.add(combo)
                unique_candidates.append(candidate)
        
        logger.info(f"Parsed {len(unique_candidates)} unique candidates from {source_url}")
        return unique_candidates
        
    except Exception as e:
        logger.error(f"Generic parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Generic parsing failed: {str(e)}")

@app.get("/wayback-parse", response_model=List[Candidate])
async def wayback_parse(url: str, from_year: int = 2023, to_year: Optional[int] = None, limit: int = 2):
    """Parse Internet Archive snapshots when live pages fail."""
    if not to_year:
        to_year = datetime.now().year
    
    candidates = []
    
    try:
        # CDX query to get snapshots
        cdx_url = f"http://web.archive.org/cdx/search/cdx"
        params = {
            "url": url,
            "from": str(from_year),
            "to": str(to_year),
            "output": "json",
            "limit": str(limit)
        }
        
        response = await http_client.get(cdx_url, params=params)
        response.raise_for_status()
        
        snapshot_data = response.json()
        if not snapshot_data or len(snapshot_data) <= 1:  # First row is headers
            return []
        
        # Get the latest snapshots
        snapshots = snapshot_data[1:limit+1]  # Skip header row
        
        for snapshot in snapshots:
            try:
                if len(snapshot) >= 3:
                    timestamp = snapshot[1]  # YYYYMMDDHHMMSS
                    snapshot_url = f"http://web.archive.org/web/{timestamp}/{url}"
                    
                    # Fetch the snapshot
                    snapshot_response = await http_client.get(snapshot_url)
                    snapshot_response.raise_for_status()
                    
                    # Parse like generic parser
                    snapshot_candidates = await parse_generic(ParseRequest(
                        url=snapshot_url,
                        html=snapshot_response.text
                    ))
                    
                    # Mark as from Wayback
                    for candidate in snapshot_candidates:
                        candidate.source_type = f"wayback_{candidate.source_type}"
                        candidate.url = snapshot_url
                    
                    candidates.extend(snapshot_candidates)
                    
            except Exception as e:
                logger.warning(f"Failed to parse snapshot: {e}")
                continue
        
        logger.info(f"Parsed {len(candidates)} candidates from {len(snapshots)} Wayback snapshots")
        return candidates
        
    except Exception as e:
        logger.error(f"Wayback parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Wayback parsing failed: {str(e)}")

@app.post("/select-latest", response_model=Any)
async def select_latest(request: SelectRequest):
    """Apply deterministic rules to select the most recent show in SF/NYC."""
    if request.metro not in ["SF", "NYC"]:
        raise HTTPException(status_code=400, detail="Metro must be 'SF' or 'NYC'")
    
    try:
        winner, alternates, decision_path = select_latest_candidates(request.candidates, request.metro)
        
        if not winner:
            # No valid candidates found
            alternates_evidence = []
            for alt in request.candidates[:3]:
                alternates_evidence.append(Evidence(
                    url=alt.url,
                    snippet=alt.snippet[:200]  # Limit snippet length
                ))
            
            return UnknownResponse(
                alternates=alternates_evidence,
                audit=Audit(
                    decision_path=decision_path,
                    candidates_considered=len(request.candidates)
                )
            )
        
        # Create evidence from winner
        evidence = [Evidence(
            url=winner.url,
            snippet=winner.snippet[:200]
        )]
        
        # Create alternates evidence
        alternates_evidence = []
        for alt in alternates:
            alternates_evidence.append(Evidence(
                url=alt.url,
                snippet=alt.snippet[:200]
            ))
        
        # Create notes
        notes = Notes(
            canceled=winner.canceled,
            multi_night_series=False  # Could be enhanced later
        )
        
        # Create audit trail
        audit = Audit(
            decision_path=decision_path,
            candidates_considered=len(request.candidates)
        )
        
        logger.info(f"Selected winner for {request.metro}: {winner.venue} on {winner.date_iso}")
        
        return SelectionResponse(
            metro=request.metro,
            date_iso=winner.date_iso,
            venue=winner.venue,
            city=winner.city,
            evidence=evidence,
            alternates=alternates_evidence,
            notes=notes,
            audit=audit
        )
        
    except Exception as e:
        logger.error(f"Selection failed: {e}")
        raise HTTPException(status_code=500, detail=f"Selection failed: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.on_event("startup")
async def startup_event():
    """Initialize the service on startup."""
    logger.info("Last-Show Oracle starting up...")
    
    # Load venue whitelists to validate config
    try:
        with open(settings.VENUE_WHITELISTS_PATH) as f:
            whitelists = json.load(f)
            logger.info(f"Loaded venue whitelists: {list(whitelists.keys())}")
    except Exception as e:
        logger.error(f"Failed to load venue whitelists: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Last-Show Oracle shutting down...")
    await http_client.aclose()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
