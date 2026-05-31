"""Trade tracker DB layer — local SQLite or Turso (libsql) via env.

If TURSO_DATABASE_URL + TURSO_AUTH_TOKEN are set, uses libsql-experimental
embedded replica (writes go to local tmp + sync to Turso). Otherwise plain
sqlite3 on a local file. Returns rows as dicts so caller code is identical
on both backends.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "")
TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")
USE_TURSO = bool(TURSO_URL and TURSO_TOKEN)

LOCAL_DB = Path(os.environ.get("TRADES_DB", "trades.db"))
# Writable scratch for the embedded replica on the host (Streamlit Cloud = Linux)
REPLICA_DB = Path("/tmp/trades_replica.db") if os.name != "nt" else Path("trades_replica.db")

if USE_TURSO:
    import libsql_experimental as libsql  # type: ignore

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT,
    updated_at      TEXT,
    entry_type      TEXT DEFAULT 'live',
    status          TEXT DEFAULT 'open',
    date            TEXT,
    asset           TEXT,
    direction       TEXT,
    timeframe       TEXT,
    session         TEXT,
    htf_bias        TEXT,
    sweep_state     TEXT,
    entry_trigger   TEXT,
    cisd_confirmed  TEXT,
    bias_alignment  TEXT,
    entry_price     REAL,
    exit_price      REAL,
    size            REAL,
    planned_sl      REAL,
    planned_tp      REAL,
    planned_rr      REAL,
    actual_r        REAL,
    outcome         TEXT,
    holding_minutes INTEGER,
    emotion         TEXT,
    followed_rules  INTEGER,
    confidence      INTEGER,
    screenshot_blob BLOB,
    notes           TEXT
);
"""

FIELDS = [
    "entry_type", "status", "date", "asset", "direction", "timeframe",
    "session", "htf_bias", "sweep_state", "entry_trigger", "cisd_confirmed",
    "bias_alignment", "entry_price", "exit_price", "size", "planned_sl",
    "planned_tp", "planned_rr", "actual_r", "outcome", "holding_minutes",
    "emotion", "followed_rules", "confidence", "screenshot_blob", "notes",
]


def get_conn():
    if USE_TURSO:
        REPLICA_DB.parent.mkdir(parents=True, exist_ok=True)
        conn = libsql.connect(str(REPLICA_DB), sync_url=TURSO_URL, auth_token=TURSO_TOKEN)
        try:
            conn.sync()  # pull latest from Turso
        except Exception:
            pass
        return conn
    LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(LOCAL_DB), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _commit_and_push(conn):
    conn.commit()
    if USE_TURSO:
        try:
            conn.sync()  # push writes to Turso
        except Exception:
            pass


def init_schema():
    conn = get_conn()
    # libsql lacks executescript; run the single CREATE TABLE statement.
    conn.execute(SCHEMA_SQL.strip().rstrip(";"))
    _commit_and_push(conn)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _rows_as_dicts(cur, rows):
    if not rows:
        return []
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in rows]


def _fetchall(sql, params=()):
    conn = get_conn()
    cur = conn.execute(sql, tuple(params))
    rows = cur.fetchall()
    return _rows_as_dicts(cur, rows)


def insert_trade(data: dict) -> int:
    cols = [c for c in FIELDS if c in data]
    placeholders = ", ".join("?" for _ in cols)
    sql = (
        f"INSERT INTO trades (created_at, updated_at, {', '.join(cols)}) "
        f"VALUES (?, ?, {placeholders})"
    )
    params = tuple([_now(), _now()] + [data[c] for c in cols])
    conn = get_conn()
    cur = conn.execute(sql, params)
    _commit_and_push(conn)
    return cur.lastrowid


def update_trade(trade_id: int, data: dict):
    cols = [c for c in FIELDS if c in data]
    if not cols:
        return
    set_clause = ", ".join(f"{c}=?" for c in cols)
    sql = f"UPDATE trades SET updated_at=?, {set_clause} WHERE id=?"
    params = tuple([_now()] + [data[c] for c in cols] + [trade_id])
    conn = get_conn()
    conn.execute(sql, params)
    _commit_and_push(conn)


def delete_trade(trade_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM trades WHERE id=?", (trade_id,))
    _commit_and_push(conn)


def get_trade(trade_id: int):
    rows = _fetchall("SELECT * FROM trades WHERE id=?", (trade_id,))
    return rows[0] if rows else None


def all_trades():
    return _fetchall("SELECT * FROM trades ORDER BY date DESC, id DESC")


def open_trades():
    return _fetchall("SELECT * FROM trades WHERE status='open' ORDER BY date DESC, id DESC")


def read_upload_bytes(uploaded_file) -> bytes | None:
    """Read an uploaded Streamlit file into bytes for BLOB storage."""
    if uploaded_file is None:
        return None
    return bytes(uploaded_file.getbuffer())
