#!/usr/bin/env python3
"""
Studio – Web appka (Flask, localhost-first).
Spúšťa:  python server.py   (alebo start_web.bat)
"""
import os, sys, re, json, hashlib, secrets, threading, zipfile, datetime, io, base64, shutil
from functools import wraps
from flask import (Flask, request, session, redirect, url_for, render_template,
                   send_file, jsonify, abort, flash)
from werkzeug.middleware.proxy_fix import ProxyFix

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
import core
import drive
import reels

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
USERS_FILE = os.path.join(DATA_DIR, "users.json")
SECRET_FILE = os.path.join(DATA_DIR, "secret.key")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 GB upload

# Beh pod URL prefixom (napr. /cappytools cez Nginx). ProxyFix nastaví SCRIPT_NAME
# z X-Forwarded-Prefix, takže url_for() a redirect() generujú prefixované URL.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


@app.context_processor
def _inject_script_root():
    return {"prefix": request.script_root}

if os.path.exists(SECRET_FILE):
    app.secret_key = open(SECRET_FILE, "rb").read()
else:
    app.secret_key = secrets.token_bytes(32)
    with open(SECRET_FILE, "wb") as f:
        f.write(app.secret_key)

JOBS = {}  # job_id -> dict(status, progress, total, log, result, error)

# ─── pomocné funkcie ──────────────────────────────────────────────────────────

