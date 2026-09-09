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
    Publish a Reel to Instagram.
    video_url must be a publicly accessible MP4 URL (HTTPS).
    Returns status dict with upload_id or error.
    """
    params = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true" if share_to_feed else "false",
        "access_token": token,
    }
    if cover_url:
        params["cover_url"] = cover_url

    # Step 1: Create container
    r1 = httpx.post(
        f"{IG_API_BASE}/{ig_user_id}/media",
        params=params,
        timeout=60,
    )
    data1 = r1.json()
    if "error" in data1:
        return {"error": data1["error"].get("message", "Container creation failed")}

    container_id = data1.get("id")
    if not container_id:
        return {"error": "Failed to create reel container"}

    # Step 2: Check upload status (reels need processing time)
    import time
    for _ in range(10):
        time.sleep(5)
        status_r = httpx.get(
            f"{IG_API_BASE}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=15,
        )
        status_data = status_r.json()
        status_code = status_data.get("status_code", "")
        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            return {"error": f"Video processing failed: {status_data.get('status')}"}

    # Step 3: Publish
    r2 = httpx.post(
        f"{IG_API_BASE}/{ig_user_id}/media_publish",
        params={"creation_id": container_id, "access_token": token},
        timeout=30,
    )
    data2 = r2.json()
    if "error" in data2:
        return {"error": data2["error"].get("message", "Publish failed")}

    return {"id": data2.get("id"), "container_id": container_id}


def check_container_status(token: str, container_id: str) -> dict:
    """Check the processing status of a media container."""
    r = httpx.get(
        f"{IG_API_BASE}/{container_id}",
        params={"fields": "status_code,status", "access_token": token},
        timeout=10,
    )
    return r.json()
