import os
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "ig_tracker.db")

os.makedirs(DATA_DIR, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS tracked_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(100) UNIQUE NOT NULL,
                full_name VARCHAR(200),
                avatar_url TEXT,
                ig_access_token TEXT DEFAULT NULL,
                ig_user_id TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migration for existing databases
        cols = [c["name"] for c in conn.execute("PRAGMA table_info(tracked_accounts)").fetchall()]
        if "ig_access_token" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN ig_access_token TEXT DEFAULT NULL")
        if "ig_user_id" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN ig_user_id TEXT DEFAULT NULL")
        if "region" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN region TEXT DEFAULT 'sk'")
        if "health_status" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN health_status TEXT DEFAULT 'healthy'")
        if "health_message" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN health_message TEXT DEFAULT 'Pripravené na použitie'")
        if "last_health_check" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN last_health_check TIMESTAMP DEFAULT NULL")
        if "usa_audience_pct" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN usa_audience_pct REAL DEFAULT NULL")
        if "fb_page_id" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN fb_page_id TEXT DEFAULT NULL")
        if "fb_page_name" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN fb_page_name TEXT DEFAULT NULL")
        if "fb_access_token" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN fb_access_token TEXT DEFAULT NULL")
        if "fb_enabled" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN fb_enabled INTEGER DEFAULT 1")
        if "top_countries_json" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN top_countries_json TEXT DEFAULT NULL")
        if "x_handle" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN x_handle TEXT DEFAULT NULL")
        if "is_burner" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN is_burner INTEGER DEFAULT 0")
        if "burner_vault_ids" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN burner_vault_ids TEXT DEFAULT ''")
        if "default_time" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN default_time TEXT DEFAULT '19:15'")
        if "default_jitter" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN default_jitter INTEGER DEFAULT 10")
        if "default_caption" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN default_caption TEXT DEFAULT ''")
        if "device_model" not in cols:
            conn.execute("ALTER TABLE tracked_accounts ADD COLUMN device_model TEXT DEFAULT 'Samsung Galaxy S24'")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                followers INTEGER DEFAULT 0,
                following INTEGER DEFAULT 0,
                posts_count INTEGER DEFAULT 0,
                top_reel_url TEXT,
                top_reel_views INTEGER DEFAULT 0,
                top_reel_likes INTEGER DEFAULT 0,
                total_views INTEGER DEFAULT 0,
                avg_views INTEGER DEFAULT 0,
                engagement_rate REAL DEFAULT 0.0,
                last_post_date TEXT,
                last_post_views INTEGER DEFAULT 0,
                last_post_url TEXT,
                last_post_likes INTEGER DEFAULT 0,
                usa_audience_pct REAL DEFAULT NULL,
                FOREIGN KEY(account_id) REFERENCES tracked_accounts(id) ON DELETE CASCADE
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_account ON snapshots(account_id, timestamp DESC)")

        # Migration for snapshots table
        snap_cols = [c["name"] for c in conn.execute("PRAGMA table_info(snapshots)").fetchall()]
        if "last_post_views" not in snap_cols:
            conn.execute("ALTER TABLE snapshots ADD COLUMN last_post_views INTEGER DEFAULT 0")
        if "last_post_url" not in snap_cols:
            conn.execute("ALTER TABLE snapshots ADD COLUMN last_post_url TEXT DEFAULT NULL")
        if "last_post_likes" not in snap_cols:
            conn.execute("ALTER TABLE snapshots ADD COLUMN last_post_likes INTEGER DEFAULT 0")
        if "usa_audience_pct" not in snap_cols:
            conn.execute("ALTER TABLE snapshots ADD COLUMN usa_audience_pct REAL DEFAULT NULL")

        # ── Media Vault: raw master videos ──────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS vault_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename VARCHAR(255) UNIQUE NOT NULL,
                original_name VARCHAR(255) NOT NULL,
                file_size INTEGER DEFAULT 0,
                duration_seconds REAL DEFAULT 0.0,
                width INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                thumbnail_path TEXT DEFAULT NULL,
                status TEXT DEFAULT 'available',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_vault_status ON vault_videos(status)")

        # Migration for vault_videos (Google Drive support, Usage Tracking & Tags)
        vault_cols = [c["name"] for c in conn.execute("PRAGMA table_info(vault_videos)").fetchall()]
        if "storage_type" not in vault_cols:
            conn.execute("ALTER TABLE vault_videos ADD COLUMN storage_type TEXT DEFAULT 'local'")
        if "gdrive_file_id" not in vault_cols:
            conn.execute("ALTER TABLE vault_videos ADD COLUMN gdrive_file_id TEXT DEFAULT NULL")
        if "gdrive_web_view_link" not in vault_cols:
            conn.execute("ALTER TABLE vault_videos ADD COLUMN gdrive_web_view_link TEXT DEFAULT NULL")
        if "media_type" not in vault_cols:
            conn.execute("ALTER TABLE vault_videos ADD COLUMN media_type TEXT DEFAULT 'video'")
        if "used_count" not in vault_cols:
            conn.execute("ALTER TABLE vault_videos ADD COLUMN used_count INTEGER DEFAULT 0")
        if "used_by_accounts" not in vault_cols:
            conn.execute("ALTER TABLE vault_videos ADD COLUMN used_by_accounts TEXT DEFAULT ''")
        if "last_used_at" not in vault_cols:
            conn.execute("ALTER TABLE vault_videos ADD COLUMN last_used_at TIMESTAMP DEFAULT NULL")
        if "tag" not in vault_cols:
            conn.execute("ALTER TABLE vault_videos ADD COLUMN tag TEXT DEFAULT 'Voľné'")
        if "folder_name" not in vault_cols:
            conn.execute("ALTER TABLE vault_videos ADD COLUMN folder_name TEXT DEFAULT ''")

        # ── Auto-Planner: scheduled / spoofed slots per account ──────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS planned_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                vault_video_id INTEGER,
                spoofed_video_path TEXT NOT NULL,
                thumbnail_path TEXT,
                scheduled_time TIMESTAMP NOT NULL,
                peak_window TEXT,
                caption TEXT DEFAULT '',
                hashtags TEXT DEFAULT '',
                first_comment TEXT DEFAULT '',
                status TEXT DEFAULT 'ready',
                published_at TIMESTAMP DEFAULT NULL,
                ig_media_id TEXT DEFAULT NULL,
                error_message TEXT DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(account_id) REFERENCES tracked_accounts(id) ON DELETE CASCADE,
                FOREIGN KEY(vault_video_id) REFERENCES vault_videos(id) ON DELETE SET NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_planned_acc_time ON planned_posts(account_id, scheduled_time)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_planned_status ON planned_posts(status)")

        # Migration for planned_posts (Multi-Platform crossposting & Jitter)
        plan_cols = [c["name"] for c in conn.execute("PRAGMA table_info(planned_posts)").fetchall()]
        if "post_to_ig" not in plan_cols:
            conn.execute("ALTER TABLE planned_posts ADD COLUMN post_to_ig INTEGER DEFAULT 1")
        if "post_to_fb" not in plan_cols:
            conn.execute("ALTER TABLE planned_posts ADD COLUMN post_to_fb INTEGER DEFAULT 1")
        if "post_to_x" not in plan_cols:
            conn.execute("ALTER TABLE planned_posts ADD COLUMN post_to_x INTEGER DEFAULT 0")
        if "fb_media_id" not in plan_cols:
            conn.execute("ALTER TABLE planned_posts ADD COLUMN fb_media_id TEXT DEFAULT NULL")
        if "fb_status" not in plan_cols:
            conn.execute("ALTER TABLE planned_posts ADD COLUMN fb_status TEXT DEFAULT 'pending'")
        if "fb_error" not in plan_cols:
            conn.execute("ALTER TABLE planned_posts ADD COLUMN fb_error TEXT DEFAULT NULL")
        if "x_caption" not in plan_cols:
            conn.execute("ALTER TABLE planned_posts ADD COLUMN x_caption TEXT DEFAULT NULL")
        if "jitter_minutes" not in plan_cols:
            conn.execute("ALTER TABLE planned_posts ADD COLUMN jitter_minutes INTEGER DEFAULT 10")
        if "is_manual_post" not in plan_cols:
            conn.execute("ALTER TABLE planned_posts ADD COLUMN is_manual_post INTEGER DEFAULT 0")
        if "is_skipped" not in plan_cols:
            conn.execute("ALTER TABLE planned_posts ADD COLUMN is_skipped INTEGER DEFAULT 0")

        # ── App Settings (Webhook URLs, intervals, etc.) ─────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


def format_number(val):
    """Sformátuje číslo do pekného skráteného tvaru (napr. 14.2k, 1.8M)."""
    if val is None:
        return "0"
    try:
        num = float(val)
    except (ValueError, TypeError):
        return "0"

    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    elif num >= 1_000:
        return f"{num / 1_000:.1f}k"
    return str(int(num))


def add_account(username, full_name="", avatar_url=""):
    username = username.strip().lstrip("@").lower()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO tracked_accounts (username, full_name, avatar_url)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                full_name = CASE WHEN excluded.full_name IS NOT NULL AND excluded.full_name != '' THEN excluded.full_name ELSE tracked_accounts.full_name END,
                avatar_url = CASE WHEN excluded.avatar_url IS NOT NULL AND excluded.avatar_url != '' THEN excluded.avatar_url ELSE tracked_accounts.avatar_url END
        """, (username, full_name, avatar_url))
        account_id = cur.lastrowid
        if not account_id:
            row = conn.execute("SELECT id FROM tracked_accounts WHERE username = ?", (username,)).fetchone()
            account_id = row["id"] if row else None
        return account_id


def delete_account(account_id):
    with get_db() as conn:
        conn.execute("DELETE FROM tracked_accounts WHERE id = ?", (account_id,))


def get_account_by_username(username):
    username = username.strip().lstrip("@").lower()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tracked_accounts WHERE username = ?", (username,)).fetchone()
        return dict(row) if row else None


def get_account_by_id(account_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM tracked_accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row) if row else None


def set_account_token(account_id, access_token, ig_user_id=None, region=None):
    with get_db() as conn:
        if region:
            conn.execute(
                "UPDATE tracked_accounts SET ig_access_token = ?, ig_user_id = ?, region = ? WHERE id = ?",
                (access_token or None, ig_user_id or None, region, account_id)
            )
        else:
            conn.execute(
                "UPDATE tracked_accounts SET ig_access_token = ?, ig_user_id = ? WHERE id = ?",
                (access_token or None, ig_user_id or None, account_id)
            )


def get_accounts_with_tokens():
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tracked_accounts WHERE ig_access_token IS NOT NULL AND ig_access_token != '' ORDER BY username ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_all_accounts():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM tracked_accounts ORDER BY username ASC").fetchall()
        return [dict(r) for r in rows]


def add_snapshot(account_id, followers, following, posts_count,
                 top_reel_url="", top_reel_views=0, top_reel_likes=0,
                 total_views=0, avg_views=0, engagement_rate=0.0,
                 last_post_date=None, last_post_views=0, last_post_url=None,
                 last_post_likes=0, usa_audience_pct=None):
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO snapshots (
                account_id, timestamp, followers, following, posts_count,
                top_reel_url, top_reel_views, top_reel_likes,
                total_views, avg_views, engagement_rate, last_post_date,
                last_post_views, last_post_url, last_post_likes, usa_audience_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            account_id, now_iso, followers, following, posts_count,
            top_reel_url, top_reel_views, top_reel_likes,
            total_views, avg_views, engagement_rate, last_post_date,
            last_post_views, last_post_url, last_post_likes, usa_audience_pct
        ))
        return cur.lastrowid


def get_latest_snapshot(account_id):
    with get_db() as conn:
        row = conn.execute("""
            SELECT * FROM snapshots
            WHERE account_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
        """, (account_id,)).fetchone()
        return dict(row) if row else None


def get_previous_snapshot(account_id):
    with get_db() as conn:
        row = conn.execute("""
            SELECT * FROM snapshots
            WHERE account_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1 OFFSET 1
        """, (account_id,)).fetchone()
        return dict(row) if row else None


def get_accounts_with_metrics():
    """Vráti zoznam všetkých účtov s najnovšími metrikami, deltou a formátovanými textami."""
    accounts = get_all_accounts()
    result = []

    for acc in accounts:
        aid = acc["id"]
        latest = get_latest_snapshot(aid)
        prev = get_previous_snapshot(aid)

        has_token = bool(acc["ig_access_token"]) if "ig_access_token" in acc.keys() and acc["ig_access_token"] else False
        ig_user_id = acc["ig_user_id"] if "ig_user_id" in acc.keys() else None
        region = acc["region"] if "region" in acc.keys() and acc["region"] else "sk"

        health_status = acc["health_status"] if "health_status" in acc.keys() and acc["health_status"] else "healthy"
        health_message = acc["health_message"] if "health_message" in acc.keys() and acc["health_message"] else "Pripravené na použitie"
        last_health_check = acc["last_health_check"] if "last_health_check" in acc.keys() else None

        # USA audience: buď zo snapshotu alebo priamo z profilu (fallback)
        acc_usa = acc["usa_audience_pct"] if "usa_audience_pct" in acc.keys() else None

        fb_page_id = acc["fb_page_id"] if "fb_page_id" in acc.keys() else None
        fb_page_name = acc["fb_page_name"] if "fb_page_name" in acc.keys() else None
        fb_enabled = acc["fb_enabled"] if "fb_enabled" in acc.keys() else 1
        x_handle = acc["x_handle"] if "x_handle" in acc.keys() else None
        is_burner = acc["is_burner"] if "is_burner" in acc.keys() and acc["is_burner"] is not None else 0
        burner_vault_ids = acc["burner_vault_ids"] if "burner_vault_ids" in acc.keys() and acc["burner_vault_ids"] else ""
        default_time = acc["default_time"] if "default_time" in acc.keys() and acc["default_time"] else "19:15"
        default_jitter = acc["default_jitter"] if "default_jitter" in acc.keys() and acc["default_jitter"] is not None else 10
        default_caption = acc["default_caption"] if "default_caption" in acc.keys() and acc["default_caption"] else ""
        device_model = acc["device_model"] if "device_model" in acc.keys() and acc["device_model"] else "Samsung Galaxy S24"

        if latest:
            followers = latest["followers"]
            prev_followers = prev["followers"] if prev else followers
            delta_followers = followers - prev_followers

            total_views = latest.get("total_views", 0) or 0
            prev_views = prev.get("total_views", 0) if prev else total_views
            if prev_views is None:
                prev_views = total_views
            delta_views = total_views - prev_views

            last_post_views = latest.get("last_post_views", 0) or 0
            last_post_url = latest.get("last_post_url")
            last_post_likes = latest.get("last_post_likes", 0) or 0
            snap_usa = latest.get("usa_audience_pct")
            usa_audience_pct = snap_usa if snap_usa is not None else acc_usa

            item = {
                "id": aid,
                "username": acc["username"],
                "full_name": acc["full_name"] or acc["username"],
                "avatar_url": acc["avatar_url"] or f"https://ui-avatars.com/api/?name={acc['username']}&background=random",
                "created_at": acc["created_at"],
                "has_token": has_token,
                "ig_user_id": ig_user_id,
                "region": region,
                "health_status": health_status,
                "health_message": health_message,
                "last_health_check": last_health_check,
                "has_data": True,
                "followers": followers,
                "followers_fmt": format_number(followers),
                "delta_followers": delta_followers,
                "delta_fmt": (f"+{delta_followers}" if delta_followers > 0 else str(delta_followers)),
                "following": latest["following"],
                "posts_count": latest["posts_count"],
                "total_views": total_views,
                "total_views_fmt": format_number(total_views) if total_views > 0 else "-",
                "delta_views": delta_views,
                "delta_views_fmt": (f"+{format_number(delta_views)}" if delta_views > 0 else ("0" if delta_views == 0 else f"-{format_number(abs(delta_views))}")),
                "avg_views": latest["avg_views"],
                "avg_views_fmt": format_number(latest["avg_views"]) if latest["avg_views"] > 0 else "-",
                "top_reel_url": latest["top_reel_url"],
                "top_reel_views": latest["top_reel_views"],
                "top_reel_views_fmt": format_number(latest["top_reel_views"]) if latest["top_reel_views"] > 0 else "-",
                "top_reel_likes": latest["top_reel_likes"],
                "top_reel_likes_fmt": format_number(latest["top_reel_likes"]) if latest["top_reel_likes"] > 0 else "-",
                "engagement_rate": latest["engagement_rate"],
                "last_post_date": latest["last_post_date"] or "Aktuálne",
                "last_post_views": last_post_views,
                "last_post_views_fmt": format_number(last_post_views) if last_post_views > 0 else str(last_post_views),
                "last_post_url": last_post_url,
                "last_post_likes": last_post_likes,
                "last_post_likes_fmt": format_number(last_post_likes) if last_post_likes > 0 else str(last_post_likes),
                "usa_audience_pct": round(usa_audience_pct, 1) if usa_audience_pct is not None else None,
                "fb_page_id": fb_page_id,
                "fb_page_name": fb_page_name,
                "fb_enabled": fb_enabled,
                "x_handle": x_handle,
                "is_burner": is_burner,
                "burner_vault_ids": burner_vault_ids,
                "default_time": default_time,
                "default_jitter": default_jitter,
                "default_caption": default_caption,
                "device_model": device_model,
                "last_updated": latest["timestamp"]
            }
        else:
            item = {
                "id": aid,
                "username": acc["username"],
                "full_name": acc["full_name"] or acc["username"],
                "avatar_url": acc["avatar_url"] or f"https://ui-avatars.com/api/?name={acc['username']}&background=random",
                "created_at": acc["created_at"],
                "has_token": has_token,
                "ig_user_id": ig_user_id,
                "region": region,
                "health_status": health_status,
                "health_message": health_message,
                "last_health_check": last_health_check,
                "has_data": False,
                "followers": 0,
                "followers_fmt": "--",
                "delta_followers": 0,
                "delta_fmt": "0",
                "following": 0,
                "posts_count": 0,
                "total_views": 0,
                "total_views_fmt": "--",
                "delta_views": 0,
                "delta_views_fmt": "0",
                "avg_views": 0,
                "avg_views_fmt": "--",
                "top_reel_url": None,
                "top_reel_views": 0,
                "top_reel_views_fmt": "--",
                "top_reel_likes": 0,
                "top_reel_likes_fmt": "--",
                "engagement_rate": 0.0,
                "last_post_date": "--",
                "last_post_views": 0,
                "last_post_views_fmt": "-",
                "last_post_url": None,
                "last_post_likes": 0,
                "last_post_likes_fmt": "-",
                "usa_audience_pct": round(acc_usa, 1) if acc_usa is not None else None,
                "fb_page_id": fb_page_id,
                "fb_page_name": fb_page_name,
                "fb_enabled": fb_enabled,
                "x_handle": x_handle,
                "is_burner": is_burner,
                "burner_vault_ids": burner_vault_ids,
                "default_time": default_time,
                "default_jitter": default_jitter,
                "default_caption": default_caption,
                "device_model": device_model,
                "last_updated": None
            }
        result.append(item)

    return result


def update_account_usa_audience(account_id, usa_audience_pct):
    """Aktualizuje podiel USA publika pre účet v tracked_accounts a v najnovšom snapshote."""
    with get_db() as conn:
        conn.execute("UPDATE tracked_accounts SET usa_audience_pct = ? WHERE id = ?", (usa_audience_pct, account_id))
        conn.execute("""
            UPDATE snapshots 
            SET usa_audience_pct = ? 
            WHERE id = (SELECT id FROM snapshots WHERE account_id = ? ORDER BY id DESC LIMIT 1)
        """, (usa_audience_pct, account_id))


# ─── Account Health Management ────────────────────────────────────────────────

def update_account_health(account_id, status, message):
    """Aktualizuje stav zdravia účtu (healthy, action_required, error)."""
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("""
            UPDATE tracked_accounts
            SET health_status = ?, health_message = ?, last_health_check = ?
            WHERE id = ?
        """, (status, message, now_iso, account_id))


def get_account_health(account_id):
    with get_db() as conn:
        row = conn.execute("""
            SELECT id, username, region, health_status, health_message, last_health_check, ig_access_token, ig_user_id
            FROM tracked_accounts WHERE id = ?
        """, (account_id,)).fetchone()
        return dict(row) if row else None


# ─── App Settings (Key-Value) ─────────────────────────────────────────────────

def get_setting(key, default=None):
    with get_db() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    now_iso = datetime.now(timezone.utc).isoformat()
    with get_db() as conn:
        conn.execute("""
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """, (key, value, now_iso))


def get_all_settings():
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
        return {r["key"]: r["value"] for r in rows}


# ─── Media Vault (Raw Videos) ─────────────────────────────────────────────────

def add_vault_video(filename, original_name, file_size=0, duration_seconds=0.0, width=0, height=0,
                    thumbnail_path=None, storage_type='local', gdrive_file_id=None, gdrive_web_view_link=None,
                    media_type='video', tag='Voľné', folder_name=''):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO vault_videos (
                filename, original_name, file_size, duration_seconds, width, height,
                thumbnail_path, status, storage_type, gdrive_file_id, gdrive_web_view_link,
                media_type, tag, folder_name
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'available', ?, ?, ?, ?, ?, ?)
        """, (filename, original_name, file_size, duration_seconds, width, height,
              thumbnail_path, storage_type, gdrive_file_id, gdrive_web_view_link,
              media_type, tag, folder_name))
        return cur.lastrowid


