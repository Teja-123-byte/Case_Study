import csv
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, model_validator
from research_engine import discover_public_page


ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "research.db"
DATA_PATH = ROOT / "applications.json"


SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL,
    category TEXT NOT NULL,
    official_website TEXT,
    login_url TEXT,
    signup_url TEXT,
    email_password INTEGER,
    google_oauth INTEGER,
    microsoft_oauth INTEGER,
    github_oauth INTEGER,
    apple_oauth INTEGER,
    magic_link INTEGER,
    passwordless INTEGER,
    sso_saml INTEGER,
    mfa_available INTEGER,
    mfa_required INTEGER,
    email_verification INTEGER,
    free_signup INTEGER,
    credit_card_required INTEGER,
    trial_available INTEGER,
    business_verification INTEGER,
    api_available INTEGER,
    api_authentication TEXT,
    developer_approval INTEGER,
    payment_requirement TEXT,
    access_status TEXT DEFAULT 'Not tested',
    research_status TEXT DEFAULT 'pending',
    blockers TEXT,
    findings TEXT,
    evidence_urls TEXT DEFAULT '[]',
    screenshot_paths TEXT DEFAULT '[]',
    confidence_score INTEGER,
    last_researched TEXT
);
CREATE TABLE IF NOT EXISTS research_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    scope_name TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    started_at TEXT,
    updated_at TEXT,
    completed INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0,
    current_app TEXT,
    log TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL,
    claim TEXT,
    source_url TEXT,
    retrieval_date TEXT,
    verification_status TEXT,
    FOREIGN KEY(application_id) REFERENCES applications(id)
);
"""


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    with connect() as db:
        db.executescript(SCHEMA)
        count = db.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
        if count == 0 and DATA_PATH.exists():
            data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
            fields = [
                "app_name", "category", "official_website", "login_url", "signup_url",
                "email_password", "google_oauth", "microsoft_oauth", "github_oauth",
                "apple_oauth", "magic_link", "passwordless", "sso_saml",
                "mfa_available", "mfa_required", "email_verification", "free_signup",
                "credit_card_required", "trial_available", "business_verification",
                "api_available", "api_authentication", "developer_approval",
                "payment_requirement", "access_status", "research_status", "blockers",
                "findings", "evidence_urls", "screenshot_paths", "confidence_score",
                "last_researched",
            ]
            placeholders = ",".join("?" for _ in fields)
            for item in data:
                values = [
                    json.dumps(item[field]) if field in ("evidence_urls", "screenshot_paths") else item.get(field)
                    for field in fields
                ]
                db.execute(
                    f"INSERT INTO applications ({','.join(fields)}) VALUES ({placeholders})",
                    values,
                )


initialize_database()
app = FastAPI(title="100-App Authentication Research Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SCREENSHOT_DIR = ROOT / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/screenshots", StaticFiles(directory=SCREENSHOT_DIR), name="screenshots")

research_pause = threading.Event()
active_jobs = set()


def row_dict(row):
    item = dict(row)
    for field in ("evidence_urls", "screenshot_paths"):
        try:
            item[field] = json.loads(item[field] or "[]")
        except json.JSONDecodeError:
            item[field] = []
    return item


class ResearchRequest(BaseModel):
    scope: str = "all"
    scope_name: Optional[str] = None

    @model_validator(mode="after")
    def validate_scope(self):
        # Keep scope validation explicit so typos can never turn into an all-app run.
        if self.scope not in {"all", "category", "application"}:
            raise ValueError("scope must be all, category, or application")
        if self.scope != "all" and not (self.scope_name and self.scope_name.strip()):
            raise ValueError("scope_name is required for category and application scopes")
        return self


def append_log(job_id, message):
    with connect() as db:
        row = db.execute("SELECT log FROM research_jobs WHERE id = ?", (job_id,)).fetchone()
        log = (row["log"] if row and row["log"] else "")
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.execute(
            "UPDATE research_jobs SET log = ?, updated_at = ? WHERE id = ?",
            (f"[{stamp}] {message}\n" + log, stamp, job_id),
        )


def run_research(job_id, scope, scope_name):
    active_jobs.add(job_id)
    with connect() as db:
        if scope == "category":
            rows = db.execute(
                "SELECT id, app_name FROM applications WHERE category = ?",
                (scope_name,),
            ).fetchall()
        elif scope == "application":
            rows = db.execute(
                "SELECT id, app_name FROM applications WHERE app_name = ?",
                (scope_name,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT id, app_name FROM applications WHERE research_status != 'completed'"
            ).fetchall()
        if scope in {"category", "application"} and not rows:
            with connect() as db:
                db.execute(
                    "UPDATE research_jobs SET status='failed', total=0, updated_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(timespec="seconds"), job_id),
                )
            append_log(job_id, f"No application matched {scope}: {scope_name}")
            active_jobs.discard(job_id)
            return
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.execute(
            "UPDATE research_jobs SET status='running', started_at=?, updated_at=?, total=? WHERE id=?",
            (now, now, len(rows), job_id),
        )

    try:
        for index, row in enumerate(rows, start=1):
            while research_pause.is_set():
                time.sleep(0.25)
                append_log(job_id, "Research paused") if index == 1 else None
            with connect() as db:
                db.execute(
                    "UPDATE research_jobs SET current_app=?, completed=?, updated_at=? WHERE id=?",
                    (
                        row["app_name"],
                        index - 1,
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        job_id,
                    ),
                )
            # Public-page probing is deliberately explicit and never creates accounts.
            official = db_execute(
                "SELECT official_website FROM applications WHERE id=?", (row["id"],)
            )[0]["official_website"]
            status = "public documentation only"
            findings = "Official public URL identified. Automated evidence collection pending or requires account verification."
            verification_status = "Public documentation only"
            http_status = None
            last_error = None
            extracted = None
            for attempt in range(3):
                try:
                    extracted = discover_public_page(row["app_name"], official)
                    http_status = extracted["http_status"]
                    status = "public documentation only"
                    findings = extracted["findings"]
                    verification_status = extracted["verification_status"]
                    screenshot_path = None
                    try:
                        from research_engine import capture_public_screenshot
                        screenshot_path = capture_public_screenshot(
                            row["app_name"],
                            extracted["official_url"],
                        )
                    except Exception:
                        screenshot_path = None
                    break
                except httpx.HTTPError as exc:
                    last_error = exc
                    if attempt < 2:
                        time.sleep(1.5 * (attempt + 1))
            if last_error is not None and http_status is None:
                status = "blocked"
                findings = (
                    f"Public site probe failed after retries: {type(last_error).__name__}; "
                    "no account action was performed."
                )
                verification_status = "Blocked"

            with connect() as db:
                db.execute(
                    """
                    UPDATE applications
                    SET research_status='completed', access_status=?, findings=?,
                        blockers=?, login_url=?, signup_url=?, official_website=?,
                        google_oauth=?, microsoft_oauth=?, github_oauth=?,
                        apple_oauth=?, magic_link=?, passwordless=?, sso_saml=?,
                        mfa_available=?, api_available=?, evidence_urls=?, last_researched=?
                        , screenshot_paths=?
                    WHERE id=?
                    """,
                    (
                        status,
                        findings,
                        findings if status == "blocked" else None,
                        locals().get("extracted", {}).get("login_url"),
                        locals().get("extracted", {}).get("signup_url"),
                        locals().get("extracted", {}).get("official_url", official),
                        locals().get("extracted", {}).get("google_oauth"),
                        locals().get("extracted", {}).get("microsoft_oauth"),
                        locals().get("extracted", {}).get("github_oauth"),
                        locals().get("extracted", {}).get("apple_oauth"),
                        locals().get("extracted", {}).get("magic_link"),
                        locals().get("extracted", {}).get("passwordless"),
                        locals().get("extracted", {}).get("sso_saml"),
                        locals().get("extracted", {}).get("mfa_available"),
                        locals().get("extracted", {}).get("api_available"),
                        json.dumps([locals().get("extracted", {}).get("evidence_url")] if locals().get("extracted", {}).get("evidence_url") else []),
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        json.dumps([screenshot_path] if locals().get("screenshot_path") else []),
                        row["id"],
                    ),
                )
                db.execute(
                    """
                    INSERT INTO evidence
                    (application_id, claim, source_url, retrieval_date, verification_status)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        row["id"],
                        findings,
                        official,
                        datetime.now(timezone.utc).isoformat(timespec="seconds"),
                        verification_status,
                    ),
                )
            append_log(job_id, f"{row['app_name']}: public probe completed ({status})")
    except Exception as exc:
        append_log(job_id, f"Job stopped: {type(exc).__name__}: {exc}")
        with connect() as db:
            db.execute(
                "UPDATE research_jobs SET status='failed', updated_at=? WHERE id=?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), job_id),
            )
        active_jobs.discard(job_id)
        return

    with connect() as db:
        db.execute(
            "UPDATE research_jobs SET status='completed', completed=?, current_app=NULL, updated_at=? WHERE id=?",
            (len(rows), datetime.now(timezone.utc).isoformat(timespec="seconds"), job_id),
        )
    append_log(job_id, "Research job completed")
    active_jobs.discard(job_id)


