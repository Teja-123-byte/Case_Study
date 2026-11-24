# 100-App Authentication Research Agent

A local-first research dashboard for studying authentication and developer access across 100 applications.

## Important research boundary

The agent only performs read-only public HTTP probes. It does not create accounts, submit personal data, bypass CAPTCHA, defeat MFA, or access paid/paywalled resources. Unknown and untested values remain `null`/unknown; they are never inferred as `false`.

## Run locally

```bash
python -m pip install -r requirements.txt
python seed_data.py
python -m uvicorn backend:app --reload --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080`.

If Windows reports `WinError 10013` with a different port, use port `8080`
or another port such as `8081`. This error means that port is reserved or
blocked by Windows, not that the FastAPI application crashed.

## API

- `GET /api/overview`
- `GET /api/applications`
- `GET /api/applications/{id}`
- `POST /api/research`
- `GET /api/jobs`
- `GET /api/export`

Example research request:

```json
{"scope":"category","scope_name":"CRM and Sales"}
```

## Architecture

- `applications.json`: structured seed of all 100 applications.
- `backend.py`: FastAPI API, SQLite persistence, and resumable public research jobs.
- `index.html`: standalone dashboard and case-study interface.
- `seed_data.py`: deterministic generation of the source dataset.
- `research.db`: local SQLite database created automatically.
- `test_backend.py`: unit and API smoke tests.
- `Procfile`: process command for common Python hosts.
- `render.yaml`: example Render deployment configuration.

## Deployment

Deploy on a Python host such as Render, Railway, or Fly.io. Set environment variables from `.env.example`, start with `uvicorn backend:app --host 0.0.0.0 --port $PORT`, and use persistent storage if SQLite data must survive restarts.
