import os
import sqlite3
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "cloakhub.db")

os.makedirs(DATA_DIR, exist_ok=True)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as conn:
        # 1. Profiles (e.g. clara, default)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug VARCHAR(60) UNIQUE NOT NULL,
                name VARCHAR(120) NOT NULL,
                handle VARCHAR(60),
                bio TEXT,
                avatar_url TEXT,
                accent_color VARCHAR(20) DEFAULT '#f75ff2',
                followers_text VARCHAR(60) DEFAULT '120k+',
                age_text VARCHAR(20) DEFAULT '21',
                custom_domain VARCHAR(120) UNIQUE,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migrácia: zabezpečiť existenciu stĺpca custom_domain
        cols = [c[1] for c in conn.execute("PRAGMA table_info(profiles)").fetchall()]
        if "custom_domain" not in cols:
            conn.execute("ALTER TABLE profiles ADD COLUMN custom_domain VARCHAR(120)")

        # 2. Safe Links (shown to bots & crawlers: Instagram, TikTok, X, YouTube, etc.)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS safe_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                title VARCHAR(100) NOT NULL,
                platform VARCHAR(50) NOT NULL,
                url TEXT NOT NULL,
                accent_color VARCHAR(20) DEFAULT '#71767b',
                order_idx INTEGER DEFAULT 0,
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            )
        """)

        # 3. Cloaked Links (real VIP/monetization links shown only to real human visitors)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cloaked_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER NOT NULL,
                slug VARCHAR(60) UNIQUE NOT NULL,
                title VARCHAR(120) NOT NULL,
                destination_url TEXT NOT NULL,
                photo_url TEXT,
                badge_icon VARCHAR(50) DEFAULT 'lock',
                badge_text VARCHAR(50),
                is_adult INTEGER DEFAULT 1,
                is_active INTEGER DEFAULT 1,
                order_idx INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE CASCADE
            )
        """)

        # 4. Click & Visit Analytics (logs every real click and bot attempt)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analytics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id INTEGER,
                link_id INTEGER,
                event_type VARCHAR(20) NOT NULL, -- 'visit', 'bot_blocked', 'click'
                ip_hash VARCHAR(64),
                user_agent TEXT,
                device_type VARCHAR(20), -- 'ios', 'android', 'desktop', 'bot'
                referrer VARCHAR(200),
                country VARCHAR(10),
                bot_reason VARCHAR(100),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(profile_id) REFERENCES profiles(id) ON DELETE SET NULL,
                FOREIGN KEY(link_id) REFERENCES cloaked_links(id) ON DELETE SET NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_time ON analytics(timestamp DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_link ON analytics(link_id, event_type)")

        # Vložiť predvolený profil Clara Garz ak neexistuje
        cur = conn.cursor()
        cur.execute("SELECT id FROM profiles WHERE slug = 'clara'")
        row = cur.fetchone()
        if not row:
            cur.execute("""
                INSERT INTO profiles (slug, name, handle, bio, avatar_url, accent_color, followers_text, age_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                'clara',
                'Clara Garz',
                '@claragarz',
                'Hey, thanks for stopping by! Follow me across my socials below 💜',
                'https://scontent-yyz1-1.cdninstagram.com/v/t51.82787-19/784790444_18088966628258434_106770029639665066_n.jpg?stp=dst-jpg_s320x320_tt6&efg=eyJ2ZW5jb2RlX3RhZyI6InByb2ZpbGVfcGljLmRqYW5nby4xMDgwLmMyIn0&_nc_ht=scontent-yyz1-1.cdninstagram.com&_nc_cat=110&_nc_oc=Q6cZ2gFbmRFq_tQXwEgj7AEG8c7owl5HXQSxCZunU5BgSDLK8q_BLDHl0frNTcJVOJHNQ0I&_nc_ohc=yI_wCqHsnSgQ7kNvwHu9wF8&_nc_gid=jxpxbnvf42kLtFu-GYNenA&edm=AOQ1c0wBAAAA&ccb=7-5&oh=00_AQKP0I_qCXb9ph55C_glLUuO-FCcUn17gXLDU1jv7uv-Vg&oe=6AA49E24&_nc_sid=8b3546',
                '#f75ff2',
                '140k+',
                '21'
            ))
            clara_id = cur.lastrowid

            # Vložiť predvolené bezpečné odkazy (Safe links pre botov)
            safe_data = [
                ('Instagram', 'instagram', 'https://instagram.com/clara.garzz', '#E1306C', 0),
                ('X (Twitter)', 'x', 'https://x.com', '#71767b', 1),
                ('TikTok', 'tiktok', 'https://tiktok.com', '#FF2D55', 2),
                ('YouTube', 'youtube', 'https://youtube.com', '#FF0000', 3),
                ('Facebook', 'facebook', 'https://facebook.com', '#1877F2', 4),
            ]
            for title, plat, url, col, idx in safe_data:
                cur.execute("""
                    INSERT INTO safe_links (profile_id, title, platform, url, accent_color, order_idx)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (clara_id, title, plat, url, col, idx))

            # Vložiť ukážkový VIP cloaked link (napr. OnlyFans VIP)
            cur.execute("""
                INSERT INTO cloaked_links (profile_id, slug, title, destination_url, photo_url, badge_icon, badge_text, is_adult, order_idx)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                clara_id,
                'of-vip',
                'Exclusive VIP Fan Club 🔞',
                'https://onlyfans.com/clara.garzz',
                'https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=800&q=80',
                'fire',
                'HOT',
                1,
                0
            ))
            cur.execute("""
                INSERT INTO cloaked_links (profile_id, slug, title, destination_url, photo_url, badge_icon, badge_text, is_adult, order_idx)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                clara_id,
                'free-trial',
                'Free Trial Link (Limited)',
                'https://onlyfans.com/clara.garzz',
                '',
                'gift',
                'FREE',
                1,
                1
            ))


        # Predvolená doména pre profil Clara ak zatiaľ nie je nastavená
        conn.execute("UPDATE profiles SET custom_domain = 'claragarz.com' WHERE slug = 'clara' AND (custom_domain IS NULL OR custom_domain = '')")


