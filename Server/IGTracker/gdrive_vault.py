"""
IG Tracker & Publisher — Google Drive Storage Engine for Media Vault
Zero-disk-space architecture for VPS with limited storage.
Master videos are stored directly in Google Drive folder 'IG_VAULT'.
"""
import os
import io
import time
import uuid
import tempfile
import logging
from contextlib import contextmanager
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import db

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
VAULT_DIR = os.path.join(DATA_DIR, "vault")
THUMBS_DIR = os.path.join(VAULT_DIR, "thumbs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(VAULT_DIR, exist_ok=True)
os.makedirs(THUMBS_DIR, exist_ok=True)

# Cesty k tokenu podľa priority
POSSIBLE_TOKEN_PATHS = [
    os.path.join(DATA_DIR, "drive_token.json"),
    os.path.abspath(os.path.join(BASE_DIR, "..", "Drive", "data", "drive_token.json")),
    os.path.abspath(os.path.join(BASE_DIR, "..", "CaPPyTools", "data", "drive_token.json")),
    "/home/patrik/server/Drive/data/drive_token.json",
    "/home/patrik/server/CaPPyTools/data/drive_token.json",
]

DEFAULT_VAULT_FOLDER_ID = "1NyPnFW4O8NYd_BEzMf5c43XWQlr8zsSJ"
VAULT_FOLDER_NAME = "IG_VAULT"


def format_bytes(size_bytes):
    """Sformátuje počet bajtov na pekný reťazec (napr. 14.5 MB, 5.0 TB)."""
    if not size_bytes:
        return "0 B"
    try:
        size = float(size_bytes)
    except (ValueError, TypeError):
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024.0 or unit == 'TB':
            return f"{size:.1f} {unit}" if unit != 'B' else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} GB"


def get_token_file():
    """Nájde prvý existujúci súbor s tokenom."""
    for p in POSSIBLE_TOKEN_PATHS:
        if os.path.exists(p):
            return p
    return POSSIBLE_TOKEN_PATHS[0]


def is_connected():
    """Overí, či existuje platný token pre Google Drive."""
    return os.path.exists(get_token_file())


