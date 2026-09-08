#!/usr/bin/env python3
"""
Studio – Google Drive integrácia.
Po prihlásení užívateľa sa na Drive vlastníka vytvorí Studio/<hash>/ so
subpriečinkami Vault / Output / Planner (anonymné – email sa tam neukladá).

Setup (stačí raz):
  1. Google Cloud Console -> projekt -> zapni "Google Drive API"
  2. "OAuth consent screen" -> External -> pridaj test usera (vlastný gmail)
  3. Credentials -> OAuth client ID -> "Desktop app" -> stiahni JSON
     a ulož ako  data/credentials.json
  4. V appke: Admin -> Google Drive -> "Pripojiť Google Drive"
"""
import os, json, hashlib
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/drive.file"]
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CRED_FILE = os.path.join(DATA_DIR, "credentials.json")
TOKEN_FILE = os.path.join(DATA_DIR, "drive_token.json")
MAPPING_FILE = os.path.join(DATA_DIR, "drive_folders.json")

def has_credentials():
    return os.path.exists(CRED_FILE)

def is_connected():
    return os.path.exists(TOKEN_FILE)

def get_service():
    """Vráti Drive service alebo None ak nie je token."""
    if not os.path.exists(TOKEN_FILE):
        return None
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    if not creds.valid:
        return None
    return build("drive", "v3", credentials=creds)

def _find_folder(svc, name, parent_id):
    q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
         f"and trashed=false")
    if parent_id:
        q += f" and '{parent_id}' in parents"
    try:
        r = svc.files().list(q=q, pageSize=10,
                             fields="files(id,name)").execute()
        files = r.get("files", [])
        return files[0]["id"] if files else None
    except Exception:
        return None

def _create_folder(svc, name, parent_id):
    body = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    try:
        f = svc.files().create(body=body, fields="id").execute()
        return f["id"]
    except Exception:
        return None

def _load_map():
    try:
        with open(MAPPING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_map(m):
    with open(MAPPING_FILE, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent=2)

def user_folder_name(email):
    """Anonymný názov priečinka = hash emailu (email sa na Drive neukladá).
    Mapovanie email→hash ostáva len lokálne (data/drive_folders.json)."""
    key = email.strip().lower()
    m = _load_map()
    if key in m:
        return m[key]
    name = "u_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]
    m[key] = name
    _save_map(m)
    return name

def ensure_user_folder(email):
    """Vytvorí Studio/<hash>/ + Vault/Output/Planner. Vráti dict id alebo None."""
    svc = get_service()
    if not svc:
        return None
    root_id = _find_folder(svc, "Studio", None)
    if not root_id:
        root_id = _create_folder(svc, "Studio", None)
    fname = user_folder_name(email)
    ufold = _find_folder(svc, fname, root_id)
    if not ufold:
        ufold = _create_folder(svc, fname, root_id)
    if not ufold:
        return None
    subs = {}
    for name in ("Vault", "Output", "Planner"):
        fid = _find_folder(svc, name, ufold)
        if not fid:
            fid = _create_folder(svc, name, ufold)
        subs[name] = fid
    return {"user": ufold, **subs}

def get_redirect_uri():
    """Registrovaný redirect URI z credentials.json (Web client)."""
    try:
        with open(CRED_FILE, "r", encoding="utf-8") as f:
            uris = json.load(f).get("web", {}).get("redirect_uris", [])
        if uris:
            return uris[0]
    except Exception:
        pass
    return "http://localhost:5000/drive/callback"

def upload_file(local_path, email, log=None):
    """Nahrá lokálny súbor do Studio/<hash>/Output so zdieľaním
    'anyone with link' a vráti priamy download URL (alebo None pri chybe)."""
    svc = get_service()
    if not svc:
        return None
    try:
        folders = ensure_user_folder(email)
        if not folders or not folders.get("Output"):
            if log:
                log("⚠ Nepodarilo sa nájsť Output priečinok na Drive.")
            return None
        name = os.path.basename(local_path)
        mime = ("application/zip" if local_path.lower().endswith(".zip")
                else "application/octet-stream")
        media = MediaFileUpload(local_path, mimetype=mime, resumable=True)
        body = {"name": name, "parents": [folders["Output"]]}
        f = svc.files().create(body=body, media_body=media, fields="id").execute()
        fid = f["id"]
        svc.permissions().create(fileId=fid,
                                 body={"type": "anyone", "role": "reader"}).execute()
        return (f"https://drive.usercontent.google.com/download?id={fid}"
                f"&export=download&confirm=t")
    except Exception as e:
        if log:
            log(f"⚠ Drive upload zlyhal: {e}")
        return None


def upload_to_root_folder(local_path, folder_name, log=None):
    """Nahrá súbor do priečinka <folder_name> v KORENI Google Drive
    (vytvorí ho, ak neexistuje). Zdieľa 'anyone with link' a vráti priamy
    download URL (alebo None pri chybe)."""
    svc = get_service()
    if not svc:
        if log:
            log("⚠ Google Drive nie je pripojený.")
        return None
    try:
        fid = _find_folder(svc, folder_name, None)
        if not fid:
            fid = _create_folder(svc, folder_name, None)
        if not fid:
            if log:
                log(f"⚠ Nepodarilo sa vytvoriť priečinok '{folder_name}'.")
            return None
        name = os.path.basename(local_path)
        low = local_path.lower()
        mime = ("video/mp4" if low.endswith(".mp4")
                else "video/webm" if low.endswith(".webm")
                else "video/quicktime" if low.endswith(".mov")
                else "application/octet-stream")
        media = MediaFileUpload(local_path, mimetype=mime, resumable=True)
        body = {"name": name, "parents": [fid]}
        f = svc.files().create(body=body, media_body=media, fields="id").execute()
        svc.permissions().create(fileId=f["id"],
                                 body={"type": "anyone", "role": "reader"}).execute()
        return (f"https://drive.usercontent.google.com/download?id={f['id']}"
                f"&export=download&confirm=t")
    except Exception as e:
        if log:
            log(f"⚠ Drive upload zlyhal: {e}")
        return None

