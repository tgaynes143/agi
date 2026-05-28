"""SQLite store for companies, contacts, activities, drafts.

Insurance middle-market focused: companies carry revenue band, industry vertical,
and the lines of coverage they likely buy. Contacts carry buyer-side titles
(Risk Mgr, CFO, GC, Treasurer, etc.) and a confidence score from hunting.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "crm.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    domain TEXT UNIQUE,
    industry TEXT,
    revenue_band TEXT,
    employee_count INTEGER,
    hq_city TEXT,
    hq_state TEXT,
    lines_of_coverage TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    first_name TEXT,
    last_name TEXT,
    title TEXT,
    email TEXT,
    email_confidence REAL DEFAULT 0,
    linkedin_url TEXT,
    phone TEXT,
    source TEXT,
    last_contacted_at TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(email)
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    company_id INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,        -- email_sent, email_received, call, meeting, note, draft_created
    direction TEXT,            -- outbound, inbound, internal
    subject TEXT,
    body TEXT,
    metadata_json TEXT,
    occurred_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id) ON DELETE CASCADE,
    template_name TEXT,
    to_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, exported, sent, failed
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_activities_contact ON activities(contact_id);
CREATE INDEX IF NOT EXISTS idx_activities_company ON activities(company_id);
CREATE INDEX IF NOT EXISTS idx_activities_occurred ON activities(occurred_at DESC);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Company:
    name: str
    domain: str | None = None
    industry: str | None = None
    revenue_band: str | None = None
    employee_count: int | None = None
    hq_city: str | None = None
    hq_state: str | None = None
    lines_of_coverage: str | None = None
    notes: str | None = None
    id: int | None = None


@dataclass
class Contact:
    first_name: str | None = None
    last_name: str | None = None
    title: str | None = None
    email: str | None = None
    email_confidence: float = 0.0
    linkedin_url: str | None = None
    phone: str | None = None
    source: str | None = None
    company_id: int | None = None
    notes: str | None = None
    id: int | None = None


@dataclass
class Activity:
    kind: str
    occurred_at: str
    contact_id: int | None = None
    company_id: int | None = None
    direction: str | None = None
    subject: str | None = None
    body: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: int | None = None


class DB:
    def __init__(self, path: Path | str = DEFAULT_DB_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ---------- companies ----------

    def upsert_company(self, company: Company) -> int:
        now = _now()
        with self._conn() as c:
            if company.domain:
                existing = c.execute(
                    "SELECT id FROM companies WHERE domain = ?", (company.domain,)
                ).fetchone()
                if existing:
                    c.execute(
                        """UPDATE companies SET name=?, industry=COALESCE(?, industry),
                           revenue_band=COALESCE(?, revenue_band),
                           employee_count=COALESCE(?, employee_count),
                           hq_city=COALESCE(?, hq_city), hq_state=COALESCE(?, hq_state),
                           lines_of_coverage=COALESCE(?, lines_of_coverage),
                           notes=COALESCE(?, notes), updated_at=?
                           WHERE id=?""",
                        (company.name, company.industry, company.revenue_band,
                         company.employee_count, company.hq_city, company.hq_state,
                         company.lines_of_coverage, company.notes, now, existing["id"]),
                    )
                    return existing["id"]
            cur = c.execute(
                """INSERT INTO companies (name, domain, industry, revenue_band,
                   employee_count, hq_city, hq_state, lines_of_coverage, notes,
                   created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (company.name, company.domain, company.industry, company.revenue_band,
                 company.employee_count, company.hq_city, company.hq_state,
                 company.lines_of_coverage, company.notes, now, now),
            )
            return cur.lastrowid

    def list_companies(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM companies ORDER BY updated_at DESC"
            )]

    def get_company(self, company_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
            return dict(row) if row else None

    # ---------- contacts ----------

    def upsert_contact(self, contact: Contact) -> int:
        now = _now()
        with self._conn() as c:
            if contact.email:
                existing = c.execute(
                    "SELECT id FROM contacts WHERE email = ?", (contact.email,)
                ).fetchone()
                if existing:
                    c.execute(
                        """UPDATE contacts SET first_name=COALESCE(?, first_name),
                           last_name=COALESCE(?, last_name), title=COALESCE(?, title),
                           email_confidence=MAX(email_confidence, ?),
                           linkedin_url=COALESCE(?, linkedin_url),
                           phone=COALESCE(?, phone), source=COALESCE(?, source),
                           company_id=COALESCE(?, company_id),
                           notes=COALESCE(?, notes), updated_at=?
                           WHERE id=?""",
                        (contact.first_name, contact.last_name, contact.title,
                         contact.email_confidence, contact.linkedin_url, contact.phone,
                         contact.source, contact.company_id, contact.notes, now,
                         existing["id"]),
                    )
                    return existing["id"]
            cur = c.execute(
                """INSERT INTO contacts (first_name, last_name, title, email,
                   email_confidence, linkedin_url, phone, source, company_id,
                   notes, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (contact.first_name, contact.last_name, contact.title, contact.email,
                 contact.email_confidence, contact.linkedin_url, contact.phone,
                 contact.source, contact.company_id, contact.notes, now, now),
            )
            return cur.lastrowid

    def list_contacts(self, company_id: int | None = None) -> list[dict]:
        with self._conn() as c:
            if company_id is not None:
                rows = c.execute(
                    """SELECT c.*, co.name AS company_name, co.domain AS company_domain
                       FROM contacts c LEFT JOIN companies co ON c.company_id = co.id
                       WHERE c.company_id = ? ORDER BY c.updated_at DESC""",
                    (company_id,),
                ).fetchall()
            else:
                rows = c.execute(
                    """SELECT c.*, co.name AS company_name, co.domain AS company_domain
                       FROM contacts c LEFT JOIN companies co ON c.company_id = co.id
                       ORDER BY c.updated_at DESC"""
                ).fetchall()
            return [dict(r) for r in rows]

    def get_contact(self, contact_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                """SELECT c.*, co.name AS company_name, co.domain AS company_domain
                   FROM contacts c LEFT JOIN companies co ON c.company_id = co.id
                   WHERE c.id=?""",
                (contact_id,),
            ).fetchone()
            return dict(row) if row else None

    def search_contacts(self, query: str) -> list[dict]:
        like = f"%{query.lower()}%"
        with self._conn() as c:
            rows = c.execute(
                """SELECT c.*, co.name AS company_name FROM contacts c
                   LEFT JOIN companies co ON c.company_id = co.id
                   WHERE LOWER(c.first_name) LIKE ? OR LOWER(c.last_name) LIKE ?
                       OR LOWER(c.email) LIKE ? OR LOWER(c.title) LIKE ?
                       OR LOWER(co.name) LIKE ?""",
                (like, like, like, like, like),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---------- activities ----------

    def log_activity(self, activity: Activity) -> int:
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO activities (contact_id, company_id, kind, direction,
                   subject, body, metadata_json, occurred_at, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (activity.contact_id, activity.company_id, activity.kind,
                 activity.direction, activity.subject, activity.body,
                 json.dumps(activity.metadata) if activity.metadata else None,
                 activity.occurred_at, _now()),
            )
            return cur.lastrowid

    def activities_for_contact(self, contact_id: int, limit: int = 200) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT * FROM activities WHERE contact_id=?
                   ORDER BY occurred_at DESC LIMIT ?""",
                (contact_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def activities_for_company(self, company_id: int, limit: int = 200) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT a.*, c.first_name, c.last_name FROM activities a
                   LEFT JOIN contacts c ON a.contact_id = c.id
                   WHERE a.company_id=? ORDER BY a.occurred_at DESC LIMIT ?""",
                (company_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def all_activities(self, limit: int = 1000) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT a.*, c.first_name, c.last_name, c.email,
                          co.name AS company_name
                   FROM activities a
                   LEFT JOIN contacts c ON a.contact_id = c.id
                   LEFT JOIN companies co ON a.company_id = co.id
                   ORDER BY a.occurred_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # ---------- drafts ----------

    def save_draft(self, contact_id: int, template_name: str | None,
                   to_email: str, subject: str, body: str) -> int:
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO drafts (contact_id, template_name, to_email,
                   subject, body, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (contact_id, template_name, to_email, subject, body, _now()),
            )
            return cur.lastrowid

    def list_drafts(self, status: str | None = None) -> list[dict]:
        with self._conn() as c:
            if status:
                rows = c.execute(
                    """SELECT d.*, c.first_name, c.last_name, co.name AS company_name
                       FROM drafts d
                       LEFT JOIN contacts c ON d.contact_id = c.id
                       LEFT JOIN companies co ON c.company_id = co.id
                       WHERE d.status=? ORDER BY d.created_at DESC""",
                    (status,),
                ).fetchall()
            else:
                rows = c.execute(
                    """SELECT d.*, c.first_name, c.last_name, co.name AS company_name
                       FROM drafts d
                       LEFT JOIN contacts c ON d.contact_id = c.id
                       LEFT JOIN companies co ON c.company_id = co.id
                       ORDER BY d.created_at DESC"""
                ).fetchall()
            return [dict(r) for r in rows]

    def mark_draft_status(self, draft_id: int, status: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE drafts SET status=? WHERE id=?", (status, draft_id))

    # ---------- templates ----------

    def upsert_template(self, name: str, subject: str, body: str,
                        description: str | None = None) -> int:
        now = _now()
        with self._conn() as c:
            existing = c.execute(
                "SELECT id FROM templates WHERE name=?", (name,)
            ).fetchone()
            if existing:
                c.execute(
                    """UPDATE templates SET subject=?, body=?, description=?,
                       updated_at=? WHERE id=?""",
                    (subject, body, description, now, existing["id"]),
                )
                return existing["id"]
            cur = c.execute(
                """INSERT INTO templates (name, subject, body, description,
                   created_at, updated_at) VALUES (?,?,?,?,?,?)""",
                (name, subject, body, description, now, now),
            )
            return cur.lastrowid

    def list_templates(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM templates ORDER BY name"
            )]

    def get_template(self, name: str) -> dict | None:
        with self._conn() as c:
            row = c.execute(
                "SELECT * FROM templates WHERE name=?", (name,)
            ).fetchone()
            return dict(row) if row else None
