"""
IG Publisher & Insights — Instagram Graph API v20.0 wrapper
Supports: profile data, media list, insights, photo/reel publishing
"""
import httpx
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

IG_API_BASE = "https://graph.instagram.com/v20.0"

# Token stored in env — set IG_ACCESS_TOKEN in environment or .env
def get_token() -> Optional[str]:
    return os.environ.get("IG_ACCESS_TOKEN", "")


# ─── Profile ─────────────────────────────────────────────────────────────────

def get_profile(token: str) -> dict:
    """Fetch basic profile info for the token owner."""
    r = httpx.get(
        f"{IG_API_BASE}/me",
        params={
            "fields": "id,username,name,biography,followers_count,follows_count,media_count,profile_picture_url,website",
            "access_token": token,
        },
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def verify_token(token: str) -> dict:
    """Verify if an access token is valid and return basic details."""
    try:
        r = httpx.get(
            f"{IG_API_BASE}/me",
            params={
                "fields": "id,username,name",
                "access_token": token,
            },
            timeout=10,
        )
        data = r.json()
        if "error" in data:
            return {"valid": False, "error": data["error"].get("message", "Neplatný token")}
        return {
            "valid": True,
            "id": data.get("id"),
            "username": data.get("username"),
            "name": data.get("name")
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


# ─── Media ───────────────────────────────────────────────────────────────────

def get_media(token: str, limit: int = 20) -> list[dict]:
    """Fetch recent media posts with engagement data."""
    r = httpx.get(
        f"{IG_API_BASE}/me/media",
        params={
            "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp,like_count,comments_count",
            "limit": limit,
            "access_token": token,
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("data", [])


def get_media_insights(token: str, media_id: str) -> dict:
    """Fetch insights for a specific media object."""
    # Different metrics depending on media type
    r = httpx.get(
        f"{IG_API_BASE}/{media_id}/insights",
        params={
            "metric": "reach,impressions,saved,video_views,total_interactions",
            "access_token": token,
        },
        timeout=10,
    )
    data = r.json()
    if "error" in data:
        return {}
    result = {}
    for item in data.get("data", []):
        result[item["name"]] = item.get("values", [{"value": 0}])[0].get("value", 0)
    return result


# ─── Account Insights ─────────────────────────────────────────────────────────

def get_account_insights(token: str, days: int = 30) -> dict:
    """Fetch account-level insights for the past N days (max 30)."""
    import time
    since = int(time.time()) - (days * 86400)
    until = int(time.time())

    metrics = ["reach", "profile_views", "total_interactions", "follower_count"]
    result = {}

    for metric in metrics:
        try:
            r = httpx.get(
                f"{IG_API_BASE}/me/insights",
                params={
                    "metric": metric,
                    "period": "day",
                    "since": since,
                    "until": until,
                    "access_token": token,
                },
                timeout=10,
            )
            data = r.json()
            if "data" in data and data["data"]:
                values = data["data"][0].get("values", [])
                result[metric] = values  # list of {value, end_time}
        except Exception as e:
            logger.warning(f"Insights fetch failed for {metric}: {e}")

    return result


def get_audience_country(token: str) -> Optional[dict]:
    """
    Pokúsi sa získať demografiu publika (rozpad podľa krajín) cez Meta Graph API.
    Poznámka: Vyžaduje oprávnenie instagram_manage_insights na tokene.
    """
    try:
        r = httpx.get(
            f"{IG_API_BASE}/me/insights",
            params={
                "metric": "follower_demographics",
                "period": "lifetime",
                "breakdown": "country",
                "access_token": token,
            },
            timeout=10,
        )
        data = r.json()
        if "data" in data and data["data"]:
            breakdowns = data["data"][0].get("total_value", {}).get("breakdowns", [])
            if breakdowns:
                results = {}
                total = 0
                for item in breakdowns[0].get("results", []):
                    c = item.get("dimension_values", [""])[0]
                    v = item.get("value", 0)
                    results[c] = v
                    total += v
                us_count = results.get("US", 0)
                us_pct = round((us_count / total * 100), 1) if total > 0 else 0.0
                return {"us_pct": us_pct, "countries": results, "total": total}
    except Exception as e:
        logger.warning(f"Audience country fetch failed: {e}")
    return None


# ─── Publish ──────────────────────────────────────────────────────────────────

def publish_photo(token: str, ig_user_id: str, image_url: str, caption: str = "") -> dict:
    """
    Publish a photo to Instagram.
    image_url must be a publicly accessible URL (HTTPS).
    Returns: {"id": "<post_id>"} on success, or {"error": ...}
    """
    # Step 1: Create media container
    r1 = httpx.post(
        f"{IG_API_BASE}/{ig_user_id}/media",
        params={
            "image_url": image_url,
            "caption": caption,
            "access_token": token,
        },
        timeout=30,
    )
    data1 = r1.json()
    if "error" in data1:
        return {"error": data1["error"].get("message", "Unknown error")}

    container_id = data1.get("id")
    if not container_id:
        return {"error": "Failed to create media container"}

    # Step 2: Publish the container
    r2 = httpx.post(
        f"{IG_API_BASE}/{ig_user_id}/media_publish",
        params={
            "creation_id": container_id,
            "access_token": token,
        },
        timeout=30,
    )
    data2 = r2.json()
    if "error" in data2:
        return {"error": data2["error"].get("message", "Publish failed")}

    return {"id": data2.get("id"), "container_id": container_id}


def publish_reel(token: str, ig_user_id: str, video_url: str, caption: str = "", cover_url: str = "", share_to_feed: bool = True) -> dict:
    """
    Publish a Reel to Instagram via Meta Graph API.
    video_url must be a publicly accessible MP4 URL (HTTPS).
    Returns status dict with id (post_id) and container_id, or error.
    """
    import time

    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true" if share_to_feed else "false",
        "access_token": token,
    }
    if cover_url:
        params["cover_url"] = cover_url

    logger.info(f"Vytváram IG Reel kontajner pre UID {ig_user_id} s videom: {video_url}")

    # Step 1: Create container
    try:
        r1 = httpx.post(
            f"{IG_API_BASE}/{ig_user_id}/media",
            params=params,
            timeout=60,
        )
        data1 = r1.json()
    except Exception as e:
        logger.exception(f"Chyba pri vytváraní IG kontajnera: {e}")
        return {"error": f"Chyba siete pri vytváraní IG kontajnera: {e}"}

    if "error" in data1:
        err_msg = data1["error"].get("message", "Container creation failed")
        logger.error(f"Zlyhanie vytvorenia kontajnera: {data1['error']}")
        return {"error": f"Container creation failed: {err_msg}"}

    container_id = data1.get("id")
    if not container_id:
        return {"error": "Failed to create reel container (no ID returned)"}

    logger.info(f"Kontajner {container_id} vytvorený, čakám na stiahnutie a transkódovanie videa na serveroch Meta...")

    # Step 2: Check upload status (reels need processing time)
    # Meta servery sťahujú video a transkódujú ho. Pre Reels je odporúčaný timeout 3-4 minúty.
    max_attempts = 45  # 45 pokusov * 5 sekúnd = 225 sekúnd (~3.75 min)
    is_finished = False
    last_status_code = "IN_PROGRESS"

    for attempt in range(1, max_attempts + 1):
        time.sleep(5)
        try:
            status_r = httpx.get(
                f"{IG_API_BASE}/{container_id}",
                params={"fields": "status_code,status", "access_token": token},
                timeout=20,
            )
            status_data = status_r.json()
        except Exception as se:
            logger.warning(f"Chyba pri dopytovaní stavu kontajnera {container_id} (pokus {attempt}): {se}")
            continue

        status_code = status_data.get("status_code", "")
        last_status_code = status_code or last_status_code

        if status_code == "FINISHED":
            is_finished = True
            logger.info(f"Kontajner {container_id} bol úspešne spracovaný po {attempt * 5}s (status: FINISHED)")
            break
        elif status_code == "ERROR":
            err_detail = status_data.get("status") or (status_data.get("error") or {}).get("message") or "Neznáma chyba spracovania"
            logger.error(f"Spracovanie videa na serveroch Meta zlyhalo pre kontajner {container_id}: {status_data}")
            return {"error": f"Video processing failed on Instagram: {err_detail}"}
        elif status_code == "EXPIRED":
            logger.error(f"Platnosť kontajnera {container_id} vypršala (EXPIRED)")
            return {"error": "Platnosť video kontajnera na Instagrame vypršala (EXPIRED)"}
        else:
            if attempt % 4 == 0 or attempt == 1:
                logger.info(f"Čakám na spracovanie videa {container_id} ({attempt}/{max_attempts})... Stav: {status_code or 'IN_PROGRESS'}")

    if not is_finished:
        logger.error(f"Kontajner {container_id} nestihol dokončiť spracovanie v limite 225s. Posledný stav: {last_status_code}")
        # KRITICKÉ: Ak video nie je FINISHED, NESMIEME volať media_publish! Inak Meta vyhodí 'Media ID is not available'.
        return {
            "error": f"Instagram nestihol dokončiť spracovanie videa (posledný stav: {last_status_code}, čakalo sa 3.5 min). Kontajner bol vytvorený (ID: {container_id}), publikovanie bolo pozastavené."
        }

    # Step 3: Publish (s replication lag ochranou)
    # Krátka pauza 3s, aby sa stav FINISHED zreplikoval naprieč Meta edge clustermi
    time.sleep(3)

    for pub_attempt in range(1, 4):
        try:
            r2 = httpx.post(
                f"{IG_API_BASE}/{ig_user_id}/media_publish",
                params={"creation_id": container_id, "access_token": token},
                timeout=45,
            )
            publish_data = r2.json()
        except Exception as pe:
            logger.exception(f"Chyba pri volaní media_publish pre kontajner {container_id} (pokus {pub_attempt}): {pe}")
            if pub_attempt < 3:
                time.sleep(5)
                continue
            return {"error": f"Chyba spojenia pri media_publish: {pe}"}

        if "error" in publish_data:
            err_msg = publish_data["error"].get("message", "Publish failed")
            err_code = publish_data["error"].get("code")
            err_subcode = publish_data["error"].get("error_subcode")
            logger.warning(f"Chyba media_publish pre kontajner {container_id} (pokus {pub_attempt}/3): {err_msg} (code={err_code}, subcode={err_subcode})")
            
            # Ak Meta hlási že Media ID ešte nie je dostupné (edge replication lag), počkáme 6s a zopakujeme
            if ("Media ID is not available" in err_msg or err_code == 9007 or err_subcode == 2207027) and pub_attempt < 3:
                logger.info(f"Čakám 6s na replikáciu Meta Media ID pre kontajner {container_id}...")
                time.sleep(6)
                continue
            return {"error": f"{err_msg}"}
        else:
            published_id = publish_data.get("id")
            logger.info(f"Reel úspešne publikovaný! ID média: {published_id}")
            return {"id": published_id, "container_id": container_id}

    return {"error": "Publikovanie zlyhalo po 3 pokusoch"}


def check_container_status(token: str, container_id: str) -> dict:
    """Check the processing status of a media container."""
    r = httpx.get(
        f"{IG_API_BASE}/{container_id}",
        params={"fields": "status_code,status", "access_token": token},
        timeout=10,
    )
    return r.json()
