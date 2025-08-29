 # LastShowFinder (SF/NYC)

Find the most recent **already-played** show for an artist in SF or NYC with URL+snippet evidence.

## Quickstart
```bash
# Code track
uvicorn worker:app --reload
# Make track
Import the blueprint JSON in /make/blueprints and set PPLX_API_KEY
