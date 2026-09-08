#!/usr/bin/env python3
"""
Drive Drop – Standalone Web Aplikácia (Flask).
Jednoduchý, rýchly a moderný file uploader a downloader pre priečinok UPLOADED na Google Drive.
Port: 5050 (predvolený)
"""
import os
import sys
import secrets
import datetime
from functools import wraps
from flask import (Flask, request, session, redirect, url_for, render_template,
                   send_file, jsonify, flash)
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import drive

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
SECRET_FILE = os.path.join(DATA_DIR, "secret.key")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
TEMP_DIR = os.path.join(DATA_DIR, "temp_uploads")
os.makedirs(TEMP_DIR, exist_ok=True)

# Predvolené heslo patrik3924
DEFAULT_PASSWORD = "patrik3924"

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB limit
app.permanent_session_lifetime = datetime.timedelta(days=60)

# ProxyFix pre beh za Nginx pod prefixom /drive
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

if os.path.exists(SECRET_FILE):
    try:
        app.secret_key = open(SECRET_FILE, "rb").read()
    except Exception:
        app.secret_key = secrets.token_bytes(32)
else:
    app.secret_key = secrets.token_bytes(32)
    with open(SECRET_FILE, "wb") as f:
        f.write(app.secret_key)


@app.context_processor
def inject_globals():
    return {
        "prefix": request.script_root or "",
        "drive_connected": drive.is_connected(),
        "has_creds": drive.has_credentials()
    }


def get_stored_password():
    """Načíta heslo z config.json alebo vráti DEFAULT_PASSWORD."""
    if os.path.exists(CONFIG_FILE):
        try:
            import json
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                c = json.load(f)
                return c.get("password", DEFAULT_PASSWORD)
        except Exception:
            pass
    return DEFAULT_PASSWORD


def is_authenticated():
    return session.get("authenticated") is True


def auth_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not is_authenticated():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Neautorizovaný prístup. Prihláste sa."}), 401
            return redirect(url_for("index"))
        return f(*a, **kw)
    return wrapper


# ─── Hlavné zobrazenie ─────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    auth = is_authenticated()
    return render_template("index.html",
                           authenticated=auth,
                           folder_name="UPLOADED")


# ─── Autentifikácia ───────────────────────────────────────────────────────────

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    pwd = (data.get("password") or request.form.get("password") or "").strip()

    valid_pwd = get_stored_password()
    if pwd == valid_pwd or pwd == DEFAULT_PASSWORD:
        session.permanent = True
        session["authenticated"] = True
        session["user"] = "Patrik"
        if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"status": "ok", "redirect": url_for("index")})
        return redirect(url_for("index"))

    if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"status": "error", "message": "Nesprávne heslo."}), 401
    flash("Nesprávne heslo. Skús znova.")
    return redirect(url_for("index"))


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


# ─── API pre prácu so súbormi ──────────────────────────────────────────────────

@app.route("/api/status", methods=["GET"])
@auth_required
def api_status():
    return jsonify({
        "connected": drive.is_connected(),
        "has_credentials": drive.has_credentials(),
        "folder": "UPLOADED"
    })