def load_users():
    try:
        with open(USERS_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def hash_pw(pw):
    return hashlib.sha256(("cappy$" + pw).encode("utf-8")).hexdigest()

def user_dir(user):
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", user)
    d = os.path.join(DATA_DIR, safe)
    os.makedirs(d, exist_ok=True)
    return d

def user_json(user, default=None):
    p = os.path.join(user_dir(user), "settings.json")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def save_user_json(user, data):
    p = os.path.join(user_dir(user), "settings.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def current_user():
    return session.get("email")

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrapper

def is_admin():
    return session.get("role") == "admin"

def admin_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for("login"))
        if not is_admin():
            abort(403)
        return f(*a, **kw)
    return wrapper

def user_jobs(user):
    return {jid: j for jid, j in JOBS.items() if j["user"] == user}

def new_job(user, kind, total=1):
    jid = secrets.token_hex(8)
    JOBS[jid] = {"user": user, "kind": kind, "status": "running",
                 "progress": 0, "total": total, "log": [], "result": None, "error": None}
    return jid

def job_log(jid, msg):
    JOBS[jid]["log"].append(msg)

def job_done(jid, result=None):
    j = JOBS[jid]
    j["status"] = "done"
    j["progress"] = j["total"]
    j["result"] = result

def job_fail(jid, err):
    j = JOBS[jid]
    j["status"] = "error"
    j["error"] = str(err)

def log_and_raise(jid, e):
    job_log(jid, f"✗ {e}")
    job_fail(jid, e)

def job_runner(jid, fn):
    """Spustí fn(jid, log) v pozadí a skončí job."""
    def _run():
        try:
            fn(jid, lambda m: job_log(jid, m))
        except Exception as e:
            job_log(jid, f"✗ {e}")
            job_fail(jid, e)
    threading.Thread(target=_run, daemon=True).start()

def get_local_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "127.0.0.1"

def base_url():
    return f"http://{get_local_ip()}:5000"

# ─── Auth ─────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        action = request.form.get("action", "login")
        email = (request.form.get("email") or request.form.get("username") or request.form.get("login") or "").strip().lower()
        pw = request.form.get("password") or ""
        if not email or not pw:
            flash("Vyplň prihlasovacie meno / email aj heslo.")
            return redirect(url_for("login"))
        users = load_users()
        if action == "register":
            if email in users:
                flash("Účet už existuje – prihlás sa.")
            else:
                name = email.split("@")[0] if "@" in email else email
                users[email] = {"name": name,
                                "pw": hash_pw(pw), "created": datetime.date.today().isoformat(),
                                "role": "user"}
                save_users(users)
                session["email"] = email
                session["role"] = "user"
                threading.Thread(target=lambda: drive.ensure_user_folder(email), daemon=True).start()
                return redirect(url_for("dashboard"))
        else:
            u = users.get(email)
            if not u:
                for k, v in users.items():
                    if k.lower() == email:
                        u = v
                        email = k
                        break
            if not u or u.get("pw") != hash_pw(pw):
                flash("Nesprávne meno / email alebo heslo.")
            else:
                session["email"] = email
                session["role"] = u.get("role", "user")
                return redirect(url_for("dashboard"))
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def index():
    if current_user():
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

# ─── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    st = user_json(user)
    if not st:
        st = {}
    st.setdefault("cloaker", {"base_url": base_url(), "links": []})
    st.setdefault("filters", core.SAFE_FILTERS)
    st.setdefault("drive_output", True)
    return render_template("dashboard.html", user=user, cities=core.CITIES,
                           devices=core.DEVICES, filters=core.FILTER_DEFS,
                           base_url=base_url(), st=st, is_admin=is_admin())

@app.route("/api/job/<jid>")
@login_required
def api_job(jid):
    j = JOBS.get(jid)
    if not j or j["user"] != current_user():
        return jsonify({"error": "nenájdené"}), 404
    return jsonify({"status": j["status"], "progress": j["progress"],
                    "total": j["total"], "log": j["log"][-60:],
                    "result": j["result"], "error": j["error"]})

def save_upload(user, f):
    """Uloží upload a vráti cestu."""
    ud = user_dir(user)
    up = os.path.join(ud, "uploads"); os.makedirs(up, exist_ok=True)
    src = core.unique_path(os.path.join(up, os.path.basename(f.filename) or "file.bin"))
    f.save(src)
    return src

# ─── Spoofer (Metadata Cleaner) ───────────────────────────────────────────────

@app.route("/api/spoof", methods=["POST"])
@login_required
def api_spoof():
    user = current_user()
    files = request.files.getlist("file")
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "Žiadny súbor"}), 400
    try:
        use_loc = request.form.get("use_location") == "1"
        lat = float(request.form.get("lat") or 34.0522)
        lon = float(request.form.get("lon") or -118.2437)
        jitter = float(request.form.get("jitter") or 0.0015)
        copies = max(1, min(20, int(request.form.get("copies") or 1)))
    except ValueError:
        return jsonify({"error": "Zlé číslo v nastaveniach"}), 400

    filter_states = {}
    for fid, *_ in core.FILTER_DEFS:
        filter_states[fid] = {
            "enabled": request.form.get(f"f_{fid}_enabled") == "1",
            "min": float(request.form.get(f"f_{fid}_min", 0) or 0),
            "max": float(request.form.get(f"f_{fid}_max", 0) or 0),
        }

    fp_settings = {
        "enabled": request.form.get("fp_enabled") == "1",
        "mode": request.form.get("fp_mode", "random"),
        "make": None, "model": None,
        "days_back": int(request.form.get("fp_days") or 30),
        "random_date": request.form.get("fp_rand_date") == "1",
        "random_uid": request.form.get("fp_rand_uid") == "1",
        "no_ffmpeg_sig": request.form.get("fp_no_sig") == "1",
        "title": request.form.get("fp_title", ""),
        "artist": request.form.get("fp_artist", ""),
        "comment": request.form.get("fp_comment", ""),
    }
    if fp_settings["mode"] != "random":
        dev_name = request.form.get("fp_device", "")
        for dname, dmake, dmodel in core.DEVICES:
            if dname == dev_name:
                fp_settings["make"], fp_settings["model"] = dmake, dmodel
                break

    # Originál bez zmeny kvality = spracovanie bez vizuálnych filtrov (-c copy)
    orig_enabled = request.form.get("orig_enabled") == "1"
    clean_filters = {fid: {"enabled": False, "min": 0, "max": 0}
                     for fid, *_ in core.FILTER_DEFS}

    # Výstup na Google Drive (per-user, trvalé nastavenie)
    st = user_json(user) or {}
    st["drive_output"] = request.form.get("drive_output") == "1"
    save_user_json(user, st)
    use_drive = st["drive_output"] and drive.is_connected()

    # Uložíme všetky uploady + ich pôvodné cesty (kvôli názvom vo výstupe)
    srcs = []
    for f in files:
        orig = f.filename
        src = save_upload(user, f)
        srcs.append((src, orig))

    total = len(srcs) * (copies + (1 if orig_enabled else 0))
    jid = new_job(user, "spoof", total=total)
    ud = user_dir(user)

    def worker(jid, log):
        import random
        out_dir = os.path.join(ud, "output"); os.makedirs(out_dir, exist_ok=True)
        outputs = []
        done = 0
        for src, orig in srcs:
            rel_in = orig.replace("\\", "/")
            stem, ext = os.path.splitext(os.path.basename(rel_in))
            prefix = re.sub(r"[^A-Za-z0-9._-]+", "_", os.path.dirname(rel_in)).strip("_")
            base = f"{prefix}_{stem}" if prefix else stem
            if orig_enabled:
                log(f"📄 {orig} · originál (bez zmeny kvality)…")
                out = core.unique_path(os.path.join(out_dir, f"{base}_orig{ext}"))
                core.process_file(src, lat, lon, use_loc, clean_filters,
                                  fp_settings, log, out_path=out)
                outputs.append(out)
                done += 1
                JOBS[jid]["progress"] = done
            for i in range(1, copies + 1):
                log(f"📄 {orig} · kópia {i}/{copies}…")
                if use_loc:
                    jlat = lat + random.uniform(-jitter, jitter)
                    jlon = lon + random.uniform(-jitter, jitter)
                else:
                    jlat, jlon = lat, lon
                out = core.unique_path(os.path.join(out_dir, f"{base}_x_{i}{ext}"))
                core.process_file(src, jlat, jlon, use_loc, filter_states,
                                  fp_settings, log, out_path=out)
                outputs.append(out)
                done += 1
                JOBS[jid]["progress"] = done
        if len(outputs) == 1:
            rel = os.path.relpath(outputs[0], ud)
            result = {"download": f"/dl/{rel}"}
        else:
            zp = os.path.join(out_dir, f"spoofed_{secrets.token_hex(3)}.zip")
            with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
                for o in outputs:
                    z.write(o, os.path.basename(o))
            rel = os.path.relpath(zp, ud)
            result = {"download": f"/dl/{rel}", "files": len(outputs)}

        # Výstup na Google Drive (0 egress z VM, šetrí disk)
        if use_drive:
            target = zp if len(outputs) > 1 else outputs[0]
            log("Nahrávam výstup na Google Drive…")
            url = drive.upload_file(target, email=user, log=log)
            if url:
                try:
                    os.remove(target)
                except Exception:
                    pass
                result = {"download": url,
                          "files": result.get("files", 1), "via": "drive"}
                log("✓ Výstup je na Google Drive – odkaz sťahuje priamo Google (0 MB egressu).")

        # Uvoľnenie zdrojových uploadov z disku
        for src, _ in srcs:
            try:
                os.remove(src)
            except Exception:
                pass

        job_done(jid, result)

    job_runner(jid, worker)
    return jsonify({"job": jid})