def db_execute(query, params=()):
    with connect() as db:
        return [dict(row) for row in db.execute(query, params).fetchall()]


@app.get("/api/overview")
def overview():
    rows = db_execute(
        "SELECT category, COUNT(*) total, "
        "SUM(CASE WHEN research_status='completed' THEN 1 ELSE 0 END) researched "
        "FROM applications GROUP BY category ORDER BY category"
    )
    totals = db_execute(
        "SELECT COUNT(*) total, "
        "SUM(CASE WHEN research_status='completed' THEN 1 ELSE 0 END) researched, "
        "SUM(CASE WHEN access_status='blocked' THEN 1 ELSE 0 END) blocked, "
        "SUM(CASE WHEN research_status='pending' THEN 1 ELSE 0 END) pending "
        "FROM applications"
    )[0]
    total = totals["total"] or 0
    researched = totals["researched"] or 0
    totals["completion"] = round(researched * 100 / total, 1) if total else 0
    totals["verified"] = db_execute(
        "SELECT COUNT(*) count FROM applications WHERE confidence_score >= 80"
    )[0]["count"]
    return {"totals": totals, "categories": rows}


@app.get("/api/applications")
def applications(
    search: str = "",
    category: str = "",
    status: str = "",
    limit: int = Query(default=500, ge=1, le=1000),
):
    clauses = []
    params = []
    if search:
        clauses.append("app_name LIKE ?")
        params.append(f"%{search}%")
    if category:
        clauses.append("category = ?")
        params.append(category)
    if status:
        clauses.append("research_status = ?")
        params.append(status)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    with connect() as db:
        rows = db.execute(
            f"SELECT * FROM applications{where} ORDER BY category, app_name LIMIT ?",
            (*params, limit),
        ).fetchall()
    return [row_dict(row) for row in rows]