@app.route("/api/files", methods=["GET"])
@auth_required
def api_files():
    try:
        files = drive.list_files("UPLOADED")
        total_bytes = sum(f.get("size", 0) for f in files)
        return jsonify({
            "status": "ok",
            "connected": drive.is_connected(),
            "folder": "UPLOADED",
            "files": files,
            "count": len(files),
            "total_size": total_bytes,
            "total_size_str": drive.format_size(total_bytes)
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/upload", methods=["POST"])
@auth_required
def api_upload():
    uploaded_files = request.files.getlist("file") or request.files.getlist("files")
    if not uploaded_files:
        single = request.files.get("file")
        if single:
            uploaded_files = [single]

    if not uploaded_files:
        return jsonify({"status": "error", "message": "Nebol odoslaný žiadny súbor."}), 400

    results = []
    errors = []

    for f in uploaded_files:
        if not f or not f.filename:
            continue
        original_name = os.path.basename(f.filename.strip())
        if not original_name:
            original_name = f"upload_{secrets.token_hex(4)}"

        temp_id = secrets.token_hex(8)
        temp_path = os.path.join(TEMP_DIR, f"{temp_id}_{original_name}")
        try:
            f.save(temp_path)
            res = drive.upload_file(temp_path, filename=original_name, folder_name="UPLOADED")
            if res:
                results.append(res)
            else:
                errors.append(f"Chyba pri nahrávaní súboru {original_name}.")
        except Exception as e:
            errors.append(f"Upload {original_name} zlyhal: {e}")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    return jsonify({
        "status": "ok" if results else "error",
        "uploaded": results,
        "errors": errors
    })


@app.route("/api/delete/<path:file_id>", methods=["POST", "DELETE"])
@auth_required
def api_delete(file_id):
    ok, msg = drive.delete_file(file_id, folder_name="UPLOADED")
    if ok:
        return jsonify({"status": "ok", "message": msg})
    return jsonify({"status": "error", "message": msg}), 400


# ─── Sťahovanie súborov ───────────────────────────────────────────────────────

@app.route("/download/<path:file_id>", methods=["GET"])
def download(file_id):
    # Overenie prihlásenia alebo tokenu
    if not is_authenticated():
        token = request.args.get("token")
        if token != get_stored_password():
            return redirect(url_for("index"))

    use_proxy = request.args.get("proxy") == "1" or str(file_id).startswith("local_")

    if not use_proxy:
        # Priame stiahnutie vysokou rýchlosťou z Google Drive
        return redirect(f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t")

    # Proxy stream cez server pre školské siete s blokovaným Google Drive
    res, fname, mime, is_local = drive.download_stream(file_id)
    if is_local and res:
        return send_file(res, as_attachment=True, download_name=fname, mimetype=mime)
    elif res:
        return send_file(res, as_attachment=True, download_name=fname, mimetype=mime)

    return redirect(f"https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t")


# ─── Google OAuth pripojenie (ak by bolo potrebné znova pripojiť) ─────────────

@app.route("/connect", methods=["GET"])
@auth_required
def connect_drive():
    if not drive.has_credentials():
        flash("Chýba súbor data/credentials.json.")
        return redirect(url_for("index"))
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(
            drive.CRED_FILE, drive.SCOPES, autogenerate_code_verifier=True)
        flow.redirect_uri = drive.get_redirect_uri()
        auth_url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true")
        session["oauth_state"] = state
        session["oauth_code_verifier"] = flow.code_verifier
        return redirect(auth_url)
    except Exception as e:
        flash(f"Chyba pripojenia Google Drive: {e}")
        return redirect(url_for("index"))


@app.route("/callback", methods=["GET"])
def drive_callback():
    from google_auth_oauthlib.flow import InstalledAppFlow
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            drive.CRED_FILE, drive.SCOPES, autogenerate_code_verifier=True)
        flow.redirect_uri = drive.get_redirect_uri()
        flow.code_verifier = session.get("oauth_code_verifier")
        flow.fetch_token(code=request.args.get("code"), state=session.get("oauth_state"))
        with open(drive.TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(flow.credentials.to_json())
        flash("Google Drive úspešne pripojený! Priečinok UPLOADED je pripravený.")
    except Exception as e:
        flash(f"Autorizácia Google Drive zlyhala: {e}")
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("DRIVE_PORT", 5050))
    host = os.environ.get("DRIVE_HOST", "0.0.0.0")
    debug = os.environ.get("DRIVE_DEBUG") == "1"
    print("=" * 55)
    print("  🚀 Drive Drop – File Uploader & Downloader")
    print(f"  Lokálna URL:  http://127.0.0.1:{port}")
    print(f"  Predvolené heslo: {DEFAULT_PASSWORD}")
    print("=" * 55)
    app.run(host=host, port=port, debug=debug)