# ─── Frame Extractor ──────────────────────────────────────────────────────────

@app.route("/api/frames", methods=["POST"])
@login_required
def api_frames():
    user = current_user()
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Žiadny súbor"}), 400
    src = save_upload(user, f)
    mode = request.form.get("mode", "interval")
    value = request.form.get("value", "5")
    fmt = request.form.get("fmt", "jpg")
    try:
        quality = int(request.form.get("quality") or 2)
    except ValueError:
        quality = 2
    jid = new_job(user, "frames")
    ud = user_dir(user)

    def worker(jid, log):
        out_root = os.path.join(ud, "output"); os.makedirs(out_root, exist_ok=True)
        count, folder = core.extract_frames(src, out_root, mode, value, fmt,
                                            quality, log=log)
        zp = os.path.join(out_root, f"frames_{secrets.token_hex(3)}.zip")
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
            for fn in sorted(os.listdir(folder)):
                z.write(os.path.join(folder, fn), fn)
        rel = os.path.relpath(zp, ud)
        job_done(jid, {"download": f"/dl/{rel}", "files": count})

    job_runner(jid, worker)
    return jsonify({"job": jid})

# ─── Audio Extractor ──────────────────────────────────────────────────────────

@app.route("/api/audio", methods=["POST"])
@login_required
def api_audio():
    user = current_user()
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Žiadny súbor"}), 400
    src = save_upload(user, f)
    fmt = request.form.get("fmt", "mp3")
    bitrate = request.form.get("bitrate", "192k")
    jid = new_job(user, "audio")
    ud = user_dir(user)

    def worker(jid, log):
        out_root = os.path.join(ud, "output"); os.makedirs(out_root, exist_ok=True)
        out = core.extract_audio(src, out_root, fmt, bitrate, log=log)
        rel = os.path.relpath(out, ud)
        job_done(jid, {"download": f"/dl/{rel}", "files": 1})

    job_runner(jid, worker)
    return jsonify({"job": jid})

