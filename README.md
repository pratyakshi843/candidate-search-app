# Candidate Search

Type a hiring requirement in plain English ("Senior backend developers with 5+ years in India") and get a ranked, paginated list of matching candidate profiles.

- **backend/**: FastAPI + DuckDB. A rule-based parser (`app/parser.py`) turns the query into structured filters (candidate name, role, seniority, skills/stack, experience, country/city, company with current/former status, domain, keywords). `app/search.py` turns those filters into SQL with relevance scoring.
  - Experience: "5 years" means exactly 5 (+/-0.1), "5+"/"at least 5" means >= 5, "more than 5" means > 5, "less than 5" means < 5, "between 3 and 5" means 3 to 5.
  - Years of experience are recalculated from employment dates (`app/experience.py`) each time the database is opened. Overlaps are merged and missing or invalid dates are skipped. Totals above 50 years count as unreliable and show as "Experience not available".
- **frontend/**: React 19 + Vite + Tailwind. Has a search box, the parsed filters shown as chips, sorting, pagination, and a profile side panel.

## Data modes

| `DATA_MODE` | Source | DB file |
|---|---|---|
| `real` | CoreSignal JSONL blob streamed from Azure Blob Storage (read-only) | `backend/data/real.duckdb` |
| `demo` | 1,500 generated fictional profiles, no names | `backend/data/demo.duckdb` |

On startup the backend builds the local DuckDB file in a background thread, or reuses it if the blob's ETag hasn't changed. If Azure can't be reached, it keeps serving the last local copy and `/api/health` reports a warning.

## Run

```bash
# backend
python -m venv .venv
.venv/Scripts/activate            # Windows (source .venv/bin/activate on macOS/Linux)
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env   # then fill in Azure settings, or keep DATA_MODE=demo
cd backend && uvicorn app.main:app --reload --port 8000

# frontend (second terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api to :8000)
```

To prebuild or rebuild the database without starting the server: `cd backend && python -m app.loader [--refresh]`.

## Search bar and filters

The typed query and the Filters panel use the same filter model (`backend/app/filters.py`): role, skills (match any/all), experience (exact ±0.1, at least, more than, at most, less than, between), country, city, company (current/former/either) and industry.
- The query is parsed into filters and shown as chips while you type.
- A panel value replaces the query's value for that category.
- Skills from both are combined without duplicates.
- A chip you remove stays removed (sent as `dismissed`) until you clear the query.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `status` (`starting` / `loading` / `ready` / `refreshing` / `error`), mode, record count, warning |
| POST | `/api/search` | `{query, filters, dismissed, page=1, page_size=12 (max 50), sort}`. `sort` is one of `relevance`, `experience_desc`, `experience_asc`, `recent`. Needs a query or at least one filter |
| POST | `/api/resolve` | Same `{query, filters, dismissed}` without searching. Returns the merged filters and the chips the search bar shows |
| GET | `/api/suggest?field=role\|skill\|country\|city\|company\|industry&q=` | Filters-panel dropdown values from the loaded data |
| GET | `/api/candidate/{id}` | Full profile (experience, education, skills) |
| POST | `/api/refresh` | Re-download and rebuild. Needs header `X-Refresh-Token: $REFRESH_TOKEN` |
