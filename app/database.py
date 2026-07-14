"""
Database layer — PostgreSQL (Neon) via psycopg2.
Connection string is read from DATABASE_URL env var (set in .env).
"""

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

@contextmanager
def _conn():
    """Yield a psycopg2 connection, auto-commit, auto-close."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _fetchall(sql: str, params=()) -> list[dict]:
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _fetchone(sql: str, params=()) -> Optional[dict]:
    with _conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def _execute(sql: str, params=()):
    with _conn() as conn:
        conn.cursor().execute(sql, params)


def _execute_returning(sql: str, params=()):
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db():
    """Create all tables if they don't exist."""
    ddl = [
        # Per-turn conversation logs
        """
        CREATE TABLE IF NOT EXISTS call_logs (
            id              SERIAL PRIMARY KEY,
            call_sid        TEXT,
            caller_number   TEXT,
            business_type   TEXT,
            user_said       TEXT,
            ai_replied      TEXT,
            transferred     INTEGER DEFAULT 0,
            timestamp       TEXT
        )
        """,
        # One row per call session
        """
        CREATE TABLE IF NOT EXISTS call_sessions (
            call_sid        TEXT PRIMARY KEY,
            caller_number   TEXT,
            business_type   TEXT,
            status          TEXT,
            started_at      TEXT,
            updated_at      TEXT
        )
        """,
        # Campaign header
        """
        CREATE TABLE IF NOT EXISTS campaigns (
            id          SERIAL PRIMARY KEY,
            name        TEXT,
            created_at  TEXT
        )
        """,
        # Imported contacts per campaign
        """
        CREATE TABLE IF NOT EXISTS campaign_contacts (
            id          SERIAL PRIMARY KEY,
            campaign_id INTEGER,
            name        TEXT,
            phone       TEXT,
            status      TEXT DEFAULT 'pending',
            created_at  TEXT,
            updated_at  TEXT,
            UNIQUE(campaign_id, phone)
        )
        """,
        # Link Twilio CallSid -> campaign contact
        """
        CREATE TABLE IF NOT EXISTS call_contact_map (
            call_sid            TEXT PRIMARY KEY,
            campaign_contact_id INTEGER,
            campaign_id         INTEGER,
            contact_name        TEXT,
            contact_phone       TEXT,
            created_at          TEXT
        )
        """,
    ]
    with _conn() as conn:
        cur = conn.cursor()
        for stmt in ddl:
            cur.execute(stmt)


# ---------------------------------------------------------------------------
# Call session helpers
# ---------------------------------------------------------------------------

def update_call_status(call_sid, caller_number, business_type, status):
    row = _fetchone(
        "SELECT started_at FROM call_sessions WHERE call_sid = %s", (call_sid,)
    )
    started_at = row["started_at"] if row else datetime.utcnow().isoformat()
    updated_at = datetime.utcnow().isoformat()
    _execute(
        """
        INSERT INTO call_sessions (call_sid, caller_number, business_type, status, started_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (call_sid) DO UPDATE
          SET caller_number = EXCLUDED.caller_number,
              business_type = EXCLUDED.business_type,
              status        = EXCLUDED.status,
              updated_at    = EXCLUDED.updated_at
        """,
        (call_sid, caller_number, business_type, status, started_at, updated_at),
    )