# ─── Reels Downloader ─────────────────────────────────────────────────────────

@app.route("/api/reels", methods=["POST"])
@login_required
def api_reels():
    user = current_user()
    data = request.get_json(silent=True) or {}
    raw = data.get("urls") or []
    if isinstance(raw, str):
        raw = raw.splitlines()
    urls = []
    for u in raw:
        n = reels.normalize_link(u)
        if n and n not in urls:
            urls.append(n)
    if not urls:
        return jsonify({"error": "Žiadne platné odkazy (musia začínať http:// alebo https://)."}), 400

    jid = new_job(user, "reels", total=len(urls))
    missing = reels.check_tools()

    def worker(jid, log):
        if missing:
            msg = ("Chýbajú nástroje: " + ", ".join(missing) +
                   ". Nainštaluj: pip install -U yt-dlp  (a ffmpeg daj do PATH).")
            log("✗ " + msg)
            job_fail(jid, msg)
            return
        tmp = os.path.join(user_dir(user), "reels_tmp")
        os.makedirs(tmp, exist_ok=True)
        ok = fail = 0
        results = []
        for u in urls:
            log("▶ " + u)
            path = reels.download(u, tmp, log=log)
            if not path:
                fail += 1
            else:
                log("Nahrávam na Google Drive → priečinok „AI RAK“…")
                url = drive.upload_to_root_folder(path, "AI RAK", log=log)
                try:
                    os.remove(path)
                except Exception:
                    pass
                if url:
                    ok += 1
                    results.append({"url": u, "drive": url})
                    log("✓ Nahrané → " + url)
                else:
                    fail += 1
                    log("✗ Google Drive upload zlyhal (je Drive pripojený?).")
            JOBS[jid]["progress"] = ok + fail
        job_done(jid, {"ok": ok, "fail": fail, "results": results})

    job_runner(jid, worker)
    return jsonify({"job": jid})

# ─── Download (s prihlásením) ─────────────────────────────────────────────────

@app.route("/dl/<path:rel>")
@login_required
def download(rel):
    ud = os.path.realpath(user_dir(current_user()))
    path = os.path.realpath(os.path.join(ud, rel))
    if not path.startswith(ud + os.sep) or not os.path.isfile(path):
        abort(404)
    return send_file(path, as_attachment=True)

# ─── Admin ────────────────────────────────────────────────────────────────────

def folder_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for fn in files:
            try:
                total += os.path.getsize(os.path.join(root, fn))
            except OSError:
                pass
    return total

@app.route("/api/admin/users")
@admin_required
def api_admin_users():
    users = load_users()
    out = []
    for email, u in users.items():
        folder = os.path.join(DATA_DIR, re.sub(r"[^a-zA-Z0-9._-]", "_", email))
        out.append({"email": email, "name": u.get("name", ""),
                    "role": u.get("role", "user"), "created": u.get("created", ""),
                    "size": folder_size(folder) if os.path.isdir(folder) else 0})
    out.sort(key=lambda x: x["created"])
    return jsonify({"users": out, "total": sum(u["size"] for u in out),
                    "admin": current_user()})

@app.route("/api/admin/users/<email>", methods=["DELETE"])
@admin_required
def api_admin_delete_user(email):
    users = load_users()
    if email not in users:
        return jsonify({"error": "nenájdený"}), 404
    if users[email].get("role") == "admin":
        return jsonify({"error": "Admina nemôžeš zmazať"}), 400
    del users[email]
    save_users(users)
    folder = os.path.join(DATA_DIR, re.sub(r"[^a-zA-Z0-9._-]", "_", email))
    shutil.rmtree(folder, ignore_errors=True)
    return jsonify({"ok": True})

@app.route("/api/admin/users/<email>/role", methods=["POST"])
@admin_required
def api_admin_set_role(email):
    users = load_users()
    if email not in users:
        return jsonify({"error": "nenájdený"}), 404
    role = (request.get_json(silent=True) or {}).get("role", "user")
    users[email]["role"] = role if role in ("admin", "user") else "user"
    save_users(users)
    return jsonify({"ok": True})

