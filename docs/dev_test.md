You are my local dev assistant. Help me run and test the Last-Show Oracle (LSO) on my laptop using real URLs I provide, then verify results. Assume the repo contains `worker.py`, `requirements.txt`, `settings.py`, and the config files.

## Goals
1) Start the FastAPI service locally (venv first; Docker optional).
2) Exercise each endpoint with **real URLs I paste** and/or Songkick.
3) Combine candidates and select the most recent show for **SF** and **NYC**.
4) Validate outputs (evidence-or-bust, correct metro, latest date).
5) Produce a clear pass/fail report and capture sample JSON for use in Make.

## Constraints
- Run on localhost, but the service must fetch the public web.
- Return **explainable** JSON with URL + snippet containing a **past date** and either **city token** or **venue**.
- Selector must be deterministic (latest date + precedence; tie-break on venue-in-snippet).
- If nothing passes, return `{"status":"unknown"}` with alternates (don’t crash).

## Tasks (check off as you complete)
- [ ] Create & activate a Python virtual environment
- [ ] Install requirements
- [ ] Start the app with uvicorn on port 8000
- [ ] Health check
- [ ] Parse at least 1 real URL I provide with `/parse-generic`
- [ ] Try Wayback fallback for that URL with `/wayback-parse`
- [ ] Scrape Songkick for the same artist with `/scrape-songkick`
- [ ] Merge candidates and select SF
- [ ] Merge candidates and select NYC
- [ ] Save sample responses into `samples/` for both metros
- [ ] Produce a summary report (precision checks + notes)
- [ ] Write a short HOWTO snippet I can paste into the Make scenario notes

## Commands (Mac/Linux default; offer Windows cmd/PowerShell when needed)

### 0) Virtual environment & run server
```bash
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn worker:app --host 0.0.0.0 --port 8000 --reload
