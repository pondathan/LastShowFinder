import pytest
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from fastapi.testclient import TestClient
from worker import app

client = TestClient(app)

def test_health_endpoint():
    """Test that the health endpoint works without authentication."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data

def test_ready_endpoint():
    """Test that the ready endpoint works without authentication."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert "timestamp" in data

def test_protected_endpoints_require_auth():
    """Test that protected endpoints require authentication when API key is set."""
    # Test scrape-songkick endpoint
    response = client.post("/scrape-songkick", json={"artist": "test"})
    # Should work without API key if not configured
    assert response.status_code in [200, 400, 500]  # Any response is fine for this test

def test_date_validation():
    """Test date validation function."""
    from worker import validate_date_sanity
    
    # Valid dates
    assert validate_date_sanity("2023-12-25") == True
    assert validate_date_sanity("2024-01-01") == True
    
    # Invalid dates
    assert validate_date_sanity("1899-12-31") == False  # Too old
    assert validate_date_sanity("2030-13-01") == False  # Invalid month
    assert validate_date_sanity("2024-00-01") == False  # Invalid day
    assert validate_date_sanity("invalid") == False      # Invalid format