@app.route("/api/admin/overview")
@admin_required
def api_admin_overview():
    """Prehľad všetkých užívateľov: rozvrhy + cloaker linky."""
    out = []
    for email in load_users():
        d = user_dir(email)
        sched = []
        try:
            with open(os.path.join(d, "schedule.json"), "r", encoding="utf-8") as f:
                sched = json.load(f)
        except Exception:
            pass
        st = user_json(email)
        cloak = st.get("cloaker", {}).get("links", [])
        planner = st.get("planner", {})
        out.append({"email": email,
                    "schedule_days": len(sched),
                    "schedule": sched[:7],
                    "cloaker": cloak,
                    "planner": {"videos": len(planner.get("videos", [])),
                                "devices": len(planner.get("devices", [])),
                                "ready": bool(planner.get("ready"))}})
    return jsonify({"users": out})

# ─── Google Drive (admin) ─────────────────────────────────────────────────────

@app.route("/drive/connect")
@admin_required
def drive_connect():
    if not drive.has_credentials():
        flash("Chýba data/credentials.json – nastav ho podľa návodu (Admin → Google Drive).")
        return redirect(url_for("dashboard"))
    flow = drive_flow()
    auth_url, state = flow.authorization_url(access_type="offline",
                                             include_granted_scopes="true")
    session["oauth_state"] = state
    session["oauth_code_verifier"] = flow.code_verifier
    return redirect(auth_url)

