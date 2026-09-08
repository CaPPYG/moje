#!/usr/bin/env python3
"""SQLite uloziste - historia vzoriek. Jednoducha single-table schema."""
import os
import sqlite3
import threading
from datetime import datetime

_BASE = os.path.dirname(os.path.abspath(__file__))
_DB_PATH = os.path.join(_BASE, "data", "solar.db")
_lock = threading.Lock()


def _conn():
    conn = sqlite3.connect(_DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with _lock:
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL,
                kind TEXT NOT NULL,          -- 'esp' | 'vendor'
                data TEXT NOT NULL           -- JSON
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_samples_ts ON samples(ts)"
        )
        conn.commit()
        conn.close()


def save(kind: str, data: dict):
    ts = datetime.now().isoformat()
    with _lock:
        conn = _conn()
        conn.execute(
            "INSERT INTO samples (ts, kind, data) VALUES (?, ?, ?)",
            (ts, kind, __import__("json").dumps(data, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()


def recent(kind: str | None = None, limit: int = 200):
    sql = "SELECT ts, kind, data FROM samples"
    args = []
    if kind:
        sql += " WHERE kind = ?"
        args.append(kind)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with _lock:
        conn = _conn()
        rows = conn.execute(sql, args).fetchall()
        conn.close()
    out = []
    for r in rows:
        try:
            item = __import__("json").loads(r["data"])
        except Exception:
            item = {}
        item["ts"] = r["ts"]
        item["kind"] = r["kind"]
        out.append(item)
    return list(reversed(out))


def prune(days: int = 30):
    """Zmac stare zaznamy (30 dni)."""
    import json
    cutoff = datetime.now().fromtimestamp(
        datetime.now().timestamp() - days * 86400
    ).isoformat()
    with _lock:
        conn = _conn()
        conn.execute("DELETE FROM samples WHERE ts < ?", (cutoff,))
        conn.commit()
        conn.close()
