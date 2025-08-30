#!/usr/bin/env python3
"""
Local smoke test for Last-Show Oracle hardening features.
This script tests the same 8 artists as the previous smoke test.
"""

import asyncio
import json
import httpx
from datetime import datetime
from typing import List, Dict, Any

# Test configuration
BASE_URL = "http://localhost:8000"
ARTISTS = [
    "5658139-crooked-colours",      # Crooked Colours
    "7958783-larry-june",           # Larry June
    "2946631-jesse-daniel",         # Jesse Daniel
    "9152349-sinego",               # Sinego
    "9224649-slenderbodies",        # Slenderbodies
    "5557998-proxima-parada",       # Proxima Parada
    "5157743-mo-lowda-and-the-humble", # Mo Lowda & the Humble
    "10158640-saint-luna"           # Saint Luna
]

async def test_health_endpoints():
    """Test health and ready endpoints."""
    async with httpx.AsyncClient() as client:
        # Test health endpoint
        response = await client.get(f"{BASE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✓ Health endpoint working")
        
        # Test ready endpoint
        response = await client.get(f"{BASE_URL}/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        print("✓ Ready endpoint working")

async def test_songkick_scraping(artist: str) -> List[Dict[str, Any]]:
    """Test Songkick scraping for an artist."""
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/scrape-songkick", json={
            "slug": artist,
            "max_pages": 3
        })
        
        if response.status_code != 200:
            print(f"✗ Failed to scrape {artist}: {response.status_code}")
            return []
        
        candidates = response.json()
        print(f"✓ {artist}: {len(candidates)} candidates")
        
        # Validate candidates have required fields
        for candidate in candidates:
            assert "date_iso" in candidate
            assert "city" in candidate
            assert "venue" in candidate
            assert "url" in candidate
            assert "source_type" in candidate
            assert "snippet" in candidate
            
            # Check date sanity
            date_iso = candidate["date_iso"]
            year = int(date_iso[:4])
            assert 1900 <= year <= datetime.now().year + 1, f"Insane year: {year}"
            
            # Check venue/city presence
            assert candidate["city"] or candidate["venue"], "No venue or city"
        
        return candidates

async def test_selection(candidates: List[Dict[str, Any]], metro: str) -> Dict[str, Any]:
    """Test selection logic for a metro area."""
    if not candidates:
        return {}
    
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/select-latest", json={
            "metro": metro,
            "candidates": candidates
        })
        
        if response.status_code != 200:
            print(f"✗ Failed to select for {metro}: {response.status_code}")
            return {}
        
        result = response.json()
        print(f"✓ {metro} selection: {result.get('date_iso', 'unknown')} at {result.get('venue', 'unknown')}")
        return result

async def main():
    """Run the complete smoke test."""
    print("🚀 Starting Last-Show Oracle Local Smoke Test")
    print("=" * 50)
    
    # Test health endpoints
    await test_health_endpoints()
    print()
    
    # Test each artist
    all_results = {}
    for artist in ARTISTS:
        print(f"Testing artist: {artist}")
        candidates = await test_songkick_scraping(artist)
        
        if candidates:
            # Test SF selection
            sf_result = await test_selection(candidates, "SF")
            if sf_result:
                all_results[f"{artist}_sf"] = sf_result
            
            # Test NYC selection
            nyc_result = await test_selection(candidates, "NYC")
            if nyc_result:
                all_results[f"{artist}_nyc"] = nyc_result
        
        print()
    
    # Save results
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"local_smoke_test_{timestamp}.json"
    
    with open(filename, "w") as f:
        json.dump(all_results, f, indent=2)
    
    print(f"📊 Results saved to {filename}")
    print("🎉 Local smoke test completed!")

if __name__ == "__main__":
    asyncio.run(main())
