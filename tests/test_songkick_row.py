import pytest
from songkick_row_classification import (
    classify_city_state_from_text,
    fallback_tokens_to_metro,
    extract_songkick_row_candidate,
)
from bs4 import BeautifulSoup


class TestSongkickRowClassification:
    """Test the Songkick row classification module."""

    @pytest.mark.parametrize(
        "txt,expect",
        [
            ("Brooklyn, NY, US", ("NYC", "Brooklyn, NY")),
            ("Manhattan, NY", ("NYC", "Manhattan, NY")),
            ("New York, NY, USA", ("NYC", "New York, NY")),
            ("Queens, NY", ("NYC", "Queens, NY")),
            ("Albany, NY", (None, "Albany, NY")),  # not NYC
            ("San Francisco, CA", ("SF", "San Francisco, CA")),
            ("Oakland, CA", ("SF", "Oakland, CA")),
            ("Palo Alto, CA", ("SF", "Palo Alto, CA")),
            ("Los Angeles, CA", (None, "Los Angeles, CA")),  # not SF
        ],
    )
    def test_city_state_parsing(self, txt, expect):
        """Test city/state parsing for metro classification."""
        result = classify_city_state_from_text(txt)
        assert result == expect

    @pytest.mark.parametrize(
        "txt,expect",
        [
            ("Live in BKLYN — NY — US", "NYC"),
            ("NYC show tonight", "NYC"),
            ("Bay Area headline — San Francisco", "SF"),
            ("Buffalo, NY", None),  # upstate NY, not NYC
            ("Brooklyn tonight", "NYC"),
            ("Manhattan show", "NYC"),
            ("Oakland venue", "SF"),
            ("Berkeley concert", "SF"),
            ("San Jose gig", "SF"),
            ("Albany, NY", None),  # upstate NY, not NYC
        ],
    )
    def test_token_fallback(self, txt, expect):
        """Test token fallback classification."""
        result = fallback_tokens_to_metro(txt)
        assert result == expect

    def test_extract_songkick_row_candidate_with_brooklyn(self):
        """Test extraction from a row with Brooklyn, NY."""
        html = """
        <li class="gig-item">
            <time datetime="2024-03-15">March 15, 2024</time>
            <span class="city">Music Hall of Williamsburg, Brooklyn, NY, US</span>
            <a href="/venues/12345" class="venue">Music Hall of Williamsburg</a>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        time_tag = soup.find("time")

        result = extract_songkick_row_candidate(
            time_tag,
            "https://example.com",
            set(),  # empty SF whitelist
            {"music hall of williamsburg"},  # NYC whitelist
            None,  # no logger
        )

        assert result is not None
        assert result["date_iso"] == "2024-03-15"
        assert result["metro"] == "NYC"
        assert "Brooklyn, NY" in result["city"]
        assert result["venue"] == "Music Hall of Williamsburg"

    def test_extract_songkick_row_candidate_with_albany(self):
        """Test extraction from a row with Albany, NY (should not be NYC)."""
        html = """
        <li class="gig-item">
            <time datetime="2024-03-15">March 15, 2024</time>
            <span class="city">Lark Hall, Albany, NY, US 351 Hudson Ave.</span>
            <a href="/venues/67890" class="venue">Lark Hall</a>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        time_tag = soup.find("time")

        result = extract_songkick_row_candidate(
            time_tag,
            "https://example.com",
            set(),  # empty SF whitelist
            set(),  # empty NYC whitelist
            None,  # no logger
        )

        assert result is not None
        assert result["date_iso"] == "2024-03-15"
        assert result["metro"] is None  # Albany is not NYC metro
        assert "Albany, NY" in result["city"]
        assert result["venue"] == "Lark Hall"

    def test_extract_songkick_row_candidate_with_sf(self):
        """Test extraction from a row with San Francisco, CA."""
        html = """
        <li class="gig-item">
            <time datetime="2024-03-15">March 15, 2024</time>
            <span class="city">The Independent, San Francisco, CA, US</span>
            <a href="/venues/11111" class="venue">The Independent</a>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        time_tag = soup.find("time")

        result = extract_songkick_row_candidate(
            time_tag,
            "https://example.com",
            {"the independent"},  # SF whitelist
            set(),  # empty NYC whitelist
            None,  # no logger
        )

        assert result is not None
        assert result["date_iso"] == "2024-03-15"
        assert result["metro"] == "SF"
        assert "San Francisco, CA" in result["city"]
        assert result["venue"] == "The Independent"

    def test_venue_whitelist_rescue(self):
        """Test that venue whitelist can rescue metro classification."""
        html = """
        <li class="gig-item">
            <time datetime="2024-03-15">March 15, 2024</time>
            <span class="city">Some Venue, Some City, ST</span>
            <a href="/venues/22222" class="venue">Brooklyn Steel</a>
        </li>
        """
        soup = BeautifulSoup(html, "html.parser")
        time_tag = soup.find("time")

        result = extract_songkick_row_candidate(
            time_tag,
            "https://example.com",
            set(),  # empty SF whitelist
            {"brooklyn steel"},  # NYC whitelist
            None,  # no logger
        )

        assert result is not None
        assert result["date_iso"] == "2024-03-15"
        assert result["metro"] == "NYC"  # rescued by venue whitelist
        assert result["venue"] == "Brooklyn Steel"
