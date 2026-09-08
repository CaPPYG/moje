#!/usr/bin/env python3
"""
Drive Drop – Google Drive integrácia pre priečinok UPLOADED.
Spravuje nahrávanie, výpis, sťahovanie a mazanie súborov.
Podporuje aj bezproblémový lokálny fallback (ak Drive nie je pripojený).
"""
import os
import json
import datetime
import mimetypes
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

CRED_FILE = os.path.join(DATA_DIR, "credentials.json")
TOKEN_FILE = os.path.join(DATA_DIR, "drive_token.json")

# Zdieľaný token z CaPPyTools ak existuje
SHARED_TOKEN_FILE = os.path.abspath(os.path.join(BASE_DIR, "..", "CaPPyTools", "data", "drive_token.json"))

LOCAL_UPLOADED_DIR = os.path.join(DATA_DIR, "UPLOADED")
os.makedirs(LOCAL_UPLOADED_DIR, exist_ok=True)


def has_credentials():
    return os.path.exists(CRED_FILE)


def get_token_path():
    """Vráti cestu k existujúcemu tokenu (lokálny alebo zdieľaný z CaPPyTools)."""
    if os.path.exists(TOKEN_FILE):
        return TOKEN_FILE
    if os.path.exists(SHARED_TOKEN_FILE):
        return SHARED_TOKEN_FILE
    return TOKEN_FILE


def is_connected():
    return os.path.exists(get_token_path())


def get_service():
    """Vráti inicializovanú Google Drive service alebo None ak chýba token."""
    token_path = get_token_path()
    if not os.path.exists(token_path):
        return None
    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            # Vždy uložíme obnovený token lokálne
            with open(TOKEN_FILE, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        if not creds.valid:
            return None
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"Chyba pri inicializácii Google Drive service: {e}")
        return None


def get_redirect_uri():
    """Registrovaný redirect URI z credentials.json."""
    try:
        with open(CRED_FILE, "r", encoding="utf-8") as f:
            uris = json.load(f).get("web", {}).get("redirect_uris", [])
        if uris:
            return uris[0]
    except Exception:
        pass
    return "http://localhost:5050/drive/callback"


def format_size(size_bytes):
    """Sformátuje počet bajtov na pekný reťazec (napr. 14.5 MB)."""
    if size_bytes is None:
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


def _find_folder(svc, name, parent_id=None):
    q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
         f"and trashed=false")
    if parent_id:
        q += f" and '{parent_id}' in parents"
    try:
        r = svc.files().list(q=q, pageSize=10, fields="files(id,name)").execute()
        files = r.get("files", [])
        return files[0]["id"] if files else None
    except Exception as e:
        print(f"Chyba pri hľadaní priečinka '{name}': {e}")
        return None


def _create_folder(svc, name, parent_id=None):
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    try:
        f = svc.files().create(body=body, fields="id").execute()
        return f["id"]
    except Exception as e:
        print(f"Chyba pri vytváraní priečinka '{name}': {e}")
        return None


def ensure_uploaded_folder(folder_name="UPLOADED"):
    """Nájde alebo vytvorí priečinok UPLOADED v koreni Google Drive."""
    svc = get_service()
    if not svc:
        return None
    fid = _find_folder(svc, folder_name, None)
    if not fid:
        fid = _create_folder(svc, folder_name, None)
    return fid


def list_files(folder_name="UPLOADED"):
    """Vráti zoznam súborov v priečinku UPLOADED (Google Drive + lokálny fallback)."""
    items = []
    seen_names = set()
    svc = get_service()

    # 1. Google Drive súbory
    if svc:
        try:
            fid = ensure_uploaded_folder(folder_name)
            if fid:
                q = f"'{fid}' in parents and trashed=false"
                r = svc.files().list(
                    q=q,
                    fields="files(id, name, size, mimeType, modifiedTime, createdTime, webViewLink, webContentLink, iconLink, thumbnailLink)",
                    orderBy="modifiedTime desc",
                    pageSize=100
                ).execute()
                for f in r.get("files", []):
                    fid_val = f.get("id")
                    name = f.get("name", "nepomenovany")
                    sz = int(f.get("size", 0)) if f.get("size") else 0
                    direct_url = (f.get("webContentLink") or
                                  f"https://drive.usercontent.google.com/download?id={fid_val}&export=download&confirm=t")
                    items.append({
                        "id": fid_val,
                        "name": name,
                        "size": sz,
                        "size_str": format_size(sz),
                        "mimeType": f.get("mimeType", "application/octet-stream"),
                        "modifiedTime": f.get("modifiedTime") or f.get("createdTime") or "",
                        "downloadUrl": direct_url,
                        "serverDownloadUrl": f"/download/{fid_val}",
                        "webViewLink": f.get("webViewLink", ""),
                        "iconLink": f.get("iconLink", ""),
                        "thumbnailLink": f.get("thumbnailLink", ""),
                        "is_local": False
                    })
                    seen_names.add(name)
        except Exception as e:
            print(f"Chyba pri načítaní súborov z Drive: {e}")

    # 2. Lokálny fallback priečinok
    if os.path.isdir(LOCAL_UPLOADED_DIR):
        for fname in os.listdir(LOCAL_UPLOADED_DIR):
            p = os.path.join(LOCAL_UPLOADED_DIR, fname)
            if os.path.isfile(p):
                sz = os.path.getsize(p)
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(p)).isoformat()
                mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"
                items.append({
                    "id": f"local_{fname}",
                    "name": fname,
                    "size": sz,
                    "size_str": format_size(sz),
                    "mimeType": mime,
                    "modifiedTime": mtime,
                    "downloadUrl": f"/download/local_{fname}",
                    "serverDownloadUrl": f"/download/local_{fname}",
                    "webViewLink": "",
                    "iconLink": "",
                    "thumbnailLink": "",
                    "is_local": True
                })

    return items


