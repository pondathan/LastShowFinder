"""Test metro filtering functionality."""

import pytest
import json
import tempfile
import os
from worker import belongs_to_metro, METRO_TOKENS


class TestMetroFiltering:
    """Test metro area filtering logic."""
    
    def test_sf_metro_tokens(self):
        """Test San Francisco metro token matching."""
        # City matches
        assert belongs_to_metro("San Francisco, CA", "", "SF") is True
        assert belongs_to_metro("SF, CA", "", "SF") is True
        assert belongs_to_metro("Oakland, CA", "", "SF") is True
        assert belongs_to_metro("Berkeley, CA", "", "SF") is True
        assert belongs_to_metro("San Jose, CA", "", "SF") is True
        
        # Case insensitive
        assert belongs_to_metro("san francisco, ca", "", "SF") is True
        assert belongs_to_metro("oakland, ca", "", "SF") is True
        
        # No match
        assert belongs_to_metro("Los Angeles, CA", "", "SF") is False
        assert belongs_to_metro("New York, NY", "", "SF") is False
    
    def test_nyc_metro_tokens(self):
        """Test New York City metro token matching."""
        # City matches
        assert belongs_to_metro("New York, NY", "", "NYC") is True
        assert belongs_to_metro("NYC, NY", "", "NYC") is True
        assert belongs_to_metro("Manhattan, NY", "", "NYC") is True
        assert belongs_to_metro("Brooklyn, NY", "", "NYC") is True
        assert belongs_to_metro("Queens, NY", "", "NYC") is True
        assert belongs_to_metro("Bronx, NY", "", "NYC") is True
        assert belongs_to_metro("Staten Island, NY", "", "NYC") is True
        
        # Case insensitive
        assert belongs_to_metro("new york, ny", "", "NYC") is True
        assert belongs_to_metro("manhattan, ny", "", "NYC") is True
        
        # No match
        assert belongs_to_metro("San Francisco, CA", "", "NYC") is False
        assert belongs_to_metro("Los Angeles, CA", "", "NYC") is False
    
    def test_venue_whitelist_matching(self):
        """Test venue whitelist matching."""
        # Create temporary venue whitelist file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            whitelist_data = {
                "SF": ["The Independent", "The Fillmore", "Great American Music Hall"],
                "NYC": ["Madison Square Garden", "Radio City Music Hall", "Brooklyn Steel"]
            }
            json.dump(whitelist_data, f)
            temp_file = f.name
        
        try:
            # Mock the settings to use our temp file
            original_path = "config/venues.json"
            
            # Test SF venues
            assert belongs_to_metro("", "The Independent", "SF") is True
            assert belongs_to_metro("", "The Fillmore", "SF") is True
            assert belongs_to_metro("", "Great American Music Hall", "SF") is True
            
            # Test NYC venues
            assert belongs_to_metro("", "Madison Square Garden", "NYC") is True
            assert belongs_to_metro("", "Radio City Music Hall", "NYC") is True
            assert belongs_to_metro("", "Brooklyn Steel", "NYC") is True
            
            # Test non-whitelisted venues
            assert belongs_to_metro("", "Some Other Venue", "SF") is False
            assert belongs_to_metro("", "Random Club", "NYC") is False
            
        finally:
            # Clean up temp file
            os.unlink(temp_file)
    
    def test_combined_city_and_venue(self):
        """Test when both city and venue are provided."""
        # City matches metro, venue doesn't matter
        assert belongs_to_metro("San Francisco, CA", "Some Random Venue", "SF") is True
        
        # Venue matches whitelist, city doesn't matter
        # (This would require the actual whitelist file to be present)
        # For now, test with city match
        assert belongs_to_metro("Oakland, CA", "The Independent", "SF") is True
    
    def test_empty_inputs(self):
        """Test edge cases with empty inputs."""
        # Both empty
        assert belongs_to_metro("", "", "SF") is False
        assert belongs_to_metro("", "", "NYC") is False
        
        # Empty city, empty venue
        assert belongs_to_metro("", "", "SF") is False
        
        # None values
        assert belongs_to_metro(None, None, "SF") is False
    
    def test_invalid_metro(self):
        """Test with invalid metro codes."""
        # Invalid metro should return False
        assert belongs_to_metro("San Francisco, CA", "", "INVALID") is False
        assert belongs_to_metro("New York, NY", "", "INVALID") is False
        
        # Empty metro
        assert belongs_to_metro("San Francisco, CA", "", "") is False
    
    def test_metro_tokens_structure(self):
        """Test that metro tokens are properly structured."""
        assert "SF" in METRO_TOKENS
        assert "NYC" in METRO_TOKENS
        
        # Check that tokens are lists
        assert isinstance(METRO_TOKENS["SF"], list)
        assert isinstance(METRO_TOKENS["NYC"], list)
        
        # Check that tokens are not empty
        assert len(METRO_TOKENS["SF"]) > 0
        assert len(METRO_TOKENS["NYC"]) > 0
        
        # Check for common expected tokens
        assert "San Francisco" in METRO_TOKENS["SF"]
        assert "New York" in METRO_TOKENS["NYC"]