@app.route("/drive/callback")
def drive_callback():
    flow = drive_flow()
    flow.code_verifier = session.get("oauth_code_verifier")
    try:
        flow.fetch_token(code=request.args.get("code"),
                         state=session.get("oauth_state"))
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f"Google prihlásenie zlyhalo: {e}")
        return redirect(url_for("dashboard"))
    with open(drive.TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(flow.credentials.to_json())
    # vytvor priečinky pre všetkých existujúcich užívateľov
    for email in load_users():
        try:
            drive.ensure_user_folder(email)
        except Exception:
            pass
    flash("Google Drive pripojený ✓ Priečinky pre užívateľov sú vytvorené.")
    return redirect(url_for("dashboard"))

def drive_flow():
    from google_auth_oauthlib.flow import InstalledAppFlow
    # PKCE (code_verifier) je od 2024 povinný – generuje sa automaticky
    flow = InstalledAppFlow.from_client_secrets_file(
        drive.CRED_FILE, drive.SCOPES, autogenerate_code_verifier=True)
    # Web client: použi registrovaný redirect URI z credentials.json
    flow.redirect_uri = drive.get_redirect_uri()
    return flow

@app.route("/api/drive/status")
@admin_required
def api_drive_status():
    return jsonify({"connected": drive.is_connected(),
                    "has_creds": drive.has_credentials(),
                    "users": list(load_users().keys())})

@app.route("/api/drive/sync", methods=["POST"])
@admin_required
def api_drive_sync():
    if not drive.is_connected():
        return jsonify({"error": "Google Drive nie je pripojený"}), 400
    results = {}
    for email in load_users():
        try:
            r = drive.ensure_user_folder(email)
            results[email] = "ok" if r else "fail"
        except Exception as e:
            results[email] = str(e)
    return jsonify({"results": results})

# ─── Link Cloaker ─────────────────────────────────────────────────────────────

@app.route("/api/cloaker/save", methods=["POST"])
@login_required
def api_cloaker_save():
    user = current_user()
    data = request.get_json(silent=True) or {}
    st = user_json(user, {})
    st["cloaker"] = {"base_url": data.get("base_url", base_url()),
                     "links": data.get("links", [])}
    save_user_json(user, st)
    return jsonify({"ok": True})

@app.route("/api/cloaker/generate", methods=["POST"])
@login_required
def api_cloaker_generate():
    user = current_user()
    st = user_json(user, {})
    c = st.get("cloaker", {})
    links = core.cloak_links(c.get("base_url", base_url()), c.get("links", []))
    return jsonify({"links": links})

@app.route("/c/<slug>")
def cloak_redirect(slug):
    """Skutočný redirect: BASE_URL/c/<slug> → cieľová URL."""
    for folder in os.listdir(DATA_DIR):
        sp = os.path.join(DATA_DIR, folder, "settings.json")
        if not os.path.isfile(sp):
            continue
        try:
            with open(sp, "r", encoding="utf-8") as f:
                st = json.load(f)
        except Exception:
            continue
        for ln in st.get("cloaker", {}).get("links", []):
            if ln.get("slug") == slug and ln.get("url"):
                return redirect(ln["url"])
    abort(404)

# ─── Planner ──────────────────────────────────────────────────────────────────

@app.route("/api/upload/planner", methods=["POST"])
@login_required
def api_upload_planner():
    user = current_user()
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Žiadny súbor"}), 400
    pdir = os.path.join(user_dir(user), "uploads", "planner")
    os.makedirs(pdir, exist_ok=True)
    src = core.unique_path(os.path.join(pdir, os.path.basename(f.filename)))
    f.save(src)
    return jsonify({"file": os.path.basename(src)})

@app.route("/api/planner/save", methods=["POST"])
@login_required
def api_planner_save():
    user = current_user()
    data = request.get_json(silent=True) or {}
    st = user_json(user, {})
    try:
        vmin = max(1, min(10, int(data.get("vmin", 1))))
        vmax = max(vmin, min(10, int(data.get("vmax", 3))))
    except (TypeError, ValueError):
        vmin, vmax = 1, 3
    st["planner"] = {"videos": data.get("videos", []),
                     "devices": data.get("devices", []),
                     "vmin": vmin, "vmax": vmax,
                     "start": data.get("start", datetime.date.today().isoformat()),
                     "ready": bool(data.get("ready", st.get("planner", {}).get("ready", False)))}
    save_user_json(user, st)
    return jsonify({"ok": True})

@app.route("/api/planner/generate", methods=["POST"])
@login_required
def api_planner_generate():
    user = current_user()
    st = user_json(user, {})
    pl = st.get("planner", {})
    videos = pl.get("videos", [])
    devices = pl.get("devices", [])
    if not videos or not devices:
        return jsonify({"error": "Pridaj videá aj zariadenia"}), 400
    pdir = os.path.join(user_dir(user), "uploads", "planner")
    vid_paths = [os.path.join(pdir, v) for v in videos if os.path.isfile(os.path.join(pdir, v))]
    if not vid_paths:
        return jsonify({"error": "Videá sa nenašli – nahraj ich znova"}), 400
    vmin, vmax = int(pl.get("vmin", 1)), int(pl.get("vmax", 3))
    try:
        start = datetime.date.fromisoformat(pl.get("start") or datetime.date.today().isoformat())
    except ValueError:
        start = datetime.date.today()
    sched = core.make_schedule(len(vid_paths), len(devices), vmin, vmax, start)
    total = sum(len(a) for _, day in sched for a in day.values())
    jid = new_job(user, "planner", total=total)
    ud = user_dir(user)
    out_root = os.path.join(ud, "output", "planner")

    dev_lat = []
    for d in devices:
        lat = lon = None
        for cn, clat, clon in core.CITIES:
            if cn == d.get("city", "") and clat is not None:
                lat, lon = clat, clon
                break
        dev_lat.append((lat, lon))

    def worker(jid, log):
        progress = 0
        for date, assignments in sched:
            dstr = date.isoformat()
            for di, vid_idxs in assignments.items():
                dev = devices[di]
                devdir = os.path.join(out_root, dev["name"], dstr)
                lat, lon = dev_lat[di]
                try:
                    jitter = float(dev.get("jitter", 0.0015))
                except (TypeError, ValueError):
                    jitter = 0.0015
                make, model = dev.get("make"), dev.get("model")
                for vi in vid_idxs:
                    src = vid_paths[vi]
                    stem, ext = os.path.splitext(os.path.basename(src))
                    out = os.path.join(devdir, f"{stem}_x_{di+1}{ext}")
                    log(f"{dev['name']} / {dstr}: {os.path.basename(out)}")
                    core.spoof_video(src, out, lat, lon, jitter, make, model, log)
                    progress += 1
                    JOBS[jid]["progress"] = progress
        with open(os.path.join(ud, "schedule.json"), "w", encoding="utf-8") as f:
            json.dump(core.schedule_to_json(sched, devices, vid_paths),
                      f, ensure_ascii=False, indent=2)
        st2 = user_json(user, {})
        st2.setdefault("planner", {})["ready"] = True
        save_user_json(user, st2)
        job_done(jid, {"devices": len(devices), "days": len(sched)})

    job_runner(jid, worker)
    return jsonify({"job": jid})

@app.route("/api/planner/status")
@login_required
def api_planner_status():
    user = current_user()
    st = user_json(user, {})
    pl = st.get("planner", {})
    ready = bool(pl.get("ready"))
    sched = []
    try:
        with open(os.path.join(user_dir(user), "schedule.json"), "r", encoding="utf-8") as f:
            sched = json.load(f)
    except Exception:
        pass
    dev_links = []
    if ready:
        for d in pl.get("devices", []):
            dev_links.append({"name": d.get("name", "?"),
                              "url": f"/device/{d.get('name','?')}/{datetime.date.today().isoformat()}"})
    return jsonify({"ready": ready, "videos": pl.get("videos", []),
                    "devices": pl.get("devices", []),
                    "schedule": sched, "dev_links": dev_links,
                    "base_url": base_url()})

# ─── Mobilné stránky zariadení + QR ───────────────────────────────────────────

@app.route("/device/<dev>/<date>")
def device_page(dev, date):
    target = date
    try:
        datetime.date.fromisoformat(target)
    except ValueError:
        target = datetime.date.today().isoformat()
    for folder in sorted(os.listdir(DATA_DIR)):
        sd = os.path.join(DATA_DIR, folder, "schedule.json")
        if not os.path.isfile(sd):
            continue
        try:
            with open(sd, "r", encoding="utf-8") as f:
                sched = json.load(f)
        except Exception:
            continue
        entry = next((e for e in sched if e.get("date") == target), None)
        if entry is None:
            continue
        fnames = entry.get("devices", {}).get(dev)
        if fnames is None:
            continue
        # index zariadenia → názov spoofnutých kópií je stem_x_{di+1}.ext
        di = 0
        try:
            with open(os.path.join(DATA_DIR, folder, "settings.json"), "r", encoding="utf-8") as f:
                st = json.load(f)
            names = [d.get("name") for d in st.get("planner", {}).get("devices", [])]
            di = names.index(dev)
        except Exception:
            pass
        ud = os.path.join(DATA_DIR, folder)
        day_dir = os.path.join(ud, "output", "planner", dev, target)
        items = []
        for fn in fnames:
            stem, ext = os.path.splitext(fn)
            real = f"{stem}_x_{di + 1}{ext}"
            p = os.path.join(day_dir, real)
            rel = os.path.join("output", "planner", dev, target, real).replace("\\", "/")
            items.append({"name": real, "dl": f"/pdl/{folder}/{rel}",
                          "exists": os.path.isfile(p)})
        prev = (datetime.date.fromisoformat(target) - datetime.timedelta(days=1)).isoformat()
        nxt = (datetime.date.fromisoformat(target) + datetime.timedelta(days=1)).isoformat()
        return render_template("device.html", dev=dev, date=target, items=items,
                               prev=prev, nxt=nxt, today=datetime.date.today().isoformat())
    abort(404)

@app.route("/pdl/<ufolder>/<path:rel>")
def pdl(ufolder, rel):
    base = os.path.realpath(os.path.join(DATA_DIR, ufolder))
    path = os.path.realpath(os.path.join(base, rel))
    if not path.startswith(base + os.sep) or not os.path.isfile(path):
        abort(404)
    return send_file(path, as_attachment=True)

@app.route("/api/qr")
def api_qr():
    url = request.args.get("url", "")
    try:
        import qrcode
        img = qrcode.make(url)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return send_file(io.BytesIO(buf.getvalue()), mimetype="image/png")
    except Exception:
        abort(404)

if __name__ == "__main__":
    print("=" * 50)
    print("  Studio WEB")
    print("  Lokálne:   http://127.0.0.1:5000")
    print(f"  V LAN:     http://{get_local_ip()}:5000")
    print("=" * 50)
    debug = os.environ.get("CAPPY_DEBUG") == "1"
    # Produkcia (systemd/nginx): počúvaj len na localhost, nginx robí proxy.
    # Lokálny vývoj: CAPPY_HOST=0.0.0.0 pre prístup z LAN.
    host = os.environ.get("CAPPY_HOST", "127.0.0.1" if not debug else "0.0.0.0")
    app.run(host=host, port=5000, debug=debug, use_reloader=False)