# ─── Profil Helper Funkcie ─────────────────────────────────────────────────────

def get_profile(slug_or_domain='clara'):
    if not slug_or_domain:
        slug_or_domain = 'clara'
    clean = str(slug_or_domain).strip().lower()
    root_clean = clean[4:] if clean.startswith("www.") else clean

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE (slug = ? OR custom_domain = ? OR custom_domain = ? OR custom_domain = ?) AND is_active = 1",
            (slug_or_domain, clean, root_clean, f"www.{root_clean}")
        ).fetchone()
        if not row:
            # Fallback na prvý aktívny profil
            row = conn.execute("SELECT * FROM profiles WHERE is_active = 1 ORDER BY id ASC LIMIT 1").fetchone()
        return dict(row) if row else None


def get_profile_by_domain(domain):
    if not domain:
        return None
    clean = str(domain).strip().lower().split(":")[0]
    root_clean = clean[4:] if clean.startswith("www.") else clean
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM profiles WHERE (custom_domain = ? OR custom_domain = ? OR custom_domain = ?) AND is_active = 1",
            (clean, root_clean, f"www.{root_clean}")
        ).fetchone()
        return dict(row) if row else None


def update_custom_domain(profile_id, custom_domain):
    if custom_domain:
        clean = str(custom_domain).strip().lower()
        import re
        clean = re.sub(r"^https?://", "", clean).split("/")[0].split(":")[0]
        if clean.startswith("www."):
            clean = clean[4:]
    else:
        clean = None

    with get_db() as conn:
        conn.execute("UPDATE profiles SET custom_domain = ? WHERE id = ?", (clean, profile_id))
        return clean


def get_all_profiles():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM profiles ORDER BY id ASC").fetchall()
        return [dict(r) for r in rows]


