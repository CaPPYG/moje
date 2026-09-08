"""
BrainDump — Database layer (SQLite WAL, async via aiosqlite)
"""
import aiosqlite
import os
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "/home/patrik/server/BrainDump/braindump.db"))


from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db():
    """Open (or create) the SQLite DB with WAL mode enabled, yielding connection."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA synchronous=NORMAL")
        await db.execute("PRAGMA cache_size=-4096")   # 4 MB page cache
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db():
    """Create tables if they don't exist, run migrations."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                text        TEXT    NOT NULL,
                category    TEXT    NOT NULL DEFAULT 'Other',
                done        INTEGER NOT NULL DEFAULT 0,
                due_date    TEXT    DEFAULT NULL,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_done_cat
            ON tasks (done, category)
        """)

        # ── Migration: add due_date column to existing DB ──────────────────────
        # Must run BEFORE we try to create index on due_date
        cur = await db.execute("PRAGMA table_info(tasks)")
        columns = [row["name"] for row in await cur.fetchall()]
        if "due_date" not in columns:
            await db.execute("ALTER TABLE tasks ADD COLUMN due_date TEXT DEFAULT NULL")

        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_due_date
            ON tasks (due_date)
        """)

        await db.commit()
