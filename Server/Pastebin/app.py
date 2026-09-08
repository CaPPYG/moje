#!/usr/bin/env python3
"""
PasteBin – Standalone Web Aplikácia (Flask).
Zabezpečený pastebin s podporou textu, kódu a obrázkov, TTL expiráciou,
ochranou heslom a funkciou burn-after-reading.
Port: 5060 (predvolený)
"""
import os
import sys
import secrets
import mimetypes
from flask import (Flask, request, session, redirect, url_for, render_template,
                   send_file, jsonify, abort, flash)
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import db
import cleaner

DATA_DIR = os.path.join(BASE_DIR, "data")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
SECRET_FILE = os.path.join(DATA_DIR, "secret.key")

ALLOWED_IMAGE_MIMES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif"
}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # 12 MB max

# ProxyFix pre beh za Nginx pod prefixom /paste a /p
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

# Štart background cleanera
cleaner.start_cleaner(interval=60)
db.init_db()


MASTER_PASSWORD = os.environ.get("PASTEBIN_PASSWORD", "patrik3924")


def is_creator_authenticated():
    return session.get("creator_auth") is True


def check_creator_auth():
    """Overí oprávnenie tvorcu cez session, HTTP hlavičky, JSON body alebo query parameter."""
    auth_header = request.headers.get("X-Master-Password") or request.headers.get("X-Paste-Master-Password")
    form_master = request.form.get("master_password") if request.form else None
    json_data = request.get_json(silent=True) if request.is_json else None
    json_master = json_data.get("master_password") if json_data else None
    query_master = request.args.get("master_password")

    return bool(
        is_creator_authenticated()
        or auth_header == MASTER_PASSWORD
        or form_master == MASTER_PASSWORD
        or json_master == MASTER_PASSWORD
        or query_master == MASTER_PASSWORD
    )


def get_base_url():
    """Zostaví základnú URL adresu (napr. https://garcarzp.online alebo lokálnu)."""
    proto = request.headers.get("X-Forwarded-Proto", request.scheme)
    host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host") or request.host
    return f"{proto}://{host}"


# ─── Creator Dashboard & Autentifikácia ─────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    if not is_creator_authenticated():
        return render_template("login.html")
    pastes = db.get_all_pastes()
    base_url = get_base_url()
    return render_template("create.html", pastes=pastes, base_url=base_url)


@app.route("/login", methods=["POST"])
def login():
    pwd = (request.form.get("password") or "").strip()
    if pwd == MASTER_PASSWORD:
        session.permanent = True
        session["creator_auth"] = True
        return redirect(url_for("index"))
    flash("Nesprávne heslo. Skúste znova.")
    return redirect(url_for("index"))


@app.route("/logout", methods=["GET"])
def logout():
    session.pop("creator_auth", None)
    return redirect(url_for("index"))


# ─── API Vytvorenie a Správa Záznamov ──────────────────────────────────────────

@app.route("/api/pastes", methods=["GET"])
def api_list_pastes():
    if not check_creator_auth():
        return jsonify({
            "status": "error",
            "message": "Neautorizovaný prístup. Vyžaduje sa prihlásenie tvorcu."
        }), 401

    raw_pastes = db.get_all_pastes()
    base_url = get_base_url()

    formatted = []
    for p in raw_pastes:
        item = dict(p)
        item["url"] = f"{base_url}/p/{p['id']}"
        item["raw_url"] = f"{base_url}/p/{p['id']}/raw"
        formatted.append(item)

    return jsonify({
        "status": "ok",
        "pastes": formatted,
        "count": len(formatted)
    })