@app.get("/api/applications/{app_id}")
def application_detail(app_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM applications WHERE id=?", (app_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Application not found")
    evidence = db_execute(
        "SELECT * FROM evidence WHERE application_id=? ORDER BY id DESC",
        (app_id,),
    )
    item = row_dict(row)
    item["evidence"] = evidence
    return item


@app.post("/api/research")
def start_research(request: ResearchRequest):
    if request.scope not in {"all", "category", "application"}:
        raise HTTPException(status_code=422, detail="scope must be all, category, or application")
    if request.scope != "all" and not (request.scope_name and request.scope_name.strip()):
        raise HTTPException(status_code=422, detail="scope_name is required for category and application scopes")
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO research_jobs(scope, scope_name, status, updated_at) VALUES (?, ?, 'queued', ?)",
            (request.scope, request.scope_name, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        job_id = cursor.lastrowid
    threading.Thread(target=run_research, args=(job_id, request.scope, request.scope_name), daemon=True).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs")
def jobs():
    return db_execute("SELECT * FROM research_jobs ORDER BY id DESC LIMIT 20")


@app.post("/api/research/pause")
def pause_research():
    research_pause.set()
    return {"status": "paused"}


@app.post("/api/research/resume")
def resume_research():
    research_pause.clear()
    return {"status": "resumed"}


@app.post("/api/research/retry")
def retry_failed():
    with connect() as db:
        db.execute(
            """
            UPDATE applications
            SET research_status='pending', access_status='Not tested',
                findings=NULL, blockers=NULL
            WHERE access_status='blocked' OR research_status='failed'
            """
        )
        cursor = db.execute(
            "INSERT INTO research_jobs(scope, scope_name, status, updated_at) "
            "VALUES ('all', 'retry failed applications', 'queued', ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
        )
        job_id = cursor.lastrowid
    threading.Thread(
        target=run_research,
        args=(job_id, "all", "retry failed applications"),
        daemon=True,
    ).start()
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/export")
def export_csv():
    with connect() as db:
        rows = db.execute("SELECT * FROM applications ORDER BY category, app_name").fetchall()
    path = ROOT / "research-export.csv"
    with path.open("w", newline="", encoding="utf-8") as file:
        if rows:
            writer = csv.DictWriter(file, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows([dict(row) for row in rows])
    return FileResponse(path, filename="100-app-authentication-research.csv")


@app.get("/api/export.json")
def export_json():
    with connect() as db:
        rows = db.execute("SELECT * FROM applications ORDER BY category, app_name").fetchall()
    items = [row_dict(row) for row in rows]
    path = ROOT / "research-export.json"
    path.write_text(json.dumps(items, indent=2), encoding="utf-8")
    return FileResponse(path, filename="100-app-authentication-research.json")


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")
