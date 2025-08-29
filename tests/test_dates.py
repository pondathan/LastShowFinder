"""Test date parsing functionality."""

import pytest
from datetime import datetime, date
from worker import parse_date


class TestDateParsing:
    """Test various date parsing scenarios."""
    
    def test_iso_date_extraction(self):
        """Test extraction of ISO dates from datetime attributes."""
        # ISO date in datetime attribute
        assert parse_date('<time datetime="2024-01-15">January 15, 2024</time>') == "2024-01-15"
        
        # ISO date in text
        assert parse_date("2024-01-15") == "2024-01-15"
        assert parse_date("Event on 2024-01-15") == "2024-01-15"
    
    def test_us_date_formats(self):
        """Test US date formats."""
        assert parse_date("January 15, 2024") == "2024-01-15"
        assert parse_date("Jan 15, 2024") == "2024-01-15"
        assert parse_date("1/15/2024") == "2024-01-15"
        assert parse_date("01/15/2024") == "2024-01-15"
    
    def test_eu_date_formats(self):
        """Test European date formats."""
        assert parse_date("15 January 2024") == "2024-01-15"
        assert parse_date("15 Jan 2024") == "2024-01-15"
        assert parse_date("15/1/2024") == "2024-01-15"
        assert parse_date("15/01/2024") == "2024-01-15"
    
    def test_date_with_prefixes(self):
        """Test dates with common prefixes that should be removed."""
        assert parse_date("on January 15, 2024") == "2024-01-15"
        assert parse_date("at January 15, 2024") == "2024-01-15"
        assert parse_date("playing January 15, 2024") == "2024-01-15"
        assert parse_date("performed January 15, 2024") == "2024-01-15"
        assert parse_date("shows January 15, 2024") == "2024-01-15"
        assert parse_date("concert January 15, 2024") == "2024-01-15"
    
    def test_invalid_dates(self):
        """Test invalid or unparseable dates."""
        assert parse_date("") is None
        assert parse_date("invalid date") is None
        assert parse_date("2024") is None  # Missing month/day
        assert parse_date("January") is None  # Missing year
        assert parse_date("upcoming") is None  # No date
    
    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Very old date
        assert parse_date("January 1, 1900") == "1900-01-01"
        
        # Future date (should still parse, validation happens elsewhere)
        assert parse_date("January 1, 2030") == "2030-01-01"
        
        # Date with extra whitespace
        assert parse_date("  January  15,  2024  ") == "2024-01-15"
        
        # Date with punctuation
        assert parse_date("January 15th, 2024") == "2024-01-15"
        assert parse_date("January 15th 2024") == "2024-01-15"
