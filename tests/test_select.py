"""Test selection logic and deterministic rules."""

import pytest
from datetime import datetime, date
from worker import (
    select_latest_candidates, 
    is_valid_candidate, 
    SOURCE_PRECEDENCE,
    Candidate
)


class TestSelectionLogic:
    """Test the deterministic selection logic."""
    
    def test_source_precedence_order(self):
        """Test that source precedence is correctly ordered."""
        # Higher numbers should mean higher precedence
        assert SOURCE_PRECEDENCE["venue"] > SOURCE_PRECEDENCE["ticketing"]
        assert SOURCE_PRECEDENCE["ticketing"] > SOURCE_PRECEDENCE["artist"]
        assert SOURCE_PRECEDENCE["artist"] > SOURCE_PRECEDENCE["setlist"]
        assert SOURCE_PRECEDENCE["setlist"] > SOURCE_PRECEDENCE["songkick"]
        assert SOURCE_PRECEDENCE["songkick"] > SOURCE_PRECEDENCE["bandsintown"]
        assert SOURCE_PRECEDENCE["bandsintown"] > SOURCE_PRECEDENCE["press"]
        
        # Verify all expected source types are present
        expected_sources = ["venue", "ticketing", "artist", "setlist", "songkick", "bandsintown", "press"]
        for source in expected_sources:
            assert source in SOURCE_PRECEDENCE
    
    def test_candidate_validation(self):
        """Test candidate validation logic."""
        today = date.today()
        yesterday = date.fromordinal(today.toordinal() - 1)
        tomorrow = date.fromordinal(today.toordinal() + 1)
        
        # Valid candidate
        valid_candidate = Candidate(
            date_iso=yesterday.strftime("%Y-%m-%d"),
            city="San Francisco, CA",
            venue="The Independent",
            url="https://example.com",
            source_type="venue",
            snippet="Played at The Independent in San Francisco",
            canceled=False
        )
        assert is_valid_candidate(valid_candidate, "SF") is True
        
        # Future date (invalid)
        future_candidate = Candidate(
            date_iso=tomorrow.strftime("%Y-%m-%d"),
            city="San Francisco, CA",
            venue="The Independent",
            url="https://example.com",
            source_type="venue",
            snippet="Playing at The Independent in San Francisco",
            canceled=False
        )
        assert is_valid_candidate(future_candidate, "SF") is False
        
        # Canceled (invalid)
        canceled_candidate = Candidate(
            date_iso=yesterday.strftime("%Y-%m-%d"),
            city="San Francisco, CA",
            venue="The Independent",
            url="https://example.com",
            source_type="venue",
            snippet="Canceled show at The Independent in San Francisco",
            canceled=True
        )
        assert is_valid_candidate(canceled_candidate, "SF") is False
        
        # Wrong metro (invalid)
        wrong_metro_candidate = Candidate(
            date_iso=yesterday.strftime("%Y-%m-%d"),
            city="Los Angeles, CA",
            venue="Some Venue",
            url="https://example.com",
            source_type="venue",
            snippet="Played in Los Angeles",
            canceled=False
        )
        assert is_valid_candidate(wrong_metro_candidate, "SF") is False
    
    def test_latest_date_selection(self):
        """Test that the latest date is always selected."""
        candidates = [
            Candidate(
                date_iso="2024-01-15",
                city="San Francisco, CA",
                venue="The Independent",
                url="https://example.com/1",
                source_type="venue",
                snippet="January show",
                canceled=False
            ),
            Candidate(
                date_iso="2024-02-15",
                city="San Francisco, CA",
                venue="The Fillmore",
                url="https://example.com/2",
                source_type="ticketing",
                snippet="February show",
                canceled=False
            ),
            Candidate(
                date_iso="2024-03-15",
                city="San Francisco, CA",
                venue="Great American Music Hall",
                url="https://example.com/3",
                source_type="press",
                snippet="March show",
                canceled=False
            )
        ]
        
        winner, alternates, decision_path = select_latest_candidates(candidates, "SF")
        
        assert winner is not None
        assert winner.date_iso == "2024-03-15"  # Latest date
        assert "latest_date" in decision_path
        assert len(alternates) > 0
    
    def test_source_precedence_tiebreaker(self):
        """Test source precedence when dates are the same."""
        same_date = "2024-01-15"
        candidates = [
            Candidate(
                date_iso=same_date,
                city="San Francisco, CA",
                venue="The Independent",
                url="https://example.com/1",
                source_type="press",  # Lowest precedence
                snippet="Press review",
                canceled=False
            ),
            Candidate(
                date_iso=same_date,
                city="San Francisco, CA",
                venue="The Independent",
                url="https://example.com/2",
                source_type="venue",  # Highest precedence
                snippet="Venue listing",
                canceled=False
            ),
            Candidate(
                date_iso=same_date,
                city="San Francisco, CA",
                venue="The Independent",
                url="https://example.com/3",
                source_type="ticketing",  # Medium precedence
                snippet="Ticket info",
                canceled=False
            )
        ]
        
        winner, alternates, decision_path = select_latest_candidates(candidates, "SF")
        
        assert winner is not None
        assert winner.source_type == "venue"  # Highest precedence should win
        assert "precedence" in decision_path
    
    def test_near_tie_window(self):
        """Test near-tie window (±3 days) preference for higher precedence."""
        candidates = [
            Candidate(
                date_iso="2024-01-15",
                city="San Francisco, CA",
                venue="The Independent",
                url="https://example.com/1",
                source_type="press",  # Lower precedence
                snippet="January 15 show",
                canceled=False
            ),
            Candidate(
                date_iso="2024-01-18",  # 3 days later
                city="San Francisco, CA",
                venue="The Fillmore",
                url="https://example.com/2",
                source_type="venue",  # Higher precedence
                snippet="January 18 show",
                canceled=False
            )
        ]
        
        winner, alternates, decision_path = select_latest_candidates(candidates, "SF")
        
        assert winner is not None
        # Should prefer higher precedence within ±3 days
        assert winner.source_type == "venue"
        assert "near_tie_precedence" in decision_path
    
    def test_venue_tiebreaker(self):
        """Test venue-in-snippet tiebreaker."""
        same_date = "2024-01-15"
        candidates = [
            Candidate(
                date_iso=same_date,
                city="San Francisco, CA",
                venue="The Independent",
                url="https://example.com/1",
                source_type="press",
                snippet="Show at The Independent",  # Contains venue name
                canceled=False
            ),
            Candidate(
                date_iso=same_date,
                city="San Francisco, CA",
                venue="The Fillmore",
                url="https://example.com/2",
                source_type="press",
                snippet="Great show in San Francisco",  # No venue name
                canceled=False
            )
        ]
        
        winner, alternates, decision_path = select_latest_candidates(candidates, "SF")
        
        assert winner is not None
        # Should prefer candidate with venue in snippet
        assert winner.venue == "The Independent"
        assert "venue_tiebreaker" in decision_path
    
    def test_no_valid_candidates(self):
        """Test handling when no valid candidates exist."""
        # All candidates are invalid (future dates)
        future_date = date.fromordinal(date.today().toordinal() + 30).strftime("%Y-%m-%d")
        candidates = [
            Candidate(
                date_iso=future_date,
                city="San Francisco, CA",
                venue="The Independent",
                url="https://example.com/1",
                source_type="venue",
                snippet="Future show",
                canceled=False
            )
        ]
        
        winner, alternates, decision_path = select_latest_candidates(candidates, "SF")
        
        assert winner is None
        assert len(alternates) == 0
        assert "no_valid_candidates" in decision_path
    
    def test_mixed_valid_invalid_candidates(self):
        """Test selection when some candidates are invalid."""
        today = date.today()
        yesterday = date.fromordinal(today.toordinal() - 1)
        tomorrow = date.fromordinal(today.toordinal() + 1)
        
        candidates = [
            Candidate(
                date_iso=yesterday.strftime("%Y-%m-%d"),
                city="San Francisco, CA",
                venue="The Independent",
                url="https://example.com/1",
                source_type="venue",
                snippet="Valid past show",
                canceled=False
            ),
            Candidate(
                date_iso=tomorrow.strftime("%Y-%m-%d"),
                city="San Francisco, CA",
                venue="The Fillmore",
                url="https://example.com/2",
                source_type="venue",
                snippet="Invalid future show",
                canceled=False
            ),
            Candidate(
                date_iso=yesterday.strftime("%Y-%m-%d"),
                city="Los Angeles, CA",  # Wrong metro
                venue="Some Venue",
                url="https://example.com/3",
                source_type="venue",
                snippet="Wrong metro show",
                canceled=False
            )
        ]
        
        winner, alternates, decision_path = select_latest_candidates(candidates, "SF")
        
        # Should only consider the valid SF candidate
        assert winner is not None
        assert winner.city == "San Francisco, CA"
        assert len(alternates) == 0  # Only one valid candidate
    
    def test_alternates_limit(self):
        """Test that alternates are limited appropriately."""
        # Create many valid candidates
        candidates = []
        for i in range(10):
            date_obj = date.fromordinal(date.today().toordinal() - i - 1)
            candidates.append(Candidate(
                date_iso=date_obj.strftime("%Y-%m-%d"),
                city="San Francisco, CA",
                venue=f"Venue {i}",
                url=f"https://example.com/{i}",
                source_type="venue",
                snippet=f"Show {i}",
                canceled=False
            ))
        
        winner, alternates, decision_path = select_latest_candidates(candidates, "SF")
        
        assert winner is not None
        # Should have alternates but limited (implementation detail)
        assert len(alternates) > 0
        assert len(alternates) <= 4  # Based on current implementation
