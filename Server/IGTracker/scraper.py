import os
import re
import html
import json
import time
import requests
from datetime import datetime, timezone

import db

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
PROXIES_CACHE_FILE = os.path.join(DATA_DIR, "working_proxies.json")
APIFY_TOKEN_FILE = os.path.join(DATA_DIR, "apify_token.txt")

# Predvolený Apify token (načítava sa z ENV alebo data/apify_token.txt)
DEFAULT_APIFY_TOKEN = os.environ.get("APIFY_API_TOKEN", "")

CRAWLER_HEADERS = {
    'User-Agent': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def get_apify_token():
    """Získa Apify token z ENV, súboru data/apify_token.txt alebo predvolenej hodnoty."""
    token = os.environ.get("APIFY_API_TOKEN")
    if token and token.strip():
        return token.strip()
    if os.path.exists(APIFY_TOKEN_FILE):
        try:
            with open(APIFY_TOKEN_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content
        except Exception:
            pass
    return DEFAULT_APIFY_TOKEN


def parse_relative_time(ts_str):
    """Prevedie ISO čas na slovenský relatívny čas."""
    if not ts_str:
        return "Aktuálne"
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        diff = now - dt
        secs = int(diff.total_seconds())
        if secs < 3600:
            return f"pred {max(1, secs // 60)} min"
        elif secs < 86400:
            return f"pred {secs // 3600} h"
        elif secs < 172800:
            return "včera"
        else:
            days = secs // 86400
            if days == 1:
                return "pred 1 dňom"
            elif 2 <= days <= 4:
                return f"pred {days} dňami"
            return f"pred {days} dňami"
    except Exception:
        return "prednedávnom"


def parse_num(text):
    """Prevedie číslo v texte (napr. '271', '14.2k', '686M') na celé číslo."""
    if not text:
        return 0
    text = str(text).replace(',', '').replace(' ', '').strip().lower()
    mult = 1
    if text.endswith('k'):
        mult = 1000
        text = text[:-1]
    elif text.endswith('m'):
        mult = 1000000
        text = text[:-1]
    elif text.endswith('b'):
        mult = 1000000000
        text = text[:-1]
    try:
        return int(float(text) * mult)
    except Exception:
        return 0


# ─── 1. PARSER PRE APIFY VÝSTUP ─────────────────────────────────────────────

def parse_apify_reel_item(item, default_username=""):
    """Spracuje jeden video/reel záznam z Apify a extrahuje metriky, AI popis a témy."""
    if not isinstance(item, dict):
        return None

    shortcode = (item.get("shortCode") or item.get("code") or item.get("shortcode") or item.get("short_code") or "").strip()
    if not shortcode:
        u = item.get("url") or item.get("link") or ""
        m = re.search(r'/(?:reel|p)/([A-Za-z0-9_-]+)', u)
        if m:
            shortcode = m.group(1)
    if not shortcode:
        return None

    pk = str(item.get("id") or item.get("pk") or "")
    url = item.get("url") or f"https://www.instagram.com/reel/{shortcode}/"
    video_url = item.get("videoUrl") or item.get("video_url") or ""
    thumbnail_url = item.get("displayUrl") or item.get("thumbnailUrl") or item.get("thumbnail_url") or item.get("display_url") or ""

    views = int(
        item.get("videoPlayCount") or item.get("videoViewCount") or 
        item.get("playCount") or item.get("viewsCount") or 
        item.get("video_play_count") or item.get("video_view_count") or 
        item.get("view_count") or item.get("play_count") or 0
    )
    likes = int(item.get("likesCount") or item.get("likes_count") or item.get("like_count") or 0)
    comments = int(item.get("commentsCount") or item.get("comments_count") or item.get("comment_count") or 0)

    caption = item.get("caption") or item.get("text") or ""
    if isinstance(caption, dict):
        caption = caption.get("text") or ""
    elif isinstance(caption, list) and caption and isinstance(caption[0], dict):
        caption = caption[0].get("text") or ""

    timestamp = item.get("timestamp") or item.get("taken_at") or item.get("taken_at_timestamp")
    if isinstance(timestamp, (int, float)):
        taken_at = datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    elif isinstance(timestamp, datetime):
        taken_at = (timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)).isoformat()
    elif isinstance(timestamp, str) and timestamp.strip():
        clean_ts = timestamp.strip()
        if clean_ts.isdigit():
            taken_at = datetime.fromtimestamp(int(clean_ts), tz=timezone.utc).isoformat()
        else:
            try:
                dt = datetime.fromisoformat(clean_ts.replace("Z", "+00:00"))
                taken_at = dt.astimezone(timezone.utc).isoformat()
            except Exception:
                taken_at = clean_ts
    else:
        taken_at = datetime.now(timezone.utc).isoformat()

    is_pinned = 1 if item.get("isPinned") or item.get("is_pinned") or item.get("pinned") else 0

    # 🤖 AI Accessibility Caption (Meta Computer Vision Popis)
    accessibility_caption = item.get("accessibilityCaption") or item.get("accessibility_caption") or item.get("accessibility_text") or ""

    # 🏷️ AI Tematické kategórie (Content Taxonomy pills / topics)
    topics = []
    pills = item.get("relatedTopicPills") or item.get("related_topic_pills") or item.get("topics") or item.get("topic_pills") or []
    if isinstance(pills, list):
        for p in pills:
            if isinstance(p, dict):
                name = p.get("topic_name") or p.get("name") or p.get("title")
                if name and str(name).strip():
                    topics.append(str(name).strip())
            elif isinstance(p, str) and p.strip() and not p.startswith("#"):
                topics.append(p.strip())

    music_title = ""
    music_artist = ""
    m_info = item.get("musicInfo") or item.get("music_info")
    if isinstance(m_info, dict):
        music_title = m_info.get("song_name") or m_info.get("songName") or m_info.get("title") or ""
        music_artist = m_info.get("artist_name") or m_info.get("artistName") or m_info.get("artist") or ""

    return {
        "shortcode": shortcode,
        "pk": pk,
        "url": url,
        "video_url": video_url,
        "thumbnail_url": thumbnail_url,
        "views_count": views,
        "likes_count": likes,
        "comments_count": comments,
        "caption": caption,
        "taken_at": taken_at,
        "is_pinned": is_pinned,
        "accessibility_caption": accessibility_caption,
        "topics": topics,
        "topics_json": json.dumps(topics, ensure_ascii=False),
        "music_title": music_title,
        "music_artist": music_artist
    }


def _parse_apify_item(data, default_username=""):
    """Spracuje jeden záznam vrátený z Apify do štandardizovaného dictu."""
    username = (data.get("username") or default_username).strip().lstrip("@").lower()
    full_name = data.get("fullName") or username.capitalize()
    avatar_url = data.get("profilePicUrlHD") or data.get("profilePicUrl") or f"https://ui-avatars.com/api/?name={username}&background=random"
    followers = data.get("followersCount", 0)
    following = data.get("followsCount", 0)
    posts_count = data.get("postsCount", 0)
    bio = data.get("biography", "")

    posts = data.get("latestPosts", [])
    top_reel_url = None
    top_reel_views = 0
    top_reel_likes = 0
    total_views = 0
    video_count = 0
    total_likes = 0
    total_comments = 0

    # 1. Identifikácia skutočne najnovšieho postu (zoradením podľa timestamp zostupne, ignorujúc pinned posty na profile)
    sorted_by_date = sorted(
        posts,
        key=lambda p: p.get("timestamp") or "",
        reverse=True
    )
    last_post_date = None
    last_post_views = 0
    last_post_likes = 0
    last_post_url = None

    if sorted_by_date:
        newest = sorted_by_date[0]
        ts_newest = newest.get("timestamp")
        if ts_newest:
            last_post_date = parse_relative_time(ts_newest)
        last_post_views = newest.get("videoPlayCount") or newest.get("videoViewCount") or 0
        last_post_likes = newest.get("likesCount") or 0
        sc_newest = newest.get("shortCode")
        if sc_newest:
            if newest.get("type") == "Video" or last_post_views > 0:
                last_post_url = f"https://www.instagram.com/reel/{sc_newest}/"
            else:
                last_post_url = f"https://www.instagram.com/p/{sc_newest}/"

    # 2. Agregácia metrík (views, likes, top reel)
    for p in posts:
        p_type = p.get("type")
        shortcode = p.get("shortCode")
        views = p.get("videoPlayCount") or p.get("videoViewCount") or 0
        likes = p.get("likesCount") or 0
        comments = p.get("commentsCount") or 0

        total_likes += likes
        total_comments += comments

        if p_type == "Video" or views > 0:
            video_count += 1
            total_views += views
            if views >= top_reel_views:
                top_reel_views = views
                top_reel_likes = likes
                top_reel_url = f"https://www.instagram.com/reel/{shortcode}/"

    # Ak žiadne video nemalo views, ale existuje video, vyberieme prvé
    if not top_reel_url and posts:
        for p in posts:
            if p.get("type") == "Video":
                top_reel_url = f"https://www.instagram.com/reel/{p.get('shortCode')}/"
                top_reel_likes = p.get("likesCount") or 0
                break

    avg_views = (total_views // video_count) if video_count > 0 else 0
    sample_posts = max(1, min(len(posts), 12))
    engagement_rate = 0.0
    if followers > 0 and sample_posts > 0:
        avg_inter = (total_likes + total_comments) / sample_posts
        engagement_rate = round((avg_inter / followers) * 100, 2)

    return {
        "username": username,
        "full_name": full_name,
        "avatar_url": avatar_url,
        "bio": bio,
        "followers": followers,
        "following": following,
        "posts_count": posts_count,
        "top_reel_url": top_reel_url or f"https://www.instagram.com/{username}/",
        "top_reel_views": top_reel_views,
        "top_reel_likes": top_reel_likes,
        "total_views": total_views,
        "avg_views": avg_views,
        "engagement_rate": engagement_rate,
        "last_post_date": last_post_date or "Aktuálne",
        "last_post_views": last_post_views,
        "last_post_likes": last_post_likes,
        "last_post_url": last_post_url,
        "reels_count": video_count
    }


def _enrich_profiles_with_posts(profiles, posts_items):
    """
    Obohatí profily o skutočné videnia Reels (videoPlayCount),
    presné celkové zhliadnutia a identifikuje skutočný Top Reel (napr. virálne videá nad 100k).
    """
    from collections import defaultdict
    posts_by_user = defaultdict(list)
    single_user = list(profiles.keys())[0] if len(profiles) == 1 else ""
    for p in posts_items:
        u = (
            p.get("ownerUsername") or p.get("username") or p.get("owner_username") or
            (p.get("owner") or {}).get("username") or (p.get("user") or {}).get("username") or
            (p.get("input") or {}).get("username") or ""
        ).strip().lower()
        if not u and single_user:
            u = single_user
        if u:
            posts_by_user[u].append(p)

    for u, p_list in posts_by_user.items():
        if u not in profiles:
            continue
        prof = profiles[u]
        total_views = 0
        video_count = 0
        top_views = 0
        top_likes = 0
        top_url = prof.get("top_reel_url")
        total_likes = 0
        total_comments = 0
        # Identifikácia skutočne najnovšieho postu
        sorted_posts = sorted(
            p_list,
            key=lambda p: p.get("timestamp") or "",
            reverse=True
        )
        if sorted_posts:
            newest = sorted_posts[0]
            ts_newest = newest.get("timestamp")
            if ts_newest:
                prof["last_post_date"] = parse_relative_time(ts_newest)
            newest_views = newest.get("videoPlayCount") or newest.get("videoViewCount") or 0
            newest_likes = newest.get("likesCount") or 0
            prof["last_post_views"] = newest_views
            prof["last_post_likes"] = newest_likes
            sc_newest = newest.get("shortCode")
            if sc_newest:
                if newest.get("type") == "Video" or newest_views > 0:
                    prof["last_post_url"] = f"https://www.instagram.com/reel/{sc_newest}/"
                else:
                    prof["last_post_url"] = f"https://www.instagram.com/p/{sc_newest}/"

        for p in p_list:
            plays = p.get("videoPlayCount") or p.get("videoViewCount") or 0
            likes = p.get("likesCount") or 0
            comments = p.get("commentsCount") or 0
            shortcode = p.get("shortCode")

            total_likes += likes
            total_comments += comments

            if plays > 0:
                video_count += 1
                total_views += plays
                if plays > top_views:
                    top_views = plays
                    top_likes = likes
                    top_url = f"https://www.instagram.com/reel/{shortcode}/"

        if video_count > 0:
            prof["total_views"] = total_views
            prof["avg_views"] = total_views // video_count
            prof["reels_count"] = video_count

        if top_url and top_views > 0:
            prof["top_reel_url"] = top_url
            prof["top_reel_views"] = top_views
            prof["top_reel_likes"] = top_likes

        followers = prof.get("followers", 0)
        sample_posts = max(1, len(p_list))
        if followers > 0:
            prof["engagement_rate"] = round(((total_likes + total_comments) / sample_posts / followers) * 100, 2)

        # Uloženie stiahnutých reels do databázy ak profil už existuje v DB
        try:
            acc_row = db.get_account_by_username(u)
            if acc_row:
                parsed_batch = [parse_apify_reel_item(p, u) for p in p_list]
                parsed_batch = [r for r in parsed_batch if r and r.get("shortcode")]
                if parsed_batch:
                    db.upsert_reels_batch(acc_row["id"], parsed_batch)
                    db.sync_reels_summary_to_snapshot(acc_row["id"])
        except Exception as e_db:
            print(f"[Apify Batch] Nepodarilo sa uložiť reels pre @{u} do DB: {e_db}")


# ─── 2. PRIMÁRNY FETCHER: APIFY INSTAGRAM SCRAPER (SINGLE & BATCH) ─────────

def fetch_all_reels_apify(username, limit=100):
    """
    Jednorazové stiahnutie všetkých (alebo až limit) historical reels účtu cez Apify actor.
    Používa resultsType: 'reels' a directUrls: https://www.instagram.com/{user}/reels/
    """
    username = username.strip().lstrip("@").lower()
    token = get_apify_token()
    if not token:
        raise RuntimeError("Apify API token nie je nastavený. Nastavte APIFY_API_TOKEN alebo data/apify_token.txt")

    url = f"https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token={token}"

    payload = {
        "directUrls": [f"https://www.instagram.com/{username}/reels/"],
        "resultsType": "reels",
        "resultsLimit": limit
    }

    print(f"[Apify Reels] Spúšťam Apify scraper pre historical reels @{username} (limit {limit})...")
    resp = requests.post(url, json=payload, timeout=120)

    if resp.status_code == 401:
        raise RuntimeError("Apify API token je neplatný alebo expiroval. Skontrolujte nastavenie tokenu.")
    elif resp.status_code == 402:
        raise RuntimeError("Na Apify účte došiel kredit (Payment Required / Insufficient compute units).")
    elif resp.status_code == 429:
        raise RuntimeError("Apify hlási prekročenie limitu volaní (Rate Limited). Skúste o chvíľu.")

    items = []
    if resp.status_code in (200, 201):
        try:
            items = resp.json()
        except Exception:
            items = []

    # Ak resultsType 'reels' vrátil prázdno, skúsime fallback na posts s profilovou URL
    if not items or (isinstance(items, list) and len(items) == 0):
        print(f"[Apify Reels] resultsType: 'reels' nevrátilo dáta, skúšam s profilovou URL a resultsType: 'posts'...")
        payload_alt = {
            "directUrls": [f"https://www.instagram.com/{username}/"],
            "resultsType": "posts",
            "resultsLimit": limit
        }
        try:
            r_alt = requests.post(url, json=payload_alt, timeout=90)
            if r_alt.status_code in (200, 201):
                items = r_alt.json()
        except Exception as e_alt:
            print(f"[Apify Reels] Fallback dotaz zlyhal: {e_alt}")

    if not isinstance(items, list):
        raise RuntimeError(f"Neočakávaná odpoveď z Apify pre @{username}.")

    parsed_reels = []
    seen_codes = set()
    for it in items:
        if isinstance(it, dict) and not it.get("error"):
            p = parse_apify_reel_item(it, default_username=username)
            if p and p["shortcode"] and p["shortcode"] not in seen_codes:
                is_video = (
                    str(it.get("type", "")).lower() in ("video", "clip", "reel") or
                    bool(it.get("videoUrl") or it.get("video_url") or it.get("isVideo") or it.get("is_video") or it.get("productType") == "clips") or
                    p["views_count"] > 0 or
                    "/reel/" in p["url"] or
                    it.get("type") is None
                )
                if is_video:
                    seen_codes.add(p["shortcode"])
                    parsed_reels.append(p)

    print(f"[Apify Reels] Úspešne spracovaných {len(parsed_reels)} reels pre @{username}.")
    return parsed_reels


def fetch_via_apify(username):
    """Stiahne kompletný profil jedného používateľa cez Apify."""
    username = username.strip().lstrip("@").lower()
    res = fetch_profiles_batch([username])
    if username in res:
        return res[username]
    raise RuntimeError(f"Nepodarilo sa stiahnuť dáta pre @{username} cez Apify.")


def fetch_profiles_batch(usernames):
    """
    Stiahne viacero profilov naraz v Apify volaní:
    1. Detaily profilov (followers, following, avatar, bio)
    2. Všetky posty a reels s plným playCountom (skutočné videnia a virálne reels)
    """
    clean_usernames = [u.strip().lstrip("@").lower() for u in usernames if u.strip()]
    if not clean_usernames:
        return {}

    token = get_apify_token()
    if token:
        try:
            url = f"https://api.apify.com/v2/acts/apify~instagram-scraper/run-sync-get-dataset-items?token={token}"

            # 1. Krok: Získanie profilov
            payload_details = {
                "directUrls": [f"https://www.instagram.com/{u}/" for u in clean_usernames],
                "resultsType": "details"
            }
            print(f"[Apify Batch] Sťahujem profily pre {len(clean_usernames)} účtov...")
            r1 = requests.post(url, json=payload_details, timeout=90)
            results = {}
            if r1.status_code in (200, 201):
                items = r1.json()
                for it in items:
                    if not it.get("error"):
                        parsed = _parse_apify_item(it, it.get("username", ""))
                        results[parsed["username"].lower()] = parsed

            # 2. Krok: Získanie reels vrátane videoPlayCount (pre reálne celkové views a top viral reel)
            try:
                payload_reels = {
                    "directUrls": [f"https://www.instagram.com/{u}/reels/" for u in clean_usernames],
                    "resultsType": "reels",
                    "resultsLimit": 20
                }
                print(f"[Apify Batch] Sťahujem reels metriky (resultsType: 'reels') pre {len(clean_usernames)} účtov...")
                r2 = requests.post(url, json=payload_reels, timeout=60)
                posts_items = []
                if r2.status_code in (200, 201):
                    try:
                        posts_items = r2.json()
                    except Exception:
                        posts_items = []

                if not posts_items or (isinstance(posts_items, list) and len(posts_items) == 0):
                    payload_posts = {
                        "directUrls": [f"https://www.instagram.com/{u}/" for u in clean_usernames],
                        "resultsType": "posts",
                        "resultsLimit": 15
                    }
                    r2_alt = requests.post(url, json=payload_posts, timeout=60)
                    if r2_alt.status_code in (200, 201):
                        posts_items = r2_alt.json()

                if posts_items and isinstance(posts_items, list):
                    _enrich_profiles_with_posts(results, posts_items)
            except Exception as e_posts:
                print(f"[Apify Batch] Varovanie: načítanie reels metrík zlyhalo ({e_posts}), používam základné metriky.")

            if results:
                print(f"[Apify Batch] Úspešne stiahnutých a obohatených {len(results)}/{len(clean_usernames)} profilov.")
                return results
        except Exception as e:
            print(f"[Apify Batch] Chyba batch sťahovania: {e}. Prechádzam na fallback.")

    # Fallback: po jednom cez záložný crawler (iba ak Apify vôbec nevrátilo výsledky)
    results = {}
    for u in clean_usernames:
        try:
            c = fetch_via_crawler(u)
            if c:
                try:
                    recent_reels = fetch_recent_reels_html(u)
                    if recent_reels:
                        c["reels_count"] = len(recent_reels)
                        tot_v = sum(r.get("views_count", 0) for r in recent_reels)
                        if tot_v > 0:
                            c["total_views"] = tot_v
                            c["avg_views"] = tot_v // len(recent_reels)
                        best_r = max(recent_reels, key=lambda r: r.get("views_count", 0))
                        if best_r and best_r.get("views_count", 0) > 0:
                            c["top_reel_url"] = best_r.get("url")
                            c["top_reel_views"] = best_r.get("views_count", 0)
                            c["top_reel_likes"] = best_r.get("likes_count", 0)
                        acc_row = db.get_account_by_username(u)
                        if acc_row:
                            db.upsert_reels_batch(acc_row["id"], recent_reels)
                            db.sync_reels_summary_to_snapshot(acc_row["id"])
                except Exception as e_html:
                    print(f"Varovanie: HTML reels fetch pre @{u} v fallback batch zlyhal: {e_html}")
                results[u] = c
        except Exception as e:
            print(f"Fallback chyba pre @{u}: {e}")
    return results


# ─── 3. ZÁLOŽNÝ FETCHER: CRAWLER OPENGRAPH S PROXY ───────────────────────────

def get_proxy_candidates():
    candidates = []
    if os.path.exists(PROXIES_CACHE_FILE):
        try:
            with open(PROXIES_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    candidates.extend(data)
        except Exception:
            pass

    if len(candidates) < 5:
        try:
            url = 'https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=yes&anonymity=all'
            r = requests.get(url, timeout=4)
            if r.status_code == 200:
                fresh = [p.strip() for p in r.text.splitlines() if p.strip()]
                for p in fresh:
                    if p not in candidates:
                        candidates.append(p)
        except Exception:
            pass

    return candidates


def save_working_proxy(proxy_str):
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        cached = []
        if os.path.exists(PROXIES_CACHE_FILE):
            with open(PROXIES_CACHE_FILE, 'r', encoding='utf-8') as f:
                cached = json.load(f)
        if proxy_str in cached:
            cached.remove(proxy_str)
        cached.insert(0, proxy_str)
        with open(PROXIES_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cached[:25], f)
    except Exception:
        pass


def parse_instagram_html(username, html_text):
    clean_html = html.unescape(html_text)
    pattern = r'([\d\.,kmKMbB]+)\s*Followers?,\s*([\d\.,kmKMbB]+)\s*Following,\s*([\d\.,kmKMbB]+)\s*Posts?'
    m = re.search(pattern, clean_html, re.IGNORECASE)
    if not m:
        return None

    followers = parse_num(m.group(1))
    following = parse_num(m.group(2))
    posts_count = parse_num(m.group(3))

    full_name = username.capitalize()
    og_title_m = re.search(r'<meta\s+property="og:title"\s+content="([^"]*)"', clean_html)
    if og_title_m:
        title_val = og_title_m.group(1)
        name_m = re.search(r'^(.*?)\s*\(@[^\)]+\)', title_val)
        if name_m and name_m.group(1).strip():
            full_name = name_m.group(1).strip()

    avatar_url = f"https://ui-avatars.com/api/?name={username}&background=random"
    og_img_m = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', clean_html)
    if og_img_m and og_img_m.group(1).strip():
        avatar_url = og_img_m.group(1).strip()

    return {
        "username": username,
        "full_name": full_name,
        "avatar_url": avatar_url,
        "bio": "",
        "followers": followers,
        "following": following,
        "posts_count": posts_count,
        "top_reel_url": f"https://www.instagram.com/{username}/",
        "top_reel_views": 0,
        "top_reel_likes": 0,
        "total_views": 0,
        "avg_views": 0,
        "engagement_rate": 0.0,
        "last_post_date": "Aktuálne",
        "reels_count": 0
    }


def fetch_via_crawler(username):
    target_url = f"https://www.instagram.com/{username}/"
    # Používame výhradne overené proxy, nikdy nie priamy unproxied request z datacenter IP VPS
    candidates = get_proxy_candidates()
    for p in candidates[:3]:
        proxies = {'http': f'http://{p}', 'https': f'http://{p}'}
        try:
            r = requests.get(target_url, headers=CRAWLER_HEADERS, proxies=proxies, timeout=3)
            if r.status_code == 200 and 'follower' in r.text.lower():
                parsed = parse_instagram_html(username, r.text)
                if parsed:
                    save_working_proxy(p)
                    return parsed
        except Exception:
            continue

    return None


# ─── 4. REELS HTML SCRAPER (FAST INCREMENTAL & DETAILS) ─────────────────────

def extract_reels_from_json_node(obj, results=None, seen=None):
    """
    Rekurzívne vyhľadá mediálne objekty Reels v akomkoľvek JSON strome (Polaris, GraphQL, relay).
    """
    if results is None:
        results = []
    if seen is None:
        seen = set()

    if isinstance(obj, dict):
        code = (obj.get("code") or obj.get("shortcode") or obj.get("shortCode") or obj.get("short_code") or "").strip()
        if not code and obj.get("url"):
            m_code = re.search(r'/(?:reel|p)/([A-Za-z0-9_-]+)', obj.get("url") or "")
            if m_code:
                code = m_code.group(1)

        has_video_metric = (
            "play_count" in obj or "view_count" in obj or 
            "video_play_count" in obj or "video_view_count" in obj or
            "video_url" in obj or "clips_metadata" in obj or
            obj.get("is_video") is True or
            obj.get("media_type") == 2 or
            obj.get("product_type") == "clips" or
            obj.get("__typename") in ("XDTGraphVideo", "GraphVideo")
        )
        if code and has_video_metric and code not in seen:
            seen.add(code)
            pk = str(obj.get("id") or obj.get("pk") or "")
            url = f"https://www.instagram.com/reel/{code}/"

            views = int(
                obj.get("play_count") or obj.get("video_play_count") or 
                obj.get("view_count") or obj.get("video_view_count") or 
                (obj.get("metrics") or {}).get("play_count") or 0
            )

            likes = 0
            if "like_count" in obj:
                likes = int(obj.get("like_count") or 0)
            elif "likes_count" in obj or "likesCount" in obj:
                likes = int(obj.get("likes_count") or obj.get("likesCount") or 0)
            elif isinstance(obj.get("edge_liked_by"), dict):
                likes = int(obj["edge_liked_by"].get("count") or 0)
            elif isinstance(obj.get("edge_media_preview_like"), dict):
                likes = int(obj["edge_media_preview_like"].get("count") or 0)

            comments = 0
            if "comment_count" in obj:
                comments = int(obj.get("comment_count") or 0)
            elif "comments_count" in obj or "commentsCount" in obj:
                comments = int(obj.get("comments_count") or obj.get("commentsCount") or 0)
            elif isinstance(obj.get("edge_media_to_comment"), dict):
                comments = int(obj["edge_media_to_comment"].get("count") or 0)

            caption = ""
            cap_obj = obj.get("caption")
            if isinstance(cap_obj, dict):
                caption = cap_obj.get("text") or ""
            elif isinstance(cap_obj, str):
                caption = cap_obj
            elif isinstance(obj.get("edge_media_to_caption"), dict):
                edges = obj["edge_media_to_caption"].get("edges") or []
                if edges and isinstance(edges[0], dict) and isinstance(edges[0].get("node"), dict):
                    caption = edges[0]["node"].get("text") or ""

            taken_at_raw = obj.get("taken_at") or obj.get("taken_at_timestamp") or obj.get("timestamp")
            if isinstance(taken_at_raw, (int, float)):
                taken_at = datetime.fromtimestamp(taken_at_raw, tz=timezone.utc).isoformat()
            elif isinstance(taken_at_raw, str) and taken_at_raw.strip():
                clean_t = taken_at_raw.strip()
                if clean_t.isdigit():
                    taken_at = datetime.fromtimestamp(int(clean_t), tz=timezone.utc).isoformat()
                else:
                    try:
                        dt = datetime.fromisoformat(clean_t.replace("Z", "+00:00"))
                        taken_at = dt.astimezone(timezone.utc).isoformat()
                    except Exception:
                        taken_at = clean_t
            else:
                taken_at = datetime.now(timezone.utc).isoformat()

            thumbnail_url = (
                obj.get("display_url") or obj.get("thumbnail_src") or 
                obj.get("thumbnail_url") or ""
            )
            if not thumbnail_url and isinstance(obj.get("display_resources"), list) and obj["display_resources"]:
                thumbnail_url = obj["display_resources"][-1].get("src") or ""
            if not thumbnail_url and isinstance(obj.get("image_versions2"), dict):
                cands = obj["image_versions2"].get("candidates") or []
                if cands and isinstance(cands[0], dict):
                    thumbnail_url = cands[0].get("url") or ""

            video_url = obj.get("video_url") or ""

            # 🤖 AI Accessibility Caption (Meta Computer Vision Popis)
            accessibility_caption = (
                obj.get("accessibility_caption") or 
                obj.get("accessibilityCaption") or 
                obj.get("accessibility_text") or ""
            )

            # 🏷️ AI Tematické kategórie (Content Taxonomy pills / topics)
            topics = []
            pills = obj.get("related_topic_pills") or obj.get("relatedTopicPills") or obj.get("topics") or []
            if isinstance(pills, list):
                for p in pills:
                    if isinstance(p, dict):
                        n = p.get("topic_name") or p.get("name") or p.get("title")
                        if n:
                            topics.append(str(n).strip())
                    elif isinstance(p, str) and p.strip() and not p.startswith("#"):
                        topics.append(p.strip())

            music_title = ""
            music_artist = ""
            clips_meta = obj.get("clips_metadata")
            if isinstance(clips_meta, dict):
                audio_info = (
                    clips_meta.get("audio_ranking_info") or 
                    clips_meta.get("music_info") or 
                    clips_meta.get("original_sound_info")
                )
                if isinstance(audio_info, dict):
                    music_title = audio_info.get("song_name") or audio_info.get("title") or ""
                    music_artist = audio_info.get("artist_name") or audio_info.get("artist") or ""
            if not music_title and isinstance(obj.get("music_info"), dict):
                m_info = obj["music_info"]
                music_title = m_info.get("song_name") or m_info.get("title") or ""
                music_artist = m_info.get("artist_name") or m_info.get("artist") or ""

            results.append({
                "shortcode": code,
                "pk": pk,
                "url": url,
                "video_url": video_url,
                "thumbnail_url": thumbnail_url,
                "views_count": views,
                "likes_count": likes,
                "comments_count": comments,
                "caption": caption,
                "taken_at": taken_at,
                "is_pinned": 1 if obj.get("is_pinned") else 0,
                "accessibility_caption": accessibility_caption,
                "topics": topics,
                "topics_json": json.dumps(topics, ensure_ascii=False),
                "music_title": music_title,
                "music_artist": music_artist
            })

        for v in obj.values():
            if isinstance(v, (dict, list)):
                extract_reels_from_json_node(v, results, seen)

    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                extract_reels_from_json_node(item, results, seen)

    return results


def parse_reels_from_html(html_text, username=""):
    """
    Extrahuje zoznam Reels z HTML kódu stránky https://www.instagram.com/{user}/reels/
    alebo detailu https://www.instagram.com/reel/{code}/
    """
    reels = []
    seen = set()

    # 1. Hľadáme JSON skripty s ľubovoľným poradím atribútov: <script ... type="application/json" ...>
    scripts = re.findall(r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', html_text, re.DOTALL)
    for sc in scripts:
        try:
            sc_clean = sc.strip()
            if not sc_clean.startswith("{") and not sc_clean.startswith("["):
                continue
            data = json.loads(sc_clean)
            extract_reels_from_json_node(data, reels, seen)
        except Exception:
            continue

    # 1b. Ak nič nenašlo, skúsime nájsť skripty obsahujúce relay/polaris dáta
    if not reels:
        raw_scripts = re.findall(r'<script[^>]*>(.*?)</script>', html_text, re.DOTALL)
        for sc in raw_scripts:
            if "clips_graphql_connection" in sc or "PolarisProfilePosts" in sc or "xdt_api__v1__clips" in sc:
                m_json = re.search(r'(\{.*\}|\[.*\])', sc, re.DOTALL)
                if m_json:
                    try:
                        data = json.loads(m_json.group(1))
                        extract_reels_from_json_node(data, reels, seen)
                    except Exception:
                        pass

    # 2. Ak v JSON nič nenašlo, skúsime regex na odkazy na reels
    if not reels:
        reel_links = re.findall(r'/reel/([A-Za-z0-9_-]+)/', html_text)
        for code in set(reel_links):
            if code not in seen:
                seen.add(code)
                reels.append({
                    "shortcode": code,
                    "pk": "",
                    "url": f"https://www.instagram.com/reel/{code}/",
                    "video_url": "",
                    "thumbnail_url": "",
                    "views_count": 0,
                    "likes_count": 0,
                    "comments_count": 0,
                    "caption": "",
                    "taken_at": datetime.now(timezone.utc).isoformat(),
                    "is_pinned": 0,
                    "accessibility_caption": "",
                    "topics": [],
                    "topics_json": "[]",
                    "music_title": "",
                    "music_artist": ""
                })

    return reels


def fetch_recent_reels_html(username):
    """
    Rýchle inkrementálne stiahnutie najnovších Reels profilu z https://www.instagram.com/{user}/reels/
    Pomocou SSR JSON dát z Polaris / LoggedOut query (až 12 najnovších reels).
    """
    username = username.strip().lstrip("@").lower()
    target_url = f"https://www.instagram.com/{username}/reels/"
    fallback_url = f"https://www.instagram.com/{username}/"

    # 1. Skúsime priamy request s crawler hlavičkami
    for url_to_try in (target_url, fallback_url):
        try:
            r = requests.get(url_to_try, headers=CRAWLER_HEADERS, timeout=8)
            if r.status_code == 200:
                reels = parse_reels_from_html(r.text, username)
                if reels:
                    return reels[:12]
        except Exception as e:
            print(f"[HTML Fast Sync] Priamy request pre @{username} ({url_to_try}) zlyhal: {e}")

    # 2. Skúsime cez proxy pool
    candidates = get_proxy_candidates()
    for p in candidates[:3]:
        proxies = {'http': f'http://{p}', 'https': f'http://{p}'}
        for url_to_try in (target_url, fallback_url):
            try:
                r = requests.get(url_to_try, headers=CRAWLER_HEADERS, proxies=proxies, timeout=5)
                if r.status_code == 200:
                    reels = parse_reels_from_html(r.text, username)
                    if reels:
                        save_working_proxy(p)
                        return reels[:12]
            except Exception:
                continue

    return []


def fetch_reel_details_html(shortcode):
    """
    Stiahne detailné informácie o jednom reelsku z https://www.instagram.com/reel/{shortcode}/
    Extrahuje najmä:
    - accessibility_caption (🤖 AI vizuálny popis Meta CV)
    - related_topic_pills (🏷️ AI tematické kategórie)
    - direct video_url, thumbnail_url, likes, comments, music info
    """
    shortcode = shortcode.strip().replace("/", "")
    m = re.search(r'([A-Za-z0-9_-]+)', shortcode)
    if m:
        shortcode = m.group(1)
    target_url = f"https://www.instagram.com/reel/{shortcode}/"

    html_text = ""
    # 1. Priamy pokus
    try:
        r = requests.get(target_url, headers=CRAWLER_HEADERS, timeout=7)
        if r.status_code == 200:
            html_text = r.text
    except Exception:
        pass

    # 2. Skúška cez proxy
    if not html_text or ("accessibility_caption" not in html_text and "og:description" not in html_text):
        candidates = get_proxy_candidates()
        for p in candidates[:2]:
            proxies = {'http': f'http://{p}', 'https': f'http://{p}'}
            try:
                r = requests.get(target_url, headers=CRAWLER_HEADERS, proxies=proxies, timeout=4)
                if r.status_code == 200:
                    html_text = r.text
                    save_working_proxy(p)
                    break
            except Exception:
                continue

    if not html_text:
        return None

    # Parsovanie detailov cez JSON
    reels = parse_reels_from_html(html_text, "")
    for r in reels:
        if r.get("shortcode", "").strip("/").lower() == shortcode.lower():
            return r

    # Fallback na OpenGraph meta tagy
    og_desc = ""
    m_desc = re.search(r'<meta\s+(?:property="og:description"|name="description")\s+content="([^"]*)"', html_text)
    if m_desc:
        og_desc = html.unescape(m_desc.group(1))

    og_img = ""
    m_img = re.search(r'<meta\s+property="og:image"\s+content="([^"]*)"', html_text)
    if m_img:
        og_img = html.unescape(m_img.group(1))

    og_video = ""
    m_vid = re.search(r'<meta\s+property="og:video(?::secure_url)?"\s+content="([^"]*)"', html_text)
    if m_vid:
        og_video = html.unescape(m_vid.group(1))

    likes = 0
    comments = 0
    m_lc = re.search(r'([\d\.,kmKMbB]+)\s*likes?,\s*([\d\.,kmKMbB]+)\s*comments?', og_desc, re.IGNORECASE)
    if m_lc:
        likes = parse_num(m_lc.group(1))
        comments = parse_num(m_lc.group(2))

    acc_caption = ""
    m_acc = re.search(r'"accessibility_caption"\s*:\s*"((?:\\.|[^"\\])*)"', html_text)
    if m_acc:
        try:
            acc_caption = json.loads(f'"{m_acc.group(1)}"')
        except Exception:
            acc_caption = m_acc.group(1).replace(r'\"', '"').replace(r'\\', '\\')

    topics = []
    # Skúsime extrahovať related_topic_pills z HTML
    m_pills = re.search(r'"related_topic_pills"\s*:\s*(\[[^\]]+\])', html_text)
    if m_pills:
        try:
            pills_data = json.loads(m_pills.group(1))
            for p in pills_data:
                if isinstance(p, dict):
                    n = p.get("topic_name") or p.get("name")
                    if n:
                        topics.append(str(n).strip())
                elif isinstance(p, str) and p.strip():
                    topics.append(p.strip())
        except Exception:
            pass

    if not topics:
        topic_matches = re.findall(r'"topic_name"\s*:\s*"((?:\\.|[^"\\])*)"', html_text)
        for tm in topic_matches:
            try:
                clean_tm = json.loads(f'"{tm}"').strip()
            except Exception:
                clean_tm = tm.strip()
            if clean_tm and clean_tm not in topics:
                topics.append(clean_tm)

    if not topics and og_desc:
        tags = re.findall(r'#([A-Za-z0-9_áčďéíĺľňóôŕšťúýžÁČĎÉÍĹĽŇÓÔŔŠŤÚÝŽ]+)', og_desc)
        if tags:
            topics = [f"#{t}" for t in tags[:5]]

    return {
        "shortcode": shortcode,
        "pk": "",
        "url": target_url,
        "video_url": og_video,
        "thumbnail_url": og_img,
        "views_count": 0,
        "likes_count": likes,
        "comments_count": comments,
        "caption": og_desc,
        "taken_at": datetime.now(timezone.utc).isoformat(),
        "is_pinned": 0,
        "accessibility_caption": acc_caption,
        "topics": topics,
        "topics_json": json.dumps(topics, ensure_ascii=False),
        "music_title": "",
        "music_artist": ""
    }


# ─── 5. HLAVNÉ ROZHRANIE ─────────────────────────────────────────────────────

def fetch_profile(username):
    """
    Univerzálny fetcher:
    1. Najprv skúsi Apify (kompletné dáta: reels, views, likes, comments).
    2. Ak Apify zlyhá, použije záložný crawler cez proxy pool a skúsi inkrementálne reels.
    """
    username = username.strip().lstrip("@").lower()

    # 1. Apify
    try:
        return fetch_via_apify(username)
    except Exception as e:
        print(f"Apify scraper zlyhal pre @{username}: {e}. Skúšam záložný crawler...")

    # 2. Záložný crawler
    res = fetch_via_crawler(username)
    if res:
        try:
            recent_reels = fetch_recent_reels_html(username)
            if recent_reels:
                res["reels_count"] = len(recent_reels)
                tot_v = sum(r.get("views_count", 0) for r in recent_reels)
                if tot_v > 0:
                    res["total_views"] = tot_v
                    res["avg_views"] = tot_v // len(recent_reels)
                best_r = max(recent_reels, key=lambda r: r.get("views_count", 0))
                if best_r and best_r.get("views_count", 0) > 0:
                    res["top_reel_url"] = best_r.get("url")
                    res["top_reel_views"] = best_r.get("views_count", 0)
                    res["top_reel_likes"] = best_r.get("likes_count", 0)
                acc_row = db.get_account_by_username(username)
                if acc_row:
                    db.upsert_reels_batch(acc_row["id"], recent_reels)
                    db.sync_reels_summary_to_snapshot(acc_row["id"])
        except Exception as e_html:
            print(f"Varovanie: HTML reels fetch pre @{username} zlyhal: {e_html}")
        return res

    raise RuntimeError(f"Instagram dočasne obmedzil prístup pre @{username}. Skúste synchronizovať o chvíľu.")
