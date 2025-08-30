# Tools Directory

This directory contains various tools and utilities for the Last-Show Oracle service.

## Smoke Testing
- `local_smoke_test.py` - Local smoke test script for testing the service
- `local_smoke_test_*.json` - Results from local smoke test runs

## Candidate Data
- `*_candidates.json` - Raw candidate data from Songkick scraping
- `proxima_parada_fixed.json` - Fixed candidate data for Proxima Parada

## Statistics
- `Venue Finder Stats - Artist Smoke Test.csv` - CSV export of smoke test statistics

## Usage
Run smoke tests from the project root:
```bash
python tools/local_smoke_test.py
```

View candidate data:
```bash
cat tools/*_candidates.json
```