def get_drive_credentials():
    """
    Načíta a vráti platné Credentials pre Google Drive.
    Automaticky obnoví expirovaný access token bez obmedzovania na hardcoded scopes.
    """
    token_path = get_token_file()
    if not os.path.exists(token_path):
        logger.warning(f"Google Drive token sa nenašiel na žiadnej z ciest: {POSSIBLE_TOKEN_PATHS}")
        return None

    try:
        # Použijeme scopes uložené priamo v súbore tokenu (nevnucujeme iné scopes)
        creds = Credentials.from_authorized_user_file(token_path)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Uložíme obnovený token späť do nájdeného súboru aj lokálne
            try:
                with open(token_path, "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            except Exception:
                pass
            local_token = os.path.join(DATA_DIR, "drive_token.json")
            if local_token != token_path:
                try:
                    with open(local_token, "w", encoding="utf-8") as f:
                        f.write(creds.to_json())
                except Exception:
                    pass

        if not creds.valid:
            logger.error("Google Drive prihlasovacie údaje nie sú platné.")
            return None

        return creds
    except Exception as e:
        logger.error(f"Chyba pri inicializácii Google Drive Credentials: {e}")
        return None


def get_drive_service():
    """Inicializuje a vráti autentifikovanú službu Google Drive v3."""
    creds = get_drive_credentials()
    if not creds:
        return None
    try:
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        logger.error(f"Chyba pri inicializácii Google Drive API: {e}")
        return None


def get_vault_folder_id(svc=None):
    """
    Vráti (folder_id, web_view_link) pre dedikovaný priečinok IG_VAULT.
    Ak priečinok neexistuje, automaticky ho vytvorí.
    """
    if svc is None:
        svc = get_drive_service()
        if not svc:
            return None, None

    # 1. Skúsime predvolené overené ID
    if DEFAULT_VAULT_FOLDER_ID:
        try:
            folder = svc.files().get(
                fileId=DEFAULT_VAULT_FOLDER_ID,
                fields="id, name, webViewLink, trashed"
            ).execute()
            if not folder.get("trashed"):
                return folder["id"], folder.get("webViewLink")
        except Exception:
            pass

    # 2. Hľadáme priečinok podľa názvu
    try:
        res = svc.files().list(
            q=f"name='{VAULT_FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name, webViewLink)",
            pageSize=5
        ).execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"], files[0].get("webViewLink")

        # 3. Ak neexistuje, vytvoríme nový
        meta = {
            "name": VAULT_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder"
        }
        folder = svc.files().create(body=meta, fields="id, webViewLink").execute()
        logger.info(f"Vytvorený nový priečinok {VAULT_FOLDER_NAME} s ID: {folder['id']}")
        return folder["id"], folder.get("webViewLink")
    except Exception as e:
        logger.error(f"Chyba pri získavaní priečinka IG_VAULT: {e}")
        return None, None


def get_storage_status():
    """
    Vráti detailné informácie o pripojenom Google Drive účte a kvóte.
    """
    svc = get_drive_service()
    if not svc:
        return {
            "connected": False,
            "message": "Google Drive nie je pripojený (chýba platný drive_token.json)."
        }

    try:
        about = svc.about().get(fields="user, storageQuota").execute()
        user = about.get("user", {})
        quota = about.get("storageQuota", {})

        limit_bytes = int(quota.get("limit", 0))
        usage_bytes = int(quota.get("usage", 0))
        folder_id, folder_link = get_vault_folder_id(svc)

        return {
            "connected": True,
            "user_email": user.get("emailAddress", "Neznámy"),
            "display_name": user.get("displayName", ""),
            "storage_used": usage_bytes,
            "storage_used_fmt": format_bytes(usage_bytes),
            "storage_total": limit_bytes,
            "storage_total_fmt": format_bytes(limit_bytes),
            "storage_percent": round((usage_bytes / limit_bytes * 100), 2) if limit_bytes > 0 else 0,
            "folder_id": folder_id,
            "folder_link": folder_link or f"https://drive.google.com/drive/folders/{folder_id}"
        }
    except Exception as e:
        logger.error(f"Chyba pri čítaní storage statusu z Google Drive: {e}")
        return {
            "connected": False,
            "error": str(e)
        }


def get_or_create_profile_folder(username, svc=None):
    """
    Nájde alebo vytvorí priečinok pre profil vo vnútri IG_VAULT (napr. '@clarigarzi').
    Vracia folder_id.
    """
    if svc is None:
        svc = get_drive_service()
    if not svc:
        return None
    parent_id, _ = get_vault_folder_id(svc)
    if not parent_id:
        return None

    clean_name = f"@{username.lstrip('@')}"
    try:
        q = f"mimeType='application/vnd.google-apps.folder' and trashed=false and name='{clean_name}' and '{parent_id}' in parents"
        res = svc.files().list(q=q, fields="files(id, name)").execute()
        files = res.get("files", [])
        if files:
            return files[0]["id"]

        meta = {
            "name": clean_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id]
        }
        folder = svc.files().create(body=meta, fields="id").execute()
        folder_id = folder.get("id")
        try:
            svc.permissions().create(
                fileId=folder_id,
                body={"type": "user", "role": "writer", "emailAddress": "garcarzp@gmail.com"},
                supportsAllDrives=True,
                sendNotificationEmail=False
            ).execute()
        except Exception:
            pass
        return folder_id
    except Exception as e:
        logger.error(f"Chyba pri hľadaní/vytváraní priečinka {clean_name} na Google Drive: {e}")
        return parent_id


def upload_file_to_drive(local_path, filename, mime_type="video/mp4", delete_local=True, folder_id=None):
    """
    Nahrá lokálny video súbor do priečinka IG_VAULT (alebo špecifického profilového priečinka) na Google Drive.
    Ak delete_local=True, po úspešnom nahratí IHNEĎ zmaže lokálny súbor z disku,
    aby na VPS neostalo žiadne zabraté miesto!
    """
    svc = get_drive_service()
    if not svc:
        raise RuntimeError("Google Drive služba nie je dostupná.")

    target_folder_id = folder_id
    if not target_folder_id:
        target_folder_id, _ = get_vault_folder_id(svc)
    if not target_folder_id:
        raise RuntimeError("Priečinok IG_VAULT na Google Drive nebol nájdený.")

    file_metadata = {
        "name": filename,
        "parents": [target_folder_id]
    }

    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
    request = svc.files().create(
        body=file_metadata,
        media_body=media,
        fields="id, name, size, webViewLink, webContentLink, videoMediaMetadata"
    )

    response = None
    while response is None:
        status, response = request.next_chunk()

    # Okamžité uvoľnenie disku VPS!
    if delete_local and os.path.exists(local_path):
        try:
            os.remove(local_path)
            logger.info(f"Master video úspešne uložené na Google Drive ({response.get('id')}). Lokálny temp zmazaný: {local_path}")
        except Exception as e:
            logger.warning(f"Chyba pri mazaní lokálneho temp súboru {local_path}: {e}")

    return response


def download_file_from_drive(file_id, dest_path):
    """
    Stiahne video z Google Drive do zadaného lokálneho cieľa (napr. v /tmp).
    """
    svc = get_drive_service()
    if not svc:
        raise RuntimeError("Google Drive služba nie je dostupná.")

    request = svc.files().get_media(fileId=file_id)
    with io.FileIO(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024 * 5)
        done = False
        while not done:
            status, done = downloader.next_chunk()

    return dest_path


