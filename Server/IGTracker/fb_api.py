"""
FB Publisher — Meta Facebook Graph API v21.0 wrapper
Podporuje:
- Načítanie detailov FB Stránky
- Publikovanie Facebook Reels (oficiálny video_reels upload protokol)
- Štandardný fallback na Facebook Page Videos
"""
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

FB_API_BASE = "https://graph.facebook.com/v21.0"


def get_page_info(page_access_token: str, page_id: str = "me") -> dict:
    """Načíta základné informácie o Facebook Stránke."""
    try:
        r = httpx.get(
            f"{FB_API_BASE}/{page_id}",
            params={
                "fields": "id,name,fan_count,followers_count,picture,link",
                "access_token": page_access_token,
            },
            timeout=10,
        )
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def get_connected_pages(user_access_token: str) -> list:
    """Vráti zoznam všetkých Facebook Stránok, ktoré používateľ spravuje."""
    try:
        r = httpx.get(
            f"{FB_API_BASE}/me/accounts",
            params={
                "fields": "id,name,access_token,category,tasks",
                "access_token": user_access_token,
            },
            timeout=12,
        )
        data = r.json()
        if "data" in data:
            return data["data"]
        return []
    except Exception as e:
        logger.warning(f"Chyba pri načítaní FB stránok cez /me/accounts: {e}")
        return []


def publish_facebook_reel(page_access_token: str, page_id: str, video_url: str, description: str = "") -> dict:
    """
    Publikuje Facebook Reel na Facebook Page cez Meta Graph API.
    Využíva trojfázový video_reels protokol:
    1. upload_phase=start -> získa video_id a upload_url
    2. POST na upload_url s file_url
    3. upload_phase=finish s video_state=PUBLISHED & description
    """
    try:
        logger.info(f"Facebook Reels: Inicializujem upload pre Page ID {page_id}...")
        # Fáza 1: Štart uploadu
        r_start = httpx.post(
            f"{FB_API_BASE}/{page_id}/video_reels",
            params={
                "upload_phase": "start",
                "access_token": page_access_token,
            },
            timeout=25,
        )
        start_data = r_start.json()
        if "error" in start_data:
            err_msg = start_data["error"].get("message", "Facebook Reel upload start failed")
            logger.error(f"Facebook Reel start error: {err_msg}")
            # Fallback na štandardný /videos endpoint
            return _publish_fallback_video(page_access_token, page_id, video_url, description)

        video_id = start_data.get("video_id")
        upload_url = start_data.get("upload_url")
        if not video_id or not upload_url:
            return _publish_fallback_video(page_access_token, page_id, video_url, description)

        # Fáza 2: Prenos videa
        logger.info(f"Facebook Reels: Prenášam video na upload_url pre video_id={video_id}...")
        headers = {
            "Authorization": f"OAuth {page_access_token}",
            "file_url": video_url,
        }
        r_upload = httpx.post(
            upload_url,
            headers=headers,
            timeout=60,
        )
        upload_res = r_upload.json() if r_upload.content else {}
        if "error" in upload_res:
            err_msg = upload_res["error"].get("message", "Facebook Reel video transfer failed")
            logger.error(f"Facebook Reel transfer error: {err_msg}")
            return _publish_fallback_video(page_access_token, page_id, video_url, description)

        # Fáza 3: Dokončenie publikovania
        logger.info(f"Facebook Reels: Dokončujem publikovanie pre video_id={video_id}...")
        r_finish = httpx.post(
            f"{FB_API_BASE}/{page_id}/video_reels",
            params={
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": description,
                "access_token": page_access_token,
            },
            timeout=30,
        )
        finish_data = r_finish.json()
        if "error" in finish_data:
            err_msg = finish_data["error"].get("message", "Facebook Reel finish failed")
            logger.error(f"Facebook Reel finish error: {err_msg}")
            return {"error": err_msg}

        logger.info(f"Facebook Reel úspešne publikovaný! ID: {video_id}")
        return {
            "success": True,
            "id": str(video_id),
            "status": "published"
        }

    except Exception as e:
        logger.exception(f"Výnimka pri Facebook Reels upload: {e}")
        return _publish_fallback_video(page_access_token, page_id, video_url, description)


def _publish_fallback_video(page_access_token: str, page_id: str, video_url: str, description: str = "") -> dict:
    """Fallback publikovanie cez štandardný /{page_id}/videos endpoint."""
    try:
        logger.info(f"Facebook Fallback: Skúšam publikovanie cez /{page_id}/videos...")
        r = httpx.post(
            f"{FB_API_BASE}/{page_id}/videos",
            params={
                "file_url": video_url,
                "description": description,
                "access_token": page_access_token,
            },
            timeout=45,
        )
        data = r.json()
        if "id" in data:
            logger.info(f"Facebook Fallback úspešný! Video ID: {data['id']}")
            return {"success": True, "id": str(data["id"]), "status": "published_fallback"}
        if "error" in data:
            return {"error": data["error"].get("message", "Fallback publish failed")}
        return {"error": "Neznáma odpoveď z Facebook Graph API"}
    except Exception as e:
        return {"error": f"Fallback výnimka: {str(e)}"}