def upload_file(local_path, filename=None, folder_name="UPLOADED", log=None):
    """Nahrá súbor do priečinka UPLOADED na Google Drive (alebo lokálny fallback)."""
    name = filename or os.path.basename(local_path)
    svc = get_service()

    if not svc:
        if log:
            log("ℹ Google Drive nie je pripojený, ukladám lokálne na server.")
        dst = os.path.join(LOCAL_UPLOADED_DIR, name)
        import shutil
        shutil.copy2(local_path, dst)
        sz = os.path.getsize(dst)
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return {
            "id": f"local_{name}",
            "name": name,
            "size": sz,
            "size_str": format_size(sz),
            "downloadUrl": f"/download/local_{name}",
            "serverDownloadUrl": f"/download/local_{name}",
            "is_local": True
        }

    try:
        fid = ensure_uploaded_folder(folder_name)
        if not fid:
            raise RuntimeError(f"Nepodarilo sa nájsť alebo vytvoriť priečinok '{folder_name}'.")

        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        media = MediaFileUpload(local_path, mimetype=mime, resumable=True)
        body = {"name": name, "parents": [fid]}
        f = svc.files().create(body=body, media_body=media, fields="id,name,size,webContentLink,webViewLink").execute()
        file_id = f["id"]

        # Verejné práva na čítanie pre priame stiahnutie odkiaľkoľvek
        try:
            svc.permissions().create(fileId=file_id, body={"type": "anyone", "role": "reader"}).execute()
        except Exception:
            pass

        direct_url = (f.get("webContentLink") or
                      f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t")
        sz = int(f.get("size", os.path.getsize(local_path)))

        return {
            "id": file_id,
            "name": name,
            "size": sz,
            "size_str": format_size(sz),
            "downloadUrl": direct_url,
            "serverDownloadUrl": f"/download/{file_id}",
            "webViewLink": f.get("webViewLink", ""),
            "is_local": False
        }
    except Exception as e:
        if log:
            log(f"⚠ Drive upload zlyhal: {e}, ukladám do lokálneho fallbacku.")
        dst = os.path.join(LOCAL_UPLOADED_DIR, name)
        import shutil
        shutil.copy2(local_path, dst)
        sz = os.path.getsize(dst)
        return {
            "id": f"local_{name}",
            "name": name,
            "size": sz,
            "size_str": format_size(sz),
            "downloadUrl": f"/download/local_{name}",
            "serverDownloadUrl": f"/download/local_{name}",
            "is_local": True
        }


def delete_file(file_id, folder_name="UPLOADED"):
    """Zmaže súbor z Google Drive alebo z lokálneho fallbacku."""
    if str(file_id).startswith("local_"):
        fname = str(file_id)[6:]
        p = os.path.join(LOCAL_UPLOADED_DIR, fname)
        if os.path.isfile(p):
            import gc
            gc.collect()
            try:
                os.remove(p)
                return True, "Lokálny súbor zmazaný."
            except Exception as e:
                return False, str(e)
        return False, "Súbor neexistuje."

    svc = get_service()
    if not svc:
        return False, "Google Drive nie je pripojený."
    try:
        svc.files().delete(fileId=file_id).execute()
        return True, "Súbor úspešne zmazaný z Google Drive."
    except Exception as e:
        return False, str(e)


def download_stream(file_id):
    """Vráti (stream_alebo_path, filename, mimeType, is_local)."""
    if str(file_id).startswith("local_"):
        fname = str(file_id)[6:]
        p = os.path.join(LOCAL_UPLOADED_DIR, fname)
        if os.path.isfile(p):
            mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"
            return p, fname, mime, True
        return None, None, None, True

    svc = get_service()
    if not svc:
        return None, None, None, False
    try:
        meta = svc.files().get(fileId=file_id, fields="name,mimeType,size").execute()
        fname = meta.get("name", f"file_{file_id}")
        mime = meta.get("mimeType", "application/octet-stream")

        import io
        request = svc.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return fh, fname, mime, False
    except Exception as e:
        print(f"Chyba pri sťahovaní streamu: {e}")
        return None, None, None, False