@app.route("/api/paste", methods=["POST"])
def api_create_paste():
    # 0. Overenie oprávnenia pre vytvorenie záznamu
    if not check_creator_auth():
        return jsonify({
            "status": "error",
            "message": "Neautorizovaný prístup. Pre vytvorenie záznamu sa vyžaduje heslo aplikácie."
        }), 401
    # 1. Kontrola či ide o multipart alebo json
    paste_type = "text"
    content = None
    file_path = None
    file_mime = None

    if request.content_type and "multipart/form-data" in request.content_type:
        paste_type = request.form.get("type", "text")
        content = request.form.get("content")
        ttl = request.form.get("ttl", "0")
        burn = request.form.get("burn_after_reading") in ("1", "true", "True", True)
        password = (request.form.get("password") or "").strip() or None

        # Ak bol odoslaný súbor (obrázok)
        file_obj = request.files.get("file")
        if file_obj and file_obj.filename:
            paste_type = "image"
            mime = file_obj.mimetype or mimetypes.guess_type(file_obj.filename)[0] or ""
            if mime not in ALLOWED_IMAGE_MIMES:
                return jsonify({
                    "status": "error",
                    "message": "Nepovolený formát obrázka. Povolené sú iba JPEG, PNG, WEBP a GIF."
                }), 400

            ext = ALLOWED_IMAGE_MIMES[mime]
            filename = f"img_{secrets.token_hex(12)}{ext}"
            saved_rel_path = os.path.join("uploads", filename)
            saved_abs_path = os.path.join(DATA_DIR, saved_rel_path)
            file_obj.save(saved_abs_path)
            file_path = saved_rel_path
            file_mime = mime
    else:
        data = request.get_json(silent=True) or {}
        paste_type = data.get("type", "text")
        content = data.get("content", "")
        ttl = data.get("ttl", 0)
        burn = bool(data.get("burn_after_reading", False))
        password = (data.get("password") or "").strip() or None

    if paste_type == "text" and not content:
        return jsonify({"status": "error", "message": "Text nesmie byť prázdny."}), 400

    try:
        ttl_seconds = int(ttl) if ttl else 0
    except ValueError:
        ttl_seconds = 0

    record = db.create_paste(
        type_=paste_type,
        content=content,
        file_path=file_path,
        file_mime=file_mime,
        password=password,
        burn_after_reading=burn,
        ttl_seconds=ttl_seconds
    )

    base_url = get_base_url()
    public_url = f"{base_url}/p/{record['id']}"

    return jsonify({
        "status": "ok",
        "id": record["id"],
        "url": public_url,
        "burn_after_reading": record["burn_after_reading"],
        "expires_at": record["expires_at"]
    }), 201


# ─── Zobrazenie Paste (Web Viewer) ─────────────────────────────────────────────

@app.route("/p/<paste_id>", methods=["GET"])
def view_paste(paste_id):
    paste = db.get_paste(paste_id)
    if not paste:
        return render_template("404.html", paste_id=paste_id), 404

    # Kontrola ochrany heslom
    has_password = bool(paste.get("password_hash"))
    is_authenticated = session.get(f"auth_{paste_id}") is True

    if has_password and not is_authenticated:
        return render_template("password.html", paste_id=paste_id)

    # Inkrementácia počtu videní
    db.increment_views(paste_id)
    views = paste.get("views_count", 0) + 1

    burn = bool(paste.get("burn_after_reading"))
    # Ak ide o burn-after-reading, ihneď zmažeme záznam
    if burn:
        db.delete_paste(paste_id)
        session.pop(f"auth_{paste_id}", None)

    if paste["type"] == "image":
        img_url = url_for("raw_paste", paste_id=paste_id) if not burn else None
        # Pri burn-after-reading si pripravíme base64 obrázka aby sa nestratil pred zobrazením
        img_b64 = None
        if burn and paste.get("file_path"):
            abs_path = os.path.join(DATA_DIR, paste["file_path"])
            if os.path.isfile(abs_path):
                import base64
                with open(abs_path, "rb") as f:
                    img_b64 = base64.b64encode(f.read()).decode("utf-8")
                # Zmazať súbor z disku hneď po načítaní do pamäte
                try:
                    os.remove(abs_path)
                except Exception:
                    pass

        return render_template("view_image.html",
                               paste=paste,
                               burned=burn,
                               img_b64=img_b64,
                               views=views)
    else:
        return render_template("view_text.html",
                               paste=paste,
                               burned=burn,
                               views=views)


@app.route("/p/<paste_id>/auth", methods=["POST"])
def auth_paste(paste_id):
    paste = db.get_paste(paste_id)
    if not paste:
        return render_template("404.html", paste_id=paste_id), 404

    pwd = (request.form.get("password") or "").strip()
    if db.verify_password(pwd, paste.get("password_hash")):
        session[f"auth_{paste_id}"] = True
        return redirect(url_for("view_paste", paste_id=paste_id))

    flash("Nesprávne heslo. Skús to znova.")
    return redirect(url_for("view_paste", paste_id=paste_id))


