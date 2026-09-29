"""SQLite persistence for app metadata, workflow records, audit results and the demo-mode memory store."""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from .config import settings

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS engagements (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, engagement_type TEXT, industry TEXT, region TEXT, size TEXT,
  status TEXT NOT NULL DEFAULT 'Active', start_date TEXT, end_date TEXT, partner TEXT,
  client_team TEXT, contract_value TEXT, sensitive_terms TEXT, simulation TEXT,
  bank_id TEXT NOT NULL, source TEXT DEFAULT 'seed', created_at TEXT, closed_at TEXT
);

CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT, engagement_id TEXT NOT NULL, date TEXT, author TEXT, text TEXT NOT NULL,
  retained_backend TEXT, created_at TEXT
);

CREATE TABLE IF NOT EXISTS sim_memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT, bank_id TEXT NOT NULL, content TEXT NOT NULL, context TEXT,
  timestamp TEXT, meta TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_sim_bank ON sim_memories(bank_id);

CREATE TABLE IF NOT EXISTS lessons (
  id TEXT PRIMARY KEY, text TEXT NOT NULL, category TEXT, approach TEXT, outcome TEXT, why TEXT,
  conditions TEXT, scale TEXT, status TEXT NOT NULL, evidence_count INTEGER DEFAULT 1,
  contributions TEXT, history TEXT, created_at TEXT, updated_at TEXT, backend TEXT, conflict_id TEXT
);

CREATE TABLE IF NOT EXISTS workflows (
  id TEXT PRIMARY KEY, engagement_id TEXT NOT NULL, status TEXT, decision TEXT, stages TEXT, candidate TEXT,
  verification TEXT, recall TEXT, lesson_id TEXT, mode TEXT, started_at TEXT, finished_at TEXT, error TEXT
);

CREATE TABLE IF NOT EXISTS conflicts (
  id TEXT PRIMARY KEY, category TEXT, approach TEXT, lesson_ids TEXT, status TEXT, synthesis_lesson_id TEXT,
  synthesis_text TEXT, engine TEXT, created_at TEXT, resolved_at TEXT
);

CREATE TABLE IF NOT EXISTS attack_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, test_id TEXT, category TEXT, prompt TEXT, mode TEXT,
  response TEXT, passed INTEGER, explanation TEXT, leaked TEXT, engine TEXT, naive INTEGER DEFAULT 0, created_at TEXT
);

CREATE TABLE IF NOT EXISTS activity (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, message TEXT, meta TEXT
);

CREATE TABLE IF NOT EXISTS access_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, scope TEXT, bank_id TEXT, operation TEXT, caller TEXT,
  allowed INTEGER, backend TEXT
);

CREATE TABLE IF NOT EXISTS playbook_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, lesson_count INTEGER, evidence_total INTEGER, event TEXT
);

CREATE TABLE IF NOT EXISTS chat_messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT, role TEXT, content TEXT, mode TEXT,
  client_id TEXT, sources TEXT, engine TEXT, ts TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def conn() -> sqlite3.Connection:
    global _conn
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(settings.db_path, check_same_thread=False, timeout=30)
            _conn.row_factory = sqlite3.Row
            # default rollback journal (not WAL): safe on OneDrive/Dropbox-synced folders and network drives
            _conn.executescript(SCHEMA)
            _conn.commit()
        return _conn


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    with _lock:
        c = conn()
        cur = c.execute(sql, tuple(params))
        c.commit()
        return cur


def query(sql: str, params: Iterable[Any] = ()) -> list[dict]:
    with _lock:
        rows = conn().execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]


def one(sql: str, params: Iterable[Any] = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None


def jdump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def jload(v: str | None, default: Any = None) -> Any:
    if v is None or v == "":
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


def kv_get(key: str, default: str | None = None) -> str | None:
    r = one("SELECT value FROM kv WHERE key=?", (key,))
    return r["value"] if r else default


def kv_set(key: str, value: str) -> None:
    execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def log_activity(kind: str, message: str, meta: dict | None = None) -> None:
    execute("INSERT INTO activity(ts,kind,message,meta) VALUES(?,?,?,?)", (now(), kind, message, jdump(meta or {})))


def snapshot_playbook(event: str) -> None:
    r = one(
        "SELECT COUNT(*) n, COALESCE(SUM(evidence_count),0) e FROM lessons WHERE status IN ('retained','synthesis','injected')"
    )
    execute(
        "INSERT INTO playbook_snapshots(ts,lesson_count,evidence_total,event) VALUES(?,?,?,?)",
        (now(), r["n"], r["e"], event),
    )


def reset_all() -> None:
    with _lock:
        c = conn()
        for t in [
            "engagements", "notes", "sim_memories", "lessons", "workflows", "conflicts", "attack_runs",
            "activity", "access_log", "playbook_snapshots", "chat_messages",
        ]:
            c.execute(f"DELETE FROM {t}")
        c.execute("DELETE FROM kv WHERE key NOT IN ('mode_override')")
        c.commit()