@contextmanager
def temporary_master(file_id, ext=".mp4"):
    """
    Stiahne master video z Google Drive do dočasného súboru (/tmp) LEN na dobu
    potrebnú na vytvorenie spoofnutej kópie.
    Po ukončení bloku (alebo v prípade výnimky) sa dočasný súbor VŽDY vymaže!
    """
    temp_dir = tempfile.gettempdir()
    temp_filename = f"gdrive_master_{file_id[:10]}_{uuid.uuid4().hex[:6]}{ext}"
    temp_path = os.path.join(temp_dir, temp_filename)
    try:
        download_file_from_drive(file_id, temp_path)
        yield temp_path
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.info(f"Dočasný master zmazaný z disku VPS: {temp_path}")
            except Exception as e:
                logger.warning(f"Chyba pri odstraňovaní dočasného master súboru {temp_path}: {e}")


def delete_file_from_drive(file_id):
    """
    Odstráni súbor z Google Drive.
    """
    svc = get_drive_service()
    if not svc:
        return False
    try:
        svc.files().delete(fileId=file_id).execute()
        return True
    except Exception as e:
        logger.error(f"Chyba pri mazaní súboru {file_id} z Google Drive: {e}")
        return False


def list_drive_vault_files():
    """
    Vráti zoznam všetkých video a foto súborov nachádzajúcich sa v priečinku IG_VAULT na Google Drive,
    vrátane všetkých podzložiek (napr. kopie 1, kopie 2, kopie 3...).
    Ku každému súboru priradí 'folder_name' zodpovedajúci názvu podzložky (alebo '' pre koreň).
    """
    svc = get_drive_service()
    if not svc:
        return []

    root_id, _ = get_vault_folder_id(svc)
    if not root_id:
        return []

    all_media_files = []

    def _fetch_files_in_folder(folder_id, folder_name=""):
        page_token = None
        while True:
            try:
                res = svc.files().list(
                    q=f"'{folder_id}' in parents and trashed=false",
                    fields="nextPageToken, files(id, name, size, mimeType, createdTime, webViewLink, webContentLink, videoMediaMetadata)",
                    pageSize=100,
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
            except Exception as e:
                logger.error(f"Chyba pri nacitavani suborov z {folder_name or root_id}: {e}")
                break

            for f in res.get("files", []):
                mime = f.get("mimeType", "")
                name = f.get("name", "")
                if mime == "application/vnd.google-apps.folder":
                    continue
                if (mime.startswith("video/") or mime.startswith("image/") or
                    name.lower().endswith((".mp4", ".mov", ".m4v", ".webm", ".jpg", ".jpeg", ".png", ".webp"))):
                    f["folder_name"] = folder_name
                    all_media_files.append(f)

            page_token = res.get("nextPageToken")
            if not page_token:
                break

    try:
        # 1. Hľadáme všetky podzložky v IG_VAULT (napr. kopie 1, kopie 2...)
        subfolders_res = svc.files().list(
            q=f"'{root_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=100
        ).execute()
        subfolders = subfolders_res.get("files", [])

        # 2. Načítame médiá z každej podzložky
        for sf in subfolders:
            _fetch_files_in_folder(sf["id"], folder_name=sf["name"])

        # 3. Načítame médiá priamo z koreňa IG_VAULT (ak tam nejaké sú)
        _fetch_files_in_folder(root_id, folder_name="")

        return all_media_files
    except Exception as e:
        logger.error(f"Chyba pri prehľadávaní priečinka IG_VAULT: {e}")
        return []


def sync_drive_vault_to_db(quick=True):
    """
    Synchronizuje videá a fotky z priečinka IG_VAULT na Google Drive do databázy vault_videos.
    Podporuje podzložky (kopie 1, kopie 2...) a automaticky čistí zmazané/odstránené súbory.
    """
    import spoofer

    drive_files = list_drive_vault_files()
    active_drive_ids = {df["id"]: df for df in drive_files}

    existing_videos = db.get_all_vault_videos()
    existing_by_gdrive_id = {v.get("gdrive_file_id"): v for v in existing_videos if v.get("gdrive_file_id")}

    # 1. Odstránime z DB záznamy, ktoré boli na Google Drive odstránené / presunuté do koša
    removed_count = 0
    for v in existing_videos:
        gid = v.get("gdrive_file_id")
        if v.get("storage_type") == "gdrive" and gid and gid not in active_drive_ids:
            if v.get("status") in ("available", "scheduled"):
                db.delete_vault_video(v["id"])
                removed_count += 1

    # 2. Aktualizujeme folder_name pre existujúce videá
    for gid, df in active_drive_ids.items():
        if gid in existing_by_gdrive_id:
            existing = existing_by_gdrive_id[gid]
            folder_name = df.get("folder_name", "")
            if existing.get("folder_name") != folder_name:
                db.update_vault_video_folder(existing["id"], folder_name)

    # 3. Pridáme nové médiá
    new_count = 0
    temp_thumb_dir = os.path.join(DATA_DIR, "vault", "thumbs")
    os.makedirs(temp_thumb_dir, exist_ok=True)

    for df in drive_files:
        file_id = df["id"]
        if file_id in existing_by_gdrive_id:
            continue

        orig_name = df.get("name", f"media_{file_id}")
        folder_name = df.get("folder_name", "")
        mime = df.get("mimeType", "")
        ext = os.path.splitext(orig_name)[1].lower()
        is_photo = mime.startswith("image/") or (ext in spoofer.IMAGE_EXT)
        media_type = "photo" if is_photo else "video"

        file_size = int(df.get("size", 0))
        web_link = df.get("webViewLink", "")
        v_meta = df.get("videoMediaMetadata", {})

        duration = float(v_meta.get("durationMillis", 0)) / 1000.0 if v_meta.get("durationMillis") else 0.0
        width = int(v_meta.get("width", 0))
        height = int(v_meta.get("height", 0))

        thumb_filename = f"thumb_gdrive_{file_id[:10]}.jpg"
        thumb_path = os.path.join(temp_thumb_dir, thumb_filename)

        if not quick and (not os.path.exists(thumb_path) or (not is_photo and duration == 0.0)):
            try:
                with temporary_master(file_id, ext=ext if ext else (".jpg" if is_photo else ".mp4")) as temp_media:
                    info = spoofer.probe_video_info(temp_media)
                    if not is_photo and duration == 0.0:
                        duration = info.get("duration_seconds", 0.0)
                    if width == 0:
                        width = info.get("width", 0)
                    if height == 0:
                        height = info.get("height", 0)
                    if file_size == 0:
                        file_size = info.get("file_size", os.path.getsize(temp_media))

                    if not os.path.exists(thumb_path):
                        spoofer.generate_thumbnail(temp_media, thumb_path)
            except Exception as e:
                logger.warning(f"Generovanie náhľadu pre Google Drive médium {orig_name} zlyhalo: {e}")

        db.add_vault_video(
            filename=f"gdrive_{file_id}",
            original_name=orig_name,
            file_size=file_size,
            duration_seconds=duration,
            width=width,
            height=height,
            thumbnail_path=thumb_filename if os.path.exists(thumb_path) else None,
            storage_type="gdrive",
            gdrive_file_id=file_id,
            gdrive_web_view_link=web_link,
            media_type=media_type,
            tag='Voľné',
            folder_name=folder_name
        )
        new_count += 1

    return {
        "status": "ok",
        "synced": new_count,
        "removed": removed_count,
        "total_in_drive": len(drive_files),
        "message": f"Synchronizácia dokončená. Pridaných {new_count} nových, odstránených {removed_count} neplatných médií."
    }


def get_vault_folders_summary(account_id=None):
    """
    Vráti prehľad zložiek (kopie 1, kopie 2...) s počtom celkových a voľných videí.
    """
    all_videos = db.get_all_vault_videos()
    gdrive_videos = [v for v in all_videos if v.get("storage_type") == "gdrive"]

    target_user = ""
    if account_id:
        acc = db.get_account_by_id(account_id)
        if acc:
            target_user = acc.get("username", "")

    folders_map = {}
    for v in gdrive_videos:
        folder = v.get("folder_name") or "(Koreň Drive)"
        if folder not in folders_map:
            folders_map[folder] = {
                "name": folder,
                "total_count": 0,
                "unused_count": 0,
                "sample_videos": []
            }
        folders_map[folder]["total_count"] += 1

        used_accounts = [u.strip().lstrip("@").lower() for u in (v.get("used_by_accounts") or "").split(",") if u.strip()]
        is_used = False
        if target_user and target_user.lstrip("@").lower() in used_accounts:
            is_used = True
        elif not target_user and v.get("status") in ("used", "scheduled"):
            is_used = True

        if not is_used:
            folders_map[folder]["unused_count"] += 1

        if len(folders_map[folder]["sample_videos"]) < 3:
            folders_map[folder]["sample_videos"].append({
                "id": v["id"],
                "name": v["original_name"],
                "size_fmt": format_bytes(v.get("file_size", 0))
            })

    sorted_folders = sorted(folders_map.values(), key=lambda f: f["name"])
    return sorted_folders