def update_vault_video_folder(video_id, folder_name):
    with get_db() as conn:
        conn.execute("UPDATE vault_videos SET folder_name = ? WHERE id = ?", (folder_name, video_id))


def get_all_vault_videos(status=None):
    with get_db() as conn:
        if status:
            rows = conn.execute("SELECT * FROM vault_videos WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM vault_videos ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]


def get_vault_video_by_id(video_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM vault_videos WHERE id = ?", (video_id,)).fetchone()
        return dict(row) if row else None


def update_vault_video_status(video_id, status):
    with get_db() as conn:
        conn.execute("UPDATE vault_videos SET status = ? WHERE id = ?", (status, video_id))


def mark_vault_video_used(video_id, account_username=None):
    """
    Označí master médium z Vaultu ako použité konkrétnym účtom.
    Zvýši used_count, pridá @username do zoznamu účtov, aktualizuje tag a status.
    """
    if not video_id:
        return
    now_iso = datetime.now(timezone.utc).isoformat()
    clean_user = (account_username or "").strip().lstrip("@")
    formatted_user = f"@{clean_user}" if clean_user else ""
    with get_db() as conn:
        row = conn.execute("SELECT used_count, used_by_accounts, tag FROM vault_videos WHERE id = ?", (video_id,)).fetchone()
        if not row:
            return
        curr_count = (row["used_count"] or 0) + 1
        curr_accounts = (row["used_by_accounts"] or "").strip()
        acc_list = [a.strip() for a in curr_accounts.split(",") if a.strip()]
        if formatted_user and formatted_user not in acc_list:
            acc_list.append(formatted_user)
        new_accounts_str = ", ".join(acc_list)

        # Build tag text
        if len(acc_list) == 1:
            new_tag = f"Použité ({acc_list[0]})"
        elif len(acc_list) > 1:
            new_tag = f"Použité ({len(acc_list)} účtov, {curr_count}x)"
        elif formatted_user:
            new_tag = f"Použité ({formatted_user})"
        else:
            new_tag = f"Použité ({curr_count}x)"

        conn.execute("""
            UPDATE vault_videos 
            SET used_count = ?,
                used_by_accounts = ?,
                last_used_at = ?,
                tag = ?,
                status = 'used'
            WHERE id = ?
        """, (curr_count, new_accounts_str, now_iso, new_tag, video_id))


def update_vault_video_tag(video_id, tag):
    """Manuálna úprava tagu média vo Vaulte."""
    with get_db() as conn:
        conn.execute("UPDATE vault_videos SET tag = ? WHERE id = ?", (tag, video_id))


def delete_vault_video(video_id):
    with get_db() as conn:
        row = conn.execute("SELECT filename, thumbnail_path, storage_type, gdrive_file_id FROM vault_videos WHERE id = ?", (video_id,)).fetchone()
        conn.execute("DELETE FROM vault_videos WHERE id = ?", (video_id,))
        return dict(row) if row else None


# ─── Auto-Planner & Scheduled Posts ───────────────────────────────────────────

def add_planned_post(account_id, vault_video_id, spoofed_video_path, scheduled_time,
                     peak_window=None, caption="", hashtags="", first_comment="", thumbnail_path=None):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO planned_posts (
                account_id, vault_video_id, spoofed_video_path, thumbnail_path,
                scheduled_time, peak_window, caption, hashtags, first_comment, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready')
        """, (
            account_id, vault_video_id, spoofed_video_path, thumbnail_path,
            scheduled_time, peak_window, caption, hashtags, first_comment
        ))
        return cur.lastrowid


def get_planned_posts(date_str=None, account_id=None, status=None):
    """
    Vráti plánované posty. date_str vo formáte 'YYYY-MM-DD'.
    Spája informácie o účte aj o pôvodnom videu vo Vaulte.
    """
    query = """
        SELECT p.*,
               a.username, a.full_name, a.avatar_url, a.region, a.health_status,
               v.original_name as master_video_name, v.duration_seconds, v.folder_name as vault_folder_name
        FROM planned_posts p
        JOIN tracked_accounts a ON a.id = p.account_id
        LEFT JOIN vault_videos v ON v.id = p.vault_video_id
        WHERE 1=1
    """
    params = []

    if date_str:
        query += " AND DATE(p.scheduled_time) = ?"
        params.append(date_str)
    if account_id:
        query += " AND p.account_id = ?"
        params.append(account_id)
    if status:
        query += " AND p.status = ?"
        params.append(status)

    query += " ORDER BY p.scheduled_time ASC"

    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_planned_post_by_id(post_id):
    with get_db() as conn:
        row = conn.execute("""
            SELECT p.*, a.username, a.full_name, a.ig_access_token, a.ig_user_id, a.region, a.health_status,
                   a.fb_page_id, a.fb_page_name, a.fb_access_token, a.fb_enabled
            FROM planned_posts p
            JOIN tracked_accounts a ON a.id = p.account_id
            WHERE p.id = ?
        """, (post_id,)).fetchone()
        return dict(row) if row else None


def update_planned_post(post_id, caption=None, hashtags=None, first_comment=None,
                        scheduled_time=None, status=None, published_at=None,
                        ig_media_id=None, error_message=None,
                        post_to_ig=None, post_to_fb=None, post_to_x=None,
                        fb_media_id=None, fb_status=None, fb_error=None,
                        x_caption=None, jitter_minutes=None):
    updates = []
    params = []

    if caption is not None:
        updates.append("caption = ?")
        params.append(caption)
    if hashtags is not None:
        updates.append("hashtags = ?")
        params.append(hashtags)
    if first_comment is not None:
        updates.append("first_comment = ?")
        params.append(first_comment)
    if scheduled_time is not None:
        updates.append("scheduled_time = ?")
        params.append(scheduled_time)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if published_at is not None:
        updates.append("published_at = ?")
        params.append(published_at)
    if ig_media_id is not None:
        updates.append("ig_media_id = ?")
        params.append(ig_media_id)
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
    if post_to_ig is not None:
        updates.append("post_to_ig = ?")
        params.append(int(post_to_ig))
    if post_to_fb is not None:
        updates.append("post_to_fb = ?")
        params.append(int(post_to_fb))
    if post_to_x is not None:
        updates.append("post_to_x = ?")
        params.append(int(post_to_x))
    if fb_media_id is not None:
        updates.append("fb_media_id = ?")
        params.append(fb_media_id)
    if fb_status is not None:
        updates.append("fb_status = ?")
        params.append(fb_status)
    if fb_error is not None:
        updates.append("fb_error = ?")
        params.append(fb_error)
    if x_caption is not None:
        updates.append("x_caption = ?")
        params.append(x_caption)
    if jitter_minutes is not None:
        updates.append("jitter_minutes = ?")
        params.append(int(jitter_minutes))

    if not updates:
        return

    params.append(post_id)
    sql = f"UPDATE planned_posts SET {', '.join(updates)} WHERE id = ?"
    with get_db() as conn:
        conn.execute(sql, params)


def update_account_fb_details(account_id, fb_page_id, fb_page_name=None, fb_access_token=None, fb_enabled=1):
    """Aktualizuje informácie o prepojenej Facebook Stránke pre daný účet."""
    with get_db() as conn:
        conn.execute("""
            UPDATE tracked_accounts
            SET fb_page_id = ?,
                fb_page_name = COALESCE(?, fb_page_name),
                fb_access_token = COALESCE(?, fb_access_token),
                fb_enabled = ?
            WHERE id = ?
        """, (fb_page_id or None, fb_page_name or None, fb_access_token or None, int(fb_enabled), account_id))


def update_account_demographics(account_id, top_countries_json, usa_audience_pct=None):
    """Uloží top krajiny a percento US publika z Meta Insights."""
    with get_db() as conn:
        if usa_audience_pct is not None:
            conn.execute("""
                UPDATE tracked_accounts
                SET top_countries_json = ?, usa_audience_pct = ?
                WHERE id = ?
            """, (top_countries_json, usa_audience_pct, account_id))
        else:
            conn.execute("""
                UPDATE tracked_accounts
                SET top_countries_json = ?
                WHERE id = ?
            """, (top_countries_json, account_id))


def delete_planned_post(post_id):
    with get_db() as conn:
        row = conn.execute("SELECT spoofed_video_path, thumbnail_path FROM planned_posts WHERE id = ?", (post_id,)).fetchone()
        conn.execute("DELETE FROM planned_posts WHERE id = ?", (post_id,))
        return dict(row) if row else None


def update_account_planner_settings(account_id, is_burner=None, burner_vault_ids=None,
                                    default_time=None, default_jitter=None,
                                    default_caption=None, device_model=None):
    """Aktualizuje nastavenia plánovača pre konkrétny profil."""
    updates = []
    params = []
    if is_burner is not None:
        updates.append("is_burner = ?")
        params.append(int(is_burner))
    if burner_vault_ids is not None:
        updates.append("burner_vault_ids = ?")
        params.append(str(burner_vault_ids))
    if default_time is not None:
        updates.append("default_time = ?")
        params.append(str(default_time))
    if default_jitter is not None:
        updates.append("default_jitter = ?")
        params.append(int(default_jitter))
    if default_caption is not None:
        updates.append("default_caption = ?")
        params.append(str(default_caption))
    if device_model is not None:
        updates.append("device_model = ?")
        params.append(str(device_model))

    if not updates:
        return
    params.append(account_id)
    with get_db() as conn:
        conn.execute(f"UPDATE tracked_accounts SET {', '.join(updates)} WHERE id = ?", params)


def apply_time_to_all_accounts(default_time, default_jitter=10):
    """Hromadne nastaví čas publikovania a jitter pre všetky účty."""
    with get_db() as conn:
        conn.execute("""
            UPDATE tracked_accounts
            SET default_time = ?, default_jitter = ?
        """, (default_time, int(default_jitter)))


def skip_planned_post(post_id):
    """Označí naplánovaný post ako preskočený a zruší jeho publikovanie."""
    with get_db() as conn:
        conn.execute("UPDATE planned_posts SET status = 'skipped', is_skipped = 1 WHERE id = ?", (post_id,))


def get_unposted_posts_by_account(account_id):
    """Vráti všetky čakajúce (nepublikované) posty daného účtu zoradené podľa času."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT p.*, v.original_name as video_original_name
            FROM planned_posts p
            LEFT JOIN vault_videos v ON v.id = p.vault_video_id
            WHERE p.account_id = ? AND p.status IN ('ready', 'scheduled')
            ORDER BY p.scheduled_time ASC
        """, (account_id,)).fetchall()
        return [dict(r) for r in rows]


