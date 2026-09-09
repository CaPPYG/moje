import os
import re
import html
import json
import time
import requests
from datetime import datetime, timezone

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
    for p in posts_items:
        u = (p.get("ownerUsername") or "").strip().lower()
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


# ─── 2. PRIMÁRNY FETCHER: APIFY INSTAGRAM SCRAPER (SINGLE & BATCH) ─────────

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

            # 2. Krok: Získanie posts & reels vrátane videoPlayCount (pre reálne celkové views a top viral reel)
            try:
                payload_posts = {
                    "directUrls": [f"https://www.instagram.com/{u}/" for u in clean_usernames],
                    "resultsType": "posts",
                    "resultsLimit": 35
                }
                print(f"[Apify Batch] Sťahujem reels metriky (playCount) pre {len(clean_usernames)} účtov...")
                r2 = requests.post(url, json=payload_posts, timeout=90)
                if r2.status_code in (200, 201):
                    posts_items = r2.json()
                    _enrich_profiles_with_posts(results, posts_items)
            except Exception as e_posts:
                print(f"[Apify Batch] Varovanie: načítanie posts metrík zlyhalo ({e_posts}), používam základné metriky.")

            if results:
                print(f"[Apify Batch] Úspešne stiahnutých a obohatených {len(results)}/{len(clean_usernames)} profilov.")
                return results
        except Exception as e:
            print(f"[Apify Batch] Chyba batch sťahovania: {e}. Prechádzam na fallback.")

    # Fallback: po jednom cez záložný crawler
    results = {}
    for u in clean_usernames:
        try:
            c = fetch_via_crawler(u)
            if c:
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
    for p in candidates[:20]:
        proxies = {'http': f'http://{p}', 'https': f'http://{p}'}
        try:
            r = requests.get(target_url, headers=CRAWLER_HEADERS, proxies=proxies, timeout=5)
            if r.status_code == 200 and 'follower' in r.text.lower():
                parsed = parse_instagram_html(username, r.text)
                if parsed:
                    save_working_proxy(p)
                    return parsed
        except Exception:
            continue

    return None


# ─── 4. HLAVNÉ ROZHRANIE ─────────────────────────────────────────────────────

def fetch_profile(username):
    """
    Univerzálny fetcher:
    1. Najprv skúsi Apify (kompletné dáta: reels, views, likes, comments).
    2. Ak Apify zlyhá, použije záložný crawler cez proxy pool.
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
        return res

    raise RuntimeError(f"Instagram dočasne obmedzil prístup pre @{username}. Skúste synchronizovať o chvíľu.")