# ─── Raw & Download Endpoint ──────────────────────────────────────────────────

@app.route("/p/<paste_id>/raw", methods=["GET"])
@app.route("/api/paste/<paste_id>/raw", methods=["GET"])
def raw_paste(paste_id):
    paste = db.get_paste(paste_id)
    if not paste:
        abort(404)

    # Kontrola hesla
    if paste.get("password_hash"):
        req_pwd = request.headers.get("X-Paste-Password") or request.args.get("password")
        if not req_pwd and session.get(f"auth_{paste_id}") is not True:
            return jsonify({"error": "Vyžaduje sa heslo."}), 401
        if req_pwd and not db.verify_password(req_pwd, paste.get("password_hash")):
            return jsonify({"error": "Nesprávne heslo."}), 401

    burn = bool(paste.get("burn_after_reading"))

    if paste["type"] == "text":
        resp = app.response_class(paste.get("content", ""), mimetype="text/plain; charset=utf-8")
        if burn:
            db.delete_paste(paste_id)
        return resp
    else:
        if not paste.get("file_path"):
            abort(404)
        abs_path = os.path.join(DATA_DIR, paste["file_path"])
        if not os.path.isfile(abs_path):
            abort(404)

        if burn:
            # Načítať do pamäte a zmazať
            import io
            with open(abs_path, "rb") as f:
                data_bytes = f.read()
            db.delete_paste(paste_id)
            return send_file(io.BytesIO(data_bytes), mimetype=paste.get("file_mime", "image/png"))
        else:
            return send_file(abs_path, mimetype=paste.get("file_mime", "image/png"))


# ─── JSON API pre Paste ────────────────────────────────────────────────────────

@app.route("/api/paste/<paste_id>", methods=["GET"])
def api_get_paste(paste_id):
    paste = db.get_paste(paste_id)
    if not paste:
        return jsonify({"error": "Záznam neexistuje alebo expiroval."}), 404

    # Kontrola hesla
    if paste.get("password_hash"):
        req_pwd = request.headers.get("X-Paste-Password") or request.args.get("password")
        if not req_pwd and session.get(f"auth_{paste_id}") is not True:
            return jsonify({"error": "Vyžaduje sa heslo cez X-Paste-Password."}), 401
        if req_pwd and not db.verify_password(req_pwd, paste.get("password_hash")):
            return jsonify({"error": "Nesprávne heslo."}), 401

    burn = bool(paste.get("burn_after_reading"))
    content = paste.get("content")

    if burn:
        db.delete_paste(paste_id)

    return jsonify({
        "status": "ok",
        "id": paste["id"],
        "type": paste["type"],
        "content": content,
        "file_mime": paste.get("file_mime"),
        "burn_after_reading": burn,
        "views_count": paste.get("views_count", 0) + 1,
        "expires_at": paste.get("expires_at"),
        "created_at": paste["created_at"]
    })


@app.route("/api/paste/<paste_id>", methods=["DELETE"])
def api_delete_paste(paste_id):
    if not check_creator_auth():
        return jsonify({
            "status": "error",
            "message": "Neautorizovaný prístup. Vyžaduje sa heslo aplikácie."
        }), 401

    deleted = db.delete_paste(paste_id)
    if not deleted:
        return jsonify({
            "status": "error",
            "message": "Záznam neexistuje alebo už bol zmazaný."
        }), 404

    return jsonify({
        "status": "ok",
        "message": "Záznam bol úspešne zmazaný.",
        "id": paste_id
    })


if __name__ == "__main__":
    port = int(os.environ.get("PASTEBIN_PORT", 5060))
    host = os.environ.get("PASTEBIN_HOST", "0.0.0.0")
    debug = os.environ.get("PASTEBIN_DEBUG") == "1"
    print("=" * 55)
    print("  🔒 PasteBin – Zabezpečený Pastebin & Image Share")
    print(f"  Lokálna URL:  http://127.0.0.1:{port}")
    print("=" * 55)
    app.run(host=host, port=port, debug=debug)
