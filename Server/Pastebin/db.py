#!/usr/bin/env python3
"""
PasteBin – Databázový model (SQLite) a správa úložísk.
"""
import os
import sqlite3
import datetime
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "pastes.db")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def generate_id(length=7):
    """Generuje bezpečný a krátky alfanumerický identifikátor."""
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pastes (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                content TEXT,
                file_path TEXT,
                file_mime TEXT,
                password_hash TEXT,
                burn_after_reading INTEGER DEFAULT 0,
                views_count INTEGER DEFAULT 0,
                expires_at TEXT,
                created_at TEXT NOT NULL
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_expires_at ON pastes(expires_at);")
        conn.commit()


def hash_password(password):
    """Zahashuje heslo pomocou bcrypt alebo werkzeug scrypt."""
    if not password:
        return None
    try:
        import bcrypt
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    except Exception:
        from werkzeug.security import generate_password_hash
        return generate_password_hash(password, method="scrypt")


def verify_password(password, hashed):
    """Overí zadané heslo voči hashu."""
    if not hashed:
        return True
    if not password:
        return False
    try:
        import bcrypt
        if hashed.startswith("$2b$") or hashed.startswith("$2a$"):
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        pass
    from werkzeug.security import check_password_hash
    return check_password_hash(hashed, password)


def create_paste(type_, content=None, file_path=None, file_mime=None,
                 password=None, burn_after_reading=False, ttl_seconds=None):
    init_db()
    paste_id = generate_id()
    # Zabezpečíme unikátnosť
    with get_db() as conn:
        while conn.execute("SELECT 1 FROM pastes WHERE id = ?", (paste_id,)).fetchone():
            paste_id = generate_id()

    now = datetime.datetime.now(datetime.timezone.utc)
    created_at = now.isoformat()

    expires_at = None
    if ttl_seconds and int(ttl_seconds) > 0:
        exp_dt = now + datetime.timedelta(seconds=int(ttl_seconds))
        expires_at = exp_dt.isoformat()

    pw_hash = hash_password(password) if password else None
    burn = 1 if burn_after_reading else 0

    with get_db() as conn:
        conn.execute("""
            INSERT INTO pastes (id, type, content, file_path, file_mime,
                               password_hash, burn_after_reading, views_count,
                               expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
        """, (paste_id, type_, content, file_path, file_mime, pw_hash, burn, expires_at, created_at))
        conn.commit()

    return {
        "id": paste_id,
        "type": type_,
        "burn_after_reading": bool(burn),
        "expires_at": expires_at,
        "created_at": created_at
    }


def get_paste(paste_id):
    """Načíta záznam alebo vráti None ak neexistuje alebo expiroval."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM pastes WHERE id = ?", (paste_id,)).fetchone()
        if not row:
            return None

        data = dict(row)
        # Kontrola expirácie
        if data.get("expires_at"):
            try:
                exp_dt = datetime.datetime.fromisoformat(data["expires_at"])
                now = datetime.datetime.now(datetime.timezone.utc)
                if exp_dt < now:
                    delete_paste(paste_id)
                    return None
            except Exception:
                pass

        return data


def increment_views(paste_id):
    with get_db() as conn:
        conn.execute("UPDATE pastes SET views_count = views_count + 1 WHERE id = ?", (paste_id,))
        conn.commit()


def delete_paste(paste_id):
    """Natrvalo zmaže záznam z databázy a prípadný obrázok z disku."""
    with get_db() as conn:
        row = conn.execute("SELECT file_path FROM pastes WHERE id = ?", (paste_id,)).fetchone()
        if row and row["file_path"]:
            full_path = os.path.join(DATA_DIR, row["file_path"])
            if os.path.isfile(full_path):
                try:
                    os.remove(full_path)
                except Exception:
                    pass
        cur = conn.execute("DELETE FROM pastes WHERE id = ?", (paste_id,))
        conn.commit()
        return cur.rowcount > 0


def cleanup_expired():
    """Nájde a zmaže všetky expirované záznamy."""
    init_db()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM pastes WHERE expires_at IS NOT NULL AND expires_at < ?", (now_iso,)).fetchall()
        for r in rows:
            delete_paste(r["id"])


def get_all_pastes(include_expired=False):
    """Vráti zoznam všetkých aktívnych záznamov zoradených od najnovšieho."""
    init_db()
    if not include_expired:
        cleanup_expired()
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, type, content, file_path, file_mime,
                   (password_hash IS NOT NULL AND password_hash != '') AS has_password,
                   burn_after_reading, views_count, expires_at, created_at
            FROM pastes
            ORDER BY created_at DESC
        """).fetchall()
        result = []
        for r in rows:
            item = dict(r)
            item["has_password"] = bool(item["has_password"])
            item["burn_after_reading"] = bool(item["burn_after_reading"])
            result.append(item)
        return result