def log_turn(call_sid, caller_number, business_type, user_said, ai_replied, transferred=False):
    _execute(
        """
        INSERT INTO call_logs
          (call_sid, caller_number, business_type, user_said, ai_replied, transferred, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (call_sid, caller_number, business_type, user_said, ai_replied,
         int(transferred), datetime.utcnow().isoformat()),
    )


# ---------------------------------------------------------------------------
# Campaign helpers
# ---------------------------------------------------------------------------

def create_campaign(name: str) -> int:
    return int(_execute_returning(
        "INSERT INTO campaigns (name, created_at) VALUES (%s, %s) RETURNING id",
        (name, datetime.utcnow().isoformat()),
    ))


def add_campaign_contacts(campaign_id: int, contacts: list[tuple[str, str]]):
    now = datetime.utcnow().isoformat()
    with _conn() as conn:
        cur = conn.cursor()
        for name, phone in contacts:
            cur.execute(
                """
                INSERT INTO campaign_contacts
                  (campaign_id, name, phone, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'pending', %s, %s)
                ON CONFLICT (campaign_id, phone) DO NOTHING
                """,
                (campaign_id, name, phone, now, now),
            )


def get_next_pending_contact(campaign_id: int) -> Optional[tuple[int, str, str]]:
    row = _fetchone(
        """
        SELECT id, name, phone FROM campaign_contacts
        WHERE campaign_id = %s AND status = 'pending'
        ORDER BY id ASC LIMIT 1
        """,
        (campaign_id,),
    )
    if not row:
        return None
    return (int(row["id"]), row["name"] or "", row["phone"] or "")


def mark_contact_status(campaign_id: int, campaign_contact_id: int, status: str):
    _execute(
        """
        UPDATE campaign_contacts
        SET status = %s, updated_at = %s
        WHERE campaign_id = %s AND id = %s
        """,
        (status, datetime.utcnow().isoformat(), campaign_id, campaign_contact_id),
    )


def get_campaign_contact_by_id(campaign_id: int, campaign_contact_id: int) -> Optional[tuple[str, str]]:
    row = _fetchone(
        "SELECT name, phone FROM campaign_contacts WHERE campaign_id = %s AND id = %s",
        (campaign_id, campaign_contact_id),
    )
    if not row:
        return None
    return (row["name"] or "", row["phone"] or "")


def get_contact_by_id_only(contact_id: int) -> Optional[dict]:
    return _fetchone(
        "SELECT name, phone, campaign_id FROM campaign_contacts WHERE id = %s",
        (contact_id,),
    )


def create_call_session_for_contact(
    *,
    campaign_id: int,
    campaign_contact_id: int,
    contact_name: str,
    contact_phone: str,
    business_type: str,
    status: str,
) -> str:
    now = datetime.utcnow().isoformat()
    call_sid = f"SIM{int(datetime.utcnow().timestamp())}{campaign_contact_id}"
    _execute(
        """
        INSERT INTO call_sessions
          (call_sid, caller_number, business_type, status, started_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (call_sid) DO UPDATE
          SET status = EXCLUDED.status, updated_at = EXCLUDED.updated_at
        """,
        (call_sid, contact_phone, business_type, status, now, now),
    )
    return call_sid


def set_call_contact_map(
    *,
    call_sid: str,
    campaign_id: int,
    campaign_contact_id: int,
    contact_name: str,
    contact_phone: str,
):
    now = datetime.utcnow().isoformat()
    _execute(
        """
        INSERT INTO call_contact_map
          (call_sid, campaign_contact_id, campaign_id, contact_name, contact_phone, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (call_sid) DO UPDATE
          SET contact_name  = EXCLUDED.contact_name,
              contact_phone = EXCLUDED.contact_phone
        """,
        (call_sid, campaign_contact_id, campaign_id, contact_name, contact_phone, now),
    )


def get_call_contact_map(call_sid: str) -> Optional[dict]:
    return _fetchone(
        """
        SELECT contact_name, contact_phone, campaign_id, campaign_contact_id
        FROM call_contact_map WHERE call_sid = %s
        """,
        (call_sid,),
    )


# ---------------------------------------------------------------------------
# Log readers
# ---------------------------------------------------------------------------

def get_all_logs():
    return _fetchall("SELECT * FROM call_logs ORDER BY id DESC")


def get_all_call_sids():
    return _fetchall(
        """
        SELECT
          s.call_sid,
          s.caller_number,
          s.business_type,
          s.status,
          s.started_at,
          s.updated_at,
          COUNT(l.id)        AS turns,
          MAX(l.transferred) AS was_transferred,
          m.contact_name,
          m.contact_phone
        FROM call_sessions s
        LEFT JOIN call_logs l         ON s.call_sid = l.call_sid
        LEFT JOIN call_contact_map m  ON s.call_sid = m.call_sid
        GROUP BY s.call_sid, s.caller_number, s.business_type, s.status,
                 s.started_at, s.updated_at, m.contact_name, m.contact_phone
        ORDER BY s.started_at DESC
        """
    )


def get_transcript(call_sid: str):
    rows = _fetchall(
        "SELECT * FROM call_logs WHERE call_sid = %s ORDER BY id ASC", (call_sid,)
    )
    return [
        {
            "question": r["user_said"],
            "answer": r["ai_replied"],
            "transferred_to_human": bool(r["transferred"]),
            "timestamp": r["timestamp"],
        }
        for r in rows
    ]


def get_transcript_as_text(call_sid: str) -> str:
    turns = get_transcript(call_sid)
    if not turns:
        return f"No transcript found for call {call_sid}"
    lines = [f"Call Transcript --- {call_sid}", "=" * 40]
    for i, t in enumerate(turns, start=1):
        lines.append(f"\nTurn {i} ({t['timestamp']})")
        lines.append(f"Q (Caller): {t['question']}")
        if t["transferred_to_human"]:
            lines.append("A (AI): [Call transferred to human agent]")
        else:
            lines.append(f"A (AI): {t['answer']}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Campaign report queries
# ---------------------------------------------------------------------------

def get_all_campaigns():
    return _fetchall(
        """
        SELECT
          c.id,
          c.name,
          c.created_at,
          COUNT(cc.id)                                                    AS total_contacts,
          SUM(CASE WHEN cc.status = 'pending'  THEN 1 ELSE 0 END)        AS pending,
          SUM(CASE WHEN cc.status = 'calling'  THEN 1 ELSE 0 END)        AS calling,
          SUM(CASE WHEN cc.status = 'called'   THEN 1 ELSE 0 END)        AS called,
          SUM(CASE WHEN cc.status = 'failed'   THEN 1 ELSE 0 END)        AS failed
        FROM campaigns c
        LEFT JOIN campaign_contacts cc ON c.id = cc.campaign_id
        GROUP BY c.id
        ORDER BY c.created_at DESC
        """
    )


def get_campaign_contacts_with_calls(campaign_id: int):
    return _fetchall(
        """
        SELECT
          cc.id            AS contact_id,
          cc.name          AS contact_name,
          cc.phone         AS contact_phone,
          cc.status        AS contact_status,
          cc.updated_at,
          m.call_sid,
          s.status         AS call_status,
          s.started_at,
          COUNT(l.id)      AS turns
        FROM campaign_contacts cc
        LEFT JOIN call_contact_map m
               ON m.campaign_id = cc.campaign_id
              AND m.campaign_contact_id = cc.id
        LEFT JOIN call_sessions s ON s.call_sid = m.call_sid
        LEFT JOIN call_logs l     ON l.call_sid = m.call_sid
        WHERE cc.campaign_id = %s
        GROUP BY cc.id, cc.name, cc.phone, cc.status, cc.updated_at,
                 m.call_sid, s.status, s.started_at
        ORDER BY cc.id ASC
        """,
        (campaign_id,),
    )


def get_campaign_report(campaign_id: int):
    contacts = get_campaign_contacts_with_calls(campaign_id)
    report = []
    for c in contacts:
        conversation = []
        if c.get("call_sid"):
            conversation = get_transcript(c["call_sid"])
        report.append({
            "contact_id": c["contact_id"],
            "name": c["contact_name"] or "Unknown",
            "phone": c["contact_phone"],
            "contact_status": c["contact_status"],
            "call_status": c["call_status"],
            "call_sid": c["call_sid"],
            "started_at": c["started_at"],
            "turns": c["turns"] or 0,
            "conversation": conversation,
        })
    return report
