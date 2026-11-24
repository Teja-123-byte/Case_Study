# AuthAtlas: Authentication Research Dashboard

AuthAtlas is a research dashboard for comparing authentication and developer access across 100 applications in 10 categories. It combines a searchable application catalog, public-page research jobs, evidence records, and downloadable exports.

**Live demo:** [case-study-nryh.onrender.com](https://case-study-nryh.onrender.com)

## What it does

- Browse, search, and filter the 100-application catalog.
- Review authentication fields, findings, limitations, and source links for an application.
- Run public-page research for all pending applications, a category, or one application.
- Pause, resume, and retry research jobs.
- View research progress and export the catalog as CSV or JSON.
- Track public-page screenshots when browser capture is available.

## Research scope and limitations

Research jobs make read-only requests to public application pages. They can collect public-page text, discover same-site login and signup links, and identify authentication indicators for later review. These indicators are not proof of the application's complete sign-in behavior. Public probes do not create accounts, submit personal information, bypass CAPTCHA or MFA, or access paid resources. Unknown values remain unknown unless supported by reviewed evidence.

The app uses SQLite and in-process background threads. It is intended for a single-instance demo or research project; queued work may not survive a service restart, and SQLite is not configured for multi-instance deployment. On Render, the default filesystem is ephemeral, so locally stored database and screenshot changes may be lost on deploy or restart. Use persistent storage or a managed database before relying on long-term hosted records.

## Tech stack

- **Backend:** Python, FastAPI, SQLite
- **Research:** HTTPX, Beautiful Soup, optional Playwright browser screenshots
- **Frontend:** standalone HTML, CSS, and JavaScript
- **Deployment:** Render configuration in `render.yaml`

## Run locally

Requires Python 3.11.9 (see `.python-version`). From the repository root:

```bash
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Then install dependencies and start the server:

```bash
python -m pip install -r requirements.txt
python seed_data.py
python -m uvicorn backend:app --reload --host 127.0.0.1 --port 8080
```

Open [http://127.0.0.1:8080](http://127.0.0.1:8080). The database is created as `research.db` in the project directory. The seed script recreates `applications.json`; the backend loads that dataset into an empty database on startup.

To run the test suite:

```bash
python -m unittest
```

Playwright screenshots require a compatible browser installation. Install Chromium with `python -m playwright install chromium`. If Chromium is unavailable, screenshot capture is skipped while public-page text research can still run.

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/overview` | Totals and category progress |
| `GET` | `/api/applications` | Search and filter applications |
| `GET` | `/api/applications/{id}` | Application details and evidence |
| `POST` | `/api/research` | Start a research job |
| `GET` | `/api/jobs` | List recent research jobs |
| `POST` | `/api/research/pause` | Pause active research |
| `POST` | `/api/research/resume` | Resume paused research |
| `POST` | `/api/research/retry` | Retry blocked or failed applications |
| `GET` | `/api/export` | Download CSV |
| `GET` | `/api/export.json` | Download JSON |

Example: start research for one category.

```bash
curl -X POST http://127.0.0.1:8080/api/research \
  -H "Content-Type: application/json" \
  -d '{"scope":"category","scope_name":"CRM and Sales"}'
```

Valid scopes are `all`, `category`, and `application`. The latter two require a matching `scope_name`.

## Deploy to Render

The repository includes a Render Blueprint in `render.yaml` and pins Python to 3.11.9. The configured commands are:

```text
Build: pip install -r requirements.txt
Start: uvicorn backend:app --host 0.0.0.0 --port $PORT
```

If configuring the service manually, use the Python 3 runtime and set `PYTHON_VERSION` to `3.11.9`. The app currently stores SQLite data in the project directory; configure persistent storage or move to a managed database if hosted data must survive deployments.

## Repository structure

```text
backend.py          FastAPI routes, SQLite persistence, research jobs
research_engine.py  Public-page extraction and optional screenshot capture
index.html          Dashboard interface
applications.json   Seed dataset for 100 applications
seed_data.py        Deterministic dataset generator
test_backend.py     Backend and research utility tests
render.yaml         Render deployment configuration
FINAL_REPORT.md     Research objective, methodology, and limitations
```