def get_safe_links(profile_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM safe_links WHERE profile_id = ? ORDER BY order_idx ASC",
            (profile_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_cloaked_links(profile_id, only_active=True):
    with get_db() as conn:
        query = "SELECT * FROM cloaked_links WHERE profile_id = ?"
        if only_active:
            query += " AND is_active = 1"
        query += " ORDER BY order_idx ASC"
        rows = conn.execute(query, (profile_id,)).fetchall()
        return [dict(r) for r in rows]


def get_cloaked_link_by_slug(slug):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM cloaked_links WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None


# ─── CRUD Operácie pre Admin ──────────────────────────────────────────────────

def add_cloaked_link(profile_id, slug, title, destination_url, photo_url='', badge_icon='lock', badge_text='', is_adult=1):
    slug = slug.strip().lower().replace(" ", "-")
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cloaked_links (profile_id, slug, title, destination_url, photo_url, badge_icon, badge_text, is_adult)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (profile_id, slug, title, destination_url, photo_url, badge_icon, badge_text, is_adult))
        return cur.lastrowid


def update_cloaked_link(link_id, title, destination_url, photo_url='', badge_icon='lock', badge_text='', is_adult=1, is_active=1):
    with get_db() as conn:
        conn.execute("""
            UPDATE cloaked_links
            SET title = ?, destination_url = ?, photo_url = ?, badge_icon = ?, badge_text = ?, is_adult = ?, is_active = ?
            WHERE id = ?
        """, (title, destination_url, photo_url, badge_icon, badge_text, is_adult, is_active, link_id))


def delete_cloaked_link(link_id):
    with get_db() as conn:
        conn.execute("DELETE FROM cloaked_links WHERE id = ?", (link_id,))


def update_profile(profile_id, name, handle, bio, avatar_url, accent_color, followers_text, age_text):
    with get_db() as conn:
        conn.execute("""
            UPDATE profiles
            SET name = ?, handle = ?, bio = ?, avatar_url = ?, accent_color = ?, followers_text = ?, age_text = ?
            WHERE id = ?
        """, (name, handle, bio, avatar_url, accent_color, followers_text, age_text, profile_id))


# ─── Analytika ────────────────────────────────────────────────────────────────

def log_event(profile_id=None, link_id=None, event_type='visit', ip_hash='', user_agent='', device_type='', referrer='', country='', bot_reason=''):
    with get_db() as conn:
        conn.execute("""
            INSERT INTO analytics (profile_id, link_id, event_type, ip_hash, user_agent, device_type, referrer, country, bot_reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (profile_id, link_id, event_type, ip_hash, user_agent[:250], device_type, referrer[:200], country, bot_reason))


def get_analytics_summary(profile_id=None):
    with get_db() as conn:
        cur = conn.cursor()
        p_filter = "WHERE profile_id = ?" if profile_id else ""
        p_params = (profile_id,) if profile_id else ()

        total_visits = cur.execute(f"SELECT COUNT(*) FROM analytics {p_filter} {'AND' if profile_id else 'WHERE'} event_type = 'visit'", p_params).fetchone()[0]
        total_clicks = cur.execute(f"SELECT COUNT(*) FROM analytics {p_filter} {'AND' if profile_id else 'WHERE'} event_type = 'click'", p_params).fetchone()[0]
        total_bots = cur.execute(f"SELECT COUNT(*) FROM analytics {p_filter} {'AND' if profile_id else 'WHERE'} event_type = 'bot_blocked'", p_params).fetchone()[0]

        # Kliknutia na jednotlivé odkazy
        link_stats = cur.execute("""
            SELECT cl.id, cl.title, cl.slug, cl.destination_url, COUNT(a.id) as clicks
            FROM cloaked_links cl
            LEFT JOIN analytics a ON cl.id = a.link_id AND a.event_type = 'click'
            GROUP BY cl.id
            ORDER BY clicks DESC
        """).fetchall()

        # Zariadenia (iOS vs Android vs Desktop)
        devices = cur.execute("""
            SELECT device_type, COUNT(*) as cnt
            FROM analytics
            WHERE event_type IN ('visit', 'click')
            GROUP BY device_type
        """).fetchall()

        # Posledné udalosti
        recent_logs = cur.execute("""
            SELECT a.*, cl.title as link_title
            FROM analytics a
            LEFT JOIN cloaked_links cl ON a.link_id = cl.id
            ORDER BY a.timestamp DESC
            LIMIT 25
        """).fetchall()

        return {
            "total_visits": total_visits,
            "total_clicks": total_clicks,
            "total_bots_blocked": total_bots,
            "link_stats": [dict(r) for r in link_stats],
            "devices": {r["device_type"] or "unknown": r["cnt"] for r in devices},
            "recent_logs": [dict(r) for r in recent_logs]
        }
