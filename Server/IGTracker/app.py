import os
import sys
import time
import threading
from functools import wraps
from datetime import datetime, timezone
import uuid

import io
import tempfile
from flask import Flask, render_template, render_template_string, request, jsonify, redirect, url_for, session, flash, send_from_directory, Response, stream_with_context
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
import httpx
import logging

logger = logging.getLogger(__name__)

import db
import scraper
import ig_api
import health_monitor
import spoofer
import vault_planner
import notifier
import gdrive_vault

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_DIR = os.path.join(BASE_DIR, "data", "vault")
SPOOFED_DIR = os.path.join(VAULT_DIR, "spoofed")
THUMBS_DIR = os.path.join(VAULT_DIR, "thumbs")
os.makedirs(VAULT_DIR, exist_ok=True)
os.makedirs(SPOOFED_DIR, exist_ok=True)
os.makedirs(THUMBS_DIR, exist_ok=True)
MASTER_PASSWORD = os.environ.get("IG_TRACKER_PASSWORD", "patrik3924")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ig-tracker-secret-key-patrik3924")

# ProxyFix pre beh za Nginx pod prefixom /ig
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Inicializácia databázy
db.init_db()


def is_authenticated():
    return session.get("authenticated") is True


def auth_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        auth_header = request.headers.get("X-Master-Password")
        if is_authenticated() or auth_header == MASTER_PASSWORD:
            return f(*a, **kw)
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": "Neautorizovaný prístup. Zadajte heslo."}), 401
        return redirect(url_for("index"))
    return wrapper


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Master-Password"
    return response


# ─── Web Rozhranie ─────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    auth_header = request.headers.get("X-Master-Password")
    if not is_authenticated() and auth_header != MASTER_PASSWORD:
        return render_template("login.html")
    accounts = db.get_accounts_with_metrics()
    total_followers = sum(a["followers"] for a in accounts if a["has_data"])
    total_views = sum(a["total_views"] for a in accounts if a["has_data"])
    return render_template(
        "index.html",
        accounts=accounts,
        total_followers_fmt=db.format_number(total_followers),
        total_views_fmt=db.format_number(total_views)
    )


@app.route("/login", methods=["POST"])
def login():
    pwd = (request.form.get("password") or "").strip()
    if pwd == MASTER_PASSWORD:
        session.permanent = True
        session["authenticated"] = True
        return redirect(url_for("index"))
    flash("Nesprávne heslo. Skúste znova.")
    return redirect(url_for("index"))


@app.route("/logout", methods=["GET"])
def logout():
    session.pop("authenticated", None)
    return redirect(url_for("index"))


# ─── REST API ──────────────────────────────────────────────────────────────────

@app.route("/api/ig-tracker", methods=["GET"])
@auth_required
def api_get_tracker():
    """Vráti zoznam sledovaných profilov, ich najnovšie čísla, top reelko a vypočítaný rozdiel (delta)."""
    accounts = db.get_accounts_with_metrics()
    total_followers = sum(a["followers"] for a in accounts if a["has_data"])
    total_views = sum(a["total_views"] for a in accounts if a["has_data"])

    return jsonify({
        "status": "ok",
        "count": len(accounts),
        "total_followers": total_followers,
        "total_followers_fmt": db.format_number(total_followers),
        "total_views": total_views,
        "total_views_fmt": db.format_number(total_views),
        "accounts": accounts
    }), 200


@app.route("/api/ig-tracker/add", methods=["POST"])
@auth_required
def api_add_account():
    """Pridá nové používateľské meno na sledovanie a okamžite stiahne úvodné dáta."""
    data = request.get_json(silent=True) or request.form or {}
    username = (data.get("username") or "").strip().lstrip("@").lower()

    if not username:
        return jsonify({"status": "error", "message": "Zadajte používateľské meno (napr. @profil)."}), 400

    # 1. Získať alebo vytvoriť záznam v databáze
    existing = db.get_account_by_username(username)
    if existing:
        account_id = existing["id"]
    else:
        account_id = db.add_account(username=username)

    # 2. Získať aktuálne dáta cez scraper
    try:
        scraped = scraper.fetch_profile(username)
        # Aktualizovať meno a avatar
        db.add_account(
            username=username,
            full_name=scraped.get("full_name", username),
            avatar_url=scraped.get("avatar_url", "")
        )
        # Uložiť snapshot
        db.add_snapshot(
            account_id=account_id,
            followers=scraped.get("followers", 0),
            following=scraped.get("following", 0),
            posts_count=scraped.get("posts_count", 0),
            top_reel_url=scraped.get("top_reel_url"),
            top_reel_views=scraped.get("top_reel_views", 0),
            top_reel_likes=scraped.get("top_reel_likes", 0),
            total_views=scraped.get("total_views", 0),
            avg_views=scraped.get("avg_views", 0),
            engagement_rate=scraped.get("engagement_rate", 0.0),
            last_post_date=scraped.get("last_post_date"),
            last_post_views=scraped.get("last_post_views", 0),
            last_post_url=scraped.get("last_post_url"),
            last_post_likes=scraped.get("last_post_likes", 0),
            usa_audience_pct=scraped.get("usa_audience_pct")
        )
    except Exception as e:
        print(f"Chyba pri scrapovaní {username}: {e}")

    accounts = db.get_accounts_with_metrics()
    return jsonify({
        "status": "ok",
        "message": f"Účet @{username} bol úspešne pridaný.",
        "accounts": accounts
    }), 201


@app.route("/api/ig-tracker/<int:account_id>", methods=["DELETE"])
@auth_required
def api_delete_account(account_id):
    """Zmaže účet zo sledovania."""
    db.delete_account(account_id)
    accounts = db.get_accounts_with_metrics()
    return jsonify({
        "status": "ok",
        "message": "Účet bol odstránený.",
        "accounts": accounts
    }), 200


@app.route("/api/ig-tracker/sync", methods=["POST"])
@auth_required
def api_sync():
    """Manuálny force-refresh všetkých sledovaných účtov naraz v jednom batchi."""
    accounts = db.get_all_accounts()
    if not accounts:
        return jsonify({
            "status": "ok",
            "message": "Žiadne účty na synchronizáciu.",
            "accounts": []
        }), 200

    usernames = [a["username"] for a in accounts]
    batch_data = scraper.fetch_profiles_batch(usernames)
    synced_count = 0

    for acc in accounts:
        uname = acc["username"].lower()
        scraped = batch_data.get(uname)
        if not scraped:
            try:
                scraped = scraper.fetch_profile(uname)
            except Exception as e:
                print(f"Sync fallback chyba pre {uname}: {e}")

        if scraped:
            try:
                db.add_account(
                    username=uname,
                    full_name=scraped.get("full_name", uname),
                    avatar_url=scraped.get("avatar_url", "")
                )
                db.add_snapshot(
                    account_id=acc["id"],
                    followers=scraped.get("followers", 0),
                    following=scraped.get("following", 0),
                    posts_count=scraped.get("posts_count", 0),
                    top_reel_url=scraped.get("top_reel_url"),
                    top_reel_views=scraped.get("top_reel_views", 0),
                    top_reel_likes=scraped.get("top_reel_likes", 0),
                    total_views=scraped.get("total_views", 0),
                    avg_views=scraped.get("avg_views", 0),
                    engagement_rate=scraped.get("engagement_rate", 0.0),
                    last_post_date=scraped.get("last_post_date"),
                    last_post_views=scraped.get("last_post_views", 0),
                    last_post_url=scraped.get("last_post_url"),
                    last_post_likes=scraped.get("last_post_likes", 0),
                    usa_audience_pct=scraped.get("usa_audience_pct")
                )
                synced_count += 1
            except Exception as e:
                print(f"Chyba pri ukladaní {uname}: {e}")

    updated_accounts = db.get_accounts_with_metrics()
    return jsonify({
        "status": "ok",
        "message": f"Úspešne synchronizovaných {synced_count} z {len(accounts)} účtov.",
        "accounts": updated_accounts
    }), 200


@app.route("/api/ig-tracker/<int:account_id>/token", methods=["POST"])
@auth_required
def api_set_account_token(account_id):
    """Overí a uloží Meta Access Token (a prípadne IG User ID) k účtu."""
    data = request.get_json(silent=True) or request.form or {}
    token = (data.get("access_token") or "").strip()
    user_id = (data.get("ig_user_id") or "").strip()

    if not token:
        return jsonify({"status": "error", "message": "Zadajte Meta Access Token."}), 400

    # Overenie tokenu cez Graph API
    verified = ig_api.verify_token(token)
    if not verified.get("valid"):
        return jsonify({
            "status": "error",
            "message": f"Neplatný token: {verified.get('error', 'Overenie zlyhalo')}"
        }), 400

    detected_user_id = verified.get("id")
    final_user_id = user_id or detected_user_id
    detected_username = verified.get("username", "")

    db.set_account_token(account_id, token, final_user_id)
    account = db.get_account_by_id(account_id)

    return jsonify({
        "status": "ok",
        "message": f"Token úspešne overený a prepojený pre @{detected_username or (account.get('username') if account else '')} (ID: {final_user_id})!",
        "ig_user_id": final_user_id,
        "username": detected_username,
        "account_id": account_id
    }), 200


@app.route("/api/ig-tracker/<int:account_id>/token", methods=["DELETE"])
@auth_required
def api_delete_account_token(account_id):
    """Odpojí token od daného účtu."""
    db.set_account_token(account_id, None, None)
    return jsonify({
        "status": "ok",
        "message": "Token bol úspešne odpojený od účtu.",
        "account_id": account_id
    }), 200


@app.route("/api/ig-tracker/<int:account_id>/audience", methods=["POST"])
@auth_required
def api_update_account_audience(account_id):
    """Aktualizuje podiel USA publika pre daný účet."""
    data = request.get_json(silent=True) or request.form or {}
    val = data.get("usa_audience_pct")
    try:
        pct = float(val) if val is not None and str(val).strip() != "" else None
        db.update_account_usa_audience(account_id, pct)
        return jsonify({
            "status": "ok",
            "message": f"Podiel USA publika bol nastavený na {pct}%" if pct is not None else "Hodnota bola vynulovaná.",
            "usa_audience_pct": pct
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Neplatná hodnota: {e}"}), 400


# ─── Meta / Instagram OAuth Login Flow ────────────────────────────────────────

# Hlavná fungujúca Meta Developer App (poster-IG, ID: 1397331775709610) pre všetky profily
META_APP_ID = os.environ.get("META_APP_ID", "1397331775709610")
META_APP_SECRET = os.environ.get("META_APP_SECRET", "784a1f481055751ed2ba7636febeb07b")

# Smerujeme aj US appku na rovnakú fungujúcu appku (poster-IG)
US_META_APP_ID = os.environ.get("US_META_APP_ID", "1397331775709610")
US_META_APP_SECRET = os.environ.get("US_META_APP_SECRET", "784a1f481055751ed2ba7636febeb07b")

META_REDIRECT_URI = os.environ.get("META_REDIRECT_URI", "https://garcarzp.online/ig/oauth/callback")


@app.route("/connect", methods=["GET"])
def oauth_connect(force_region=None):
    """
    Odkaz pre mobil: otvorí natívny Instagram dialóg na prihlásenie a autorizáciu.
    Podporuje parameter ?region=sk|us a ?account_id=... pre spárovanie s existujúcim profilom.
    """
    region = force_region or request.args.get("region", "us").lower()
    account_id = request.args.get("account_id", "")
    app_id = US_META_APP_ID if region == "us" else META_APP_ID
    state = f"{region}:{account_id}" if account_id else region

    # Instagram Login scope pre Creator/Business
    scope = "instagram_business_basic,instagram_business_content_publish"

    import urllib.parse
    params = {
        "client_id": app_id,
        "redirect_uri": META_REDIRECT_URI,
        "response_type": "code",
        "scope": scope,
        "state": state,
    }
    ig_auth_url = f"https://www.instagram.com/oauth/authorize?{urllib.parse.urlencode(params)}"
    return redirect(ig_auth_url)


@app.route("/connect-us", methods=["GET"])
def oauth_connect_us():
    """Priamy odkaz pre US cloud mobily v Multilogine (použije oddelenú US Meta Appku)."""
    return oauth_connect(force_region="us")


@app.route("/accept-invite", methods=["GET"])
def accept_invite_redirect():
    """Otvára správu prístupov a pozvánok priamo v internom prehliadači Instagramu bez nutnosti hesla."""
    return redirect("https://www.instagram.com/accounts/manage_access/")


@app.route("/oauth/callback", methods=["GET"])
def oauth_callback():
    """Spracuje návrat z Instagramu po ťuknutí na 'Povoliť' na mobile."""
    error = request.args.get("error")
    error_reason = request.args.get("error_reason")
    error_description = request.args.get("error_description")

    if error:
        logger.error(f"Instagram OAuth error: {error} - {error_description}")
        return render_template_string("""
            <!DOCTYPE html>
            <html lang="sk">
            <head>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <title>Chyba pripojenia</title>
              <style>
                body { background:#0b0f19; color:#f1f5f9; font-family:sans-serif; text-align:center; padding:40px 20px; }
                .card { background:#151b26; border:1px solid #ef4444; border-radius:18px; padding:30px; max-width:380px; margin:0 auto; }
                h2 { color:#ef4444; margin-top:0; }
                p { color:#94a3b8; font-size:14px; line-height:1.5; }
                a { display:inline-block; margin-top:20px; background:#334155; color:#fff; text-decoration:none; padding:10px 20px; border-radius:10px; font-weight:600; }
              </style>
            </head>
            <body>
              <div class="card">
                <h2>❌ Autorizácia zlyhala</h2>
                <p>{{ desc or error }}</p>
                <a href="/ig/">Späť do IG Trackera</a>
              </div>
            </body>
            </html>
        """, desc=error_description, error=error), 400

    code = request.args.get("code")
    raw_state = request.args.get("state", "")

    if not code:
        return "Chýba autorizačný kód.", 400

    # Očistenie kódu (Instagram na koniec niekedy pridáva '#_')
    if code.endswith("#_"):
        code = code[:-2]

    # Určenie, či ide o US alebo SK appku podľa state parametra
    region = "us" if raw_state.startswith("us") else "sk"
    account_id_str = ""
    if ":" in raw_state:
        _, account_id_str = raw_state.split(":", 1)
    elif raw_state.isdigit():
        account_id_str = raw_state

    active_app_id = US_META_APP_ID if region == "us" else META_APP_ID
    active_app_secret = US_META_APP_SECRET if region == "us" else META_APP_SECRET

    try:
        # 1. Výmena authorization_code za Access Token
        logger.info(f"OAuth callback: exchanging code for region={region}, client_id={active_app_id}, redirect_uri={META_REDIRECT_URI}")
        token_res = httpx.post(
            "https://api.instagram.com/oauth/access_token",
            data={
                "client_id": active_app_id,
                "client_secret": active_app_secret,
                "grant_type": "authorization_code",
                "redirect_uri": META_REDIRECT_URI,
                "code": code,
            },
            timeout=25,
        )
        token_data = token_res.json()
        logger.info(f"OAuth token response: status={token_res.status_code}, data={token_data}")

        if "error" in token_data or "access_token" not in token_data:
            err_msg = token_data.get("error_message") or token_data.get("error", {}).get("message", "Neznáma chyba pri výmene kódu")
            logger.error(f"Token exchange failed: {token_data}")
            return render_template_string("""
                <!DOCTYPE html>
                <html lang="sk">
                <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Chyba</title>
                <style>body{background:#0b0f19;color:#fff;font-family:sans-serif;text-align:center;padding:40px 20px;}</style></head>
                <body>
                    <h2 style="color:#ef4444;">❌ Chyba výmeny tokenu</h2>
                    <p style="color:#94a3b8;">{{ err_msg }}</p>
                    <p style="font-size:12px;color:#64748b;">Uistite sa, že účet je pridaný ako Instagram Tester v príslušnej Meta Appke ({{ app_label }}) a pozvánka bola prijatá.</p>
                    <a href="/ig/" style="color:#38bdf8;">Späť do IG Trackera</a>
                </body></html>
            """, err_msg=err_msg, app_label="US App" if region == "us" else "SK App"), 400

        short_token = token_data["access_token"]
        user_id = str(token_data.get("user_id", ""))

        # 2. Pokus o výmenu za Long-Lived Token (platnosť 60 dní)
        final_token = short_token
        try:
            long_res = httpx.get(
                "https://graph.instagram.com/access_token",
                params={
                    "grant_type": "ig_exchange_token",
                    "client_secret": active_app_secret,
                    "access_token": short_token,
                },
                timeout=15,
            )
            long_data = long_res.json()
            if "access_token" in long_data:
                final_token = long_data["access_token"]
        except Exception as e:
            logger.warning(f"Long-lived exchange warning: {e}")

        # 3. Zistenie údajov o profile
        username = ""
        try:
            prof = ig_api.get_profile(final_token)
            username = prof.get("username", "")
            if not user_id:
                user_id = str(prof.get("id", ""))
        except Exception as e:
            logger.warning(f"Could not fetch profile via final_token: {e}")

        # 4. Uloženie do databázy s označením regiónu (sk / us)
        account_id = int(account_id_str) if account_id_str.isdigit() else None
        target_account = None

        if account_id:
            target_account = db.get_account_by_id(account_id)
        if not target_account and username:
            target_account = db.get_account_by_username(username)

        if target_account:
            db.set_account_token(target_account["id"], final_token, user_id, region=region)
            saved_name = target_account["username"]
        elif username:
            matched_id = db.add_account(username, full_name=username, avatar_url="")
            db.set_account_token(matched_id, final_token, user_id, region=region)
            saved_name = username
        else:
            saved_name = user_id or "Neznámy"

        region_badge = "🇺🇸 US Profil (Oddelená US Appka)" if region == "us" else "🇸🇰 Slovenský profil"

        return render_template_string("""
            <!DOCTYPE html>
            <html lang="sk">
            <head>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <title>Instagram Úspešne Prepojený!</title>
              <style>
                body {
                  background: #0b0f19;
                  color: #f1f5f9;
                  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                  display: flex;
                  align-items: center;
                  justify-content: center;
                  min-height: 100vh;
                  margin: 0;
                  padding: 20px;
                  box-sizing: border-box;
                  text-align: center;
                }
                .card {
                  background: #151b26;
                  border: 1px solid rgba(16, 185, 129, 0.4);
                  border-radius: 24px;
                  padding: 34px 24px;
                  max-width: 380px;
                  box-shadow: 0 15px 40px rgba(0,0,0,0.6), 0 0 30px rgba(16, 185, 129, 0.15);
                }
                .icon { font-size: 54px; margin-bottom: 12px; }
                h2 { color: #10b981; margin: 0 0 10px 0; font-size: 22px; }
                p { color: #94a3b8; font-size: 14px; line-height: 1.5; margin: 0 0 22px 0; }
                .badge { display: inline-block; background: rgba(56, 189, 248, 0.15); color: #38bdf8; padding: 6px 16px; border-radius: 20px; font-weight: 700; font-size: 16px; margin-bottom: 8px; }
                .region-tag { display: block; font-size: 12px; color: #10b981; font-weight: 600; margin-bottom: 18px; }
                .btn { display: inline-block; background: #3b82f6; color: #fff; text-decoration: none; padding: 12px 24px; border-radius: 12px; font-weight: 600; font-size: 14px; transition: all 0.2s; }
                .btn:hover { background: #2563eb; }
              </style>
            </head>
            <body>
              <div class="card">
                <div class="icon">🎉</div>
                <h2>Instagram Úspešne Prepojený!</h2>
                <div class="badge">@{{ saved_name }}</div>
                <div class="region-tag">{{ region_badge }}</div>
                <p>Účet bol automaticky autorizovaný a nový 60-dňový token bol bezpečne uložený na serveri. Už môžeš toto okno zavrieť.</p>
                <a href="/ig/" class="btn">Prejsť do IG Trackera</a>
              </div>
            </body>
            </html>
        """, saved_name=saved_name, region_badge=region_badge)

    except Exception as e:
        logger.exception("OAuth processing error")
        return f"Vyskytla sa neočakávaná chyba: {e}", 500


# ─── IG Publisher & Insights Routes ────────────────────────────────────────────

IG_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
IG_USER_ID = os.environ.get("IG_USER_ID", "")


@app.route("/api/ig-publisher/profile", methods=["GET"])
@auth_required
def api_ig_profile():
    """Vráti profil a posledné médiá cez Graph API."""
    account_id = request.args.get("account_id", type=int)
    token = None
    if account_id:
        acc = db.get_account_by_id(account_id)
        if acc:
            token = acc.get("ig_access_token")

    if not token:
        token = os.environ.get("IG_ACCESS_TOKEN", IG_TOKEN)

    if not token:
        return jsonify({"status": "error", "message": "Access token nie je nastavený."}), 503
    try:
        profile = ig_api.get_profile(token)
        media = ig_api.get_media(token, limit=20)
        return jsonify({"status": "ok", "profile": profile, "media": media})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ig-publisher/insights", methods=["GET"])
@auth_required
def api_ig_insights():
    """Vráti account-level insights za posledných 30 dní."""
    account_id = request.args.get("account_id", type=int)
    token = None
    if account_id:
        acc = db.get_account_by_id(account_id)
        if acc:
            token = acc.get("ig_access_token")

    if not token:
        token = os.environ.get("IG_ACCESS_TOKEN", IG_TOKEN)

    if not token:
        return jsonify({"status": "error", "message": "Access token nie je nastavený."}), 503
    try:
        insights = ig_api.get_account_insights(token, days=30)
        return jsonify({"status": "ok", "insights": insights})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "mp4", "mov"}


@app.route("/api/ig-publisher/upload", methods=["POST"])
@auth_required
def api_ig_upload():
    """Upload lokálneho súboru z mobilu/PC a vygenerovanie verejnej HTTPS linky pre Meta API."""
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "Nebol vybraný žiadny súbor."}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"status": "error", "message": "Prázdny názov súboru."}), 400

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({"status": "error", "message": f"Nepodporovaný formát (povolené: {', '.join(ALLOWED_EXTENSIONS)})."}), 400

    safe_name = f"media_{int(time.time())}_{uuid.uuid4().hex[:8]}.{ext}"
    dest_path = os.path.join(UPLOAD_DIR, safe_name)
    file.save(dest_path)

    # Verejná URL adresa cez Nginx (pre Meta Graph API vyžadované https://)
    host = request.headers.get("X-Forwarded-Host") or request.host or "garcarzp.online"
    if "127.0.0.1" in host or "localhost" in host:
        host = "garcarzp.online"
    public_url = f"https://{host}/ig/static/uploads/{safe_name}"

    return jsonify({
        "status": "ok",
        "url": public_url,
        "filename": safe_name,
        "media_type": "VIDEO" if ext in {"mp4", "mov"} else "IMAGE"
    }), 201


@app.route("/api/ig-publisher/publish-photo", methods=["POST"])
@auth_required
def api_ig_publish_photo():
    """
    Publikuj foto na Instagram pre konkrétny účet.
    Body JSON: {image_url: str, caption: str, account_id?: int, vault_video_id?: int}
    image_url MUSÍ byť verejne dostupná HTTPS URL.
    """
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    vault_video_id = data.get("vault_video_id")

    token = None
    user_id = None
    target_username = None

    if account_id:
        acc = db.get_account_by_id(int(account_id))
        if acc:
            token = acc.get("ig_access_token")
            user_id = acc.get("ig_user_id")
            target_username = acc.get("username")
        if not token or not user_id:
            return jsonify({"status": "error", "message": f"Účet nemá priradený Meta Access Token. Prepojte ho v zozname profilov."}), 400
    else:
        token = os.environ.get("IG_ACCESS_TOKEN", IG_TOKEN)
        user_id = os.environ.get("IG_USER_ID", IG_USER_ID)

    if not token or not user_id:
        return jsonify({"status": "error", "message": "Nie je nastavený token alebo IG User ID."}), 400

    image_url = (data.get("image_url") or "").strip()
    caption = (data.get("caption") or "").strip()

    if not image_url or not image_url.startswith("https://"):
        return jsonify({"status": "error", "message": "Zadajte platnú verejnú HTTPS URL obrázka."}), 400

    try:
        result = ig_api.publish_photo(token, user_id, image_url, caption)
        if "error" in result:
            return jsonify({"status": "error", "message": result["error"]}), 400

        # Ak pochádza z Media Vaultu, automaticky označíme médium ako použité s tagom účtu
        if vault_video_id:
            try:
                db.mark_vault_video_used(int(vault_video_id), target_username)
            except Exception as e:
                logger.warning(f"Chyba pri označovaní vault média ako použité: {e}")

        return jsonify({"status": "ok", "message": "Foto úspešne zverejnené!", "post_id": result.get("id")}), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/ig-publisher/publish-reel", methods=["POST"])
@auth_required
def api_ig_publish_reel():
    """
    Publikuj Reel na Instagram pre konkrétny účet.
    Body JSON: {video_url: str, caption: str, cover_url: str (optional), account_id?: int, vault_video_id?: int}
    video_url MUSÍ byť verejne dostupná HTTPS MP4 URL.
    """
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id")
    vault_video_id = data.get("vault_video_id")

    token = None
    user_id = None
    target_username = None

    if account_id:
        acc = db.get_account_by_id(int(account_id))
        if acc:
            token = acc.get("ig_access_token")
            user_id = acc.get("ig_user_id")
            target_username = acc.get("username")
        if not token or not user_id:
            return jsonify({"status": "error", "message": f"Účet nemá priradený Meta Access Token. Prepojte ho v zozname profilov."}), 400
    else:
        token = os.environ.get("IG_ACCESS_TOKEN", IG_TOKEN)
        user_id = os.environ.get("IG_USER_ID", IG_USER_ID)

    if not token or not user_id:
        return jsonify({"status": "error", "message": "Nie je nastavený token alebo IG User ID."}), 400

    video_url = (data.get("video_url") or "").strip()
    caption = (data.get("caption") or "").strip()
    cover_url = (data.get("cover_url") or "").strip()
    share_to_feed = bool(data.get("share_to_feed", True))

    if not video_url or not video_url.startswith("https://"):
        return jsonify({"status": "error", "message": "Zadajte platnú verejnú HTTPS URL MP4 videa."}), 400

    try:
        result = ig_api.publish_reel(token, user_id, video_url, caption, cover_url, share_to_feed=share_to_feed)
        if "error" in result:
            return jsonify({"status": "error", "message": result["error"]}), 400

        # Ak pochádza z Media Vaultu, automaticky označíme médium ako použité s tagom účtu
        if vault_video_id:
            try:
                db.mark_vault_video_used(int(vault_video_id), target_username)
            except Exception as e:
                logger.warning(f"Chyba pri označovaní vault média ako použité: {e}")

        return jsonify({"status": "ok", "message": "Reel úspešne zverejnený!", "post_id": result.get("id")}), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/publisher", methods=["GET"])
@auth_required
def publisher_page():
    """IG Publisher & Insights stránka — podpora prepínania účtov so samostatnými tokenmi."""
    req_account_id = request.args.get("account_id", type=int)
    all_accounts = db.get_accounts_with_metrics()
    accounts_with_tokens = [a for a in all_accounts if a.get("has_token")]

    selected_account = None
    if req_account_id:
        for a in all_accounts:
            if a["id"] == req_account_id:
                selected_account = a
                break
    elif accounts_with_tokens:
        selected_account = accounts_with_tokens[0]

    token = None
    user_id = None

    if selected_account:
        account_obj = db.get_account_by_id(selected_account["id"])
        if account_obj:
            token = account_obj.get("ig_access_token")
            user_id = account_obj.get("ig_user_id")
    else:
        token = os.environ.get("IG_ACCESS_TOKEN", IG_TOKEN)
        user_id = os.environ.get("IG_USER_ID", IG_USER_ID)

    profile = {}
    media = []
    insights = {}
    error = None

    if not token:
        acc_name = f"@{selected_account['username']}" if selected_account else "Tento účet"
        error = f"{acc_name} zatiaľ nemá priradený Meta Access Token. Prepojte token v Trackeri pomocou tlačidla „Linknúť token“."
    else:
        try:
            profile = ig_api.get_profile(token)
            media = ig_api.get_media(token, limit=20)
        except Exception as e:
            error = f"Chyba pri načítaní profilu cez Graph API: {e}"
        try:
            insights = ig_api.get_account_insights(token, days=30)
        except Exception:
            pass  # insights sú voliteľné

    return render_template(
        "publisher.html",
        profile=profile,
        media=media,
        insights=insights,
        ig_user_id=user_id or (profile.get("id") if profile else ""),
        error=error,
        selected_account=selected_account,
        accounts_with_tokens=accounts_with_tokens,
        all_accounts=all_accounts,
        current_account_id=(selected_account["id"] if selected_account else (req_account_id or 0)),
        master_password=MASTER_PASSWORD,
    )


# ─── Media Vault Static File Serving ──────────────────────────────────────────

@app.route("/media/vault/<path:subpath>", methods=["GET"])
def serve_vault_media(subpath):
    """Verejný prístup pre Instagram Graph API a video player (podporuje byte-range requests)."""
    return send_from_directory(VAULT_DIR, subpath, conditional=True)


@app.route("/api/download/desktop-spoofer", methods=["GET"])
def download_desktop_spoofer():
    """Umožňuje stiahnuť desktop spoofer balík priamo z webu na akýkoľvek PC."""
    zip_path = os.path.join(BASE_DIR, "static", "desktop_spoofer.zip")
    spoofer_dir = os.path.join(BASE_DIR, "desktop_spoofer")
    main_script = os.path.join(spoofer_dir, "spoofer_desktop.py")
    need_rebuild = not os.path.exists(zip_path)
    if os.path.exists(zip_path) and os.path.exists(main_script):
        if os.path.getmtime(main_script) > os.path.getmtime(zip_path):
            need_rebuild = True
    if need_rebuild and os.path.exists(spoofer_dir):
        import shutil
        shutil.make_archive(os.path.join(BASE_DIR, "static", "desktop_spoofer"), 'zip', spoofer_dir)
    return send_from_directory(
        os.path.join(BASE_DIR, "static"),
        "desktop_spoofer.zip",
        as_attachment=True,
        download_name="IG_Desktop_Spoofer.zip"
    )


# ─── Account Health Monitor API ────────────────────────────────────────────────

@app.route("/api/ig-tracker/health-check", methods=["POST"])
@auth_required
def api_health_check():
    """Manuálny trigger okamžitého overenia zdravia účtov."""
    data = request.get_json(silent=True) or {}
    account_id = data.get("account_id") or request.args.get("account_id", type=int)

    if account_id:
        res = health_monitor.check_account_health(account_id)
        return jsonify({"status": "ok", "result": res}), 200

    results = health_monitor.check_all_accounts_health()
    healthy_cnt = sum(1 for r in results if r["new_status"] == "healthy")
    action_cnt = sum(1 for r in results if r["new_status"] == "action_required")
    error_cnt = sum(1 for r in results if r["new_status"] == "error")

    accounts = db.get_accounts_with_metrics()
    return jsonify({
        "status": "ok",
        "total": len(results),
        "healthy_count": healthy_cnt,
        "action_required_count": action_cnt,
        "error_count": error_cnt,
        "results": results,
        "accounts": accounts
    }), 200


@app.route("/api/ig-tracker/health", methods=["GET"])
@auth_required
def api_get_health():
    """Vráti aktuálny stav zdravia všetkých účtov."""
    accounts = db.get_accounts_with_metrics()
    healthy = [a for a in accounts if a.get("health_status") == "healthy"]
    action_req = [a for a in accounts if a.get("health_status") == "action_required"]
    errors = [a for a in accounts if a.get("health_status") in ("error", "banned")]
    return jsonify({
        "status": "ok",
        "total": len(accounts),
        "healthy": len(healthy),
        "action_required": len(action_req),
        "errors": len(errors),
        "accounts": accounts
    }), 200


@app.route("/api/ig-tracker/settings", methods=["GET", "POST"])
@auth_required
def api_settings():
    """Čítanie a ukladanie nastavení (Discord Webhook, Telegram, intervaly)."""
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form or {}
        for k, v in data.items():
            db.set_setting(k, str(v).strip())
        return jsonify({"status": "ok", "message": "Nastavenia boli úspešne uložené.", "settings": db.get_all_settings()}), 200

    return jsonify({"status": "ok", "settings": db.get_all_settings()}), 200


@app.route("/api/ig-tracker/settings/test-webhook", methods=["POST"])
@auth_required
def api_test_webhook():
    """Odošle testovací alert do nastaveného webhooku."""
    data = request.get_json(silent=True) or {}
    webhook_url = data.get("webhook_url")
    if webhook_url:
        db.set_setting("discord_webhook_url", webhook_url.strip())

    sample_account = {
        "id": 0,
        "username": "test_account",
        "region": "us"
    }
    notifier.send_alert(
        sample_account,
        old_status="healthy",
        new_status="action_required",
        message="Toto je testovacia notifikácia z IG Tracker Health Monitora.",
        details="Webhook spojenie bolo úspešne overené."
    )
    return jsonify({"status": "ok", "message": "Testovacia správa bola odoslaná do webhooku."}), 200


# ─── Media Vault API (Google Drive Powered) ───────────────────────────────────

@app.route("/api/vault/gdrive-status", methods=["GET"])
@auth_required
def api_vault_gdrive_status():
    """Vráti stav Google Drive úložiska pre Media Vault."""
    status = gdrive_vault.get_storage_status()
    return jsonify(status), 200


@app.route("/api/vault/sync-gdrive", methods=["POST"])
@auth_required
def api_vault_sync_gdrive():
    """Synchronizuje master videá priamo z priečinka IG_VAULT na Google Drive."""
    res = gdrive_vault.sync_drive_vault_to_db()
    return jsonify(res), 200


@app.route("/api/vault/stream/<int:video_id>", methods=["GET", "HEAD"])
@app.route("/api/vault/stream/<int:video_id>/<path:filename>", methods=["GET", "HEAD"])
def stream_vault_video(video_id, filename=None):
    """Streamovacia proxy pre Google Drive master video/foto s plnou podporou HTTP Range (206 Partial Content)."""
    video = db.get_vault_video_by_id(video_id)
    if not video:
        return "Médium nebolo nájdené", 404

    is_photo = (video.get("media_type") == "photo")
    ext = os.path.splitext(video.get("original_name") or video.get("filename") or "")[1].lower()
    if is_photo:
        default_mime = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"
    else:
        default_mime = "video/quicktime" if ext in (".mov", ".qt") else "video/mp4"

    if video.get("storage_type") == "gdrive" and video.get("gdrive_file_id"):
        creds = gdrive_vault.get_drive_credentials()
        if not creds:
            if video.get("gdrive_web_view_link"):
                return redirect(video["gdrive_web_view_link"])
            return "Google Drive nie je pripojený", 503

        import requests
        from google.auth.transport.requests import Request as GRequest

        drive_url = f"https://www.googleapis.com/drive/v3/files/{video['gdrive_file_id']}?alt=media"
        req_headers = {"Authorization": f"Bearer {creds.token}"}

        # Preposlanie Range hlavičky z prehliadača (kľúčové pre video prehrávanie v Chrome/Safari)
        range_header = request.headers.get("Range")
        if range_header:
            req_headers["Range"] = range_header

        try:
            drive_res = requests.get(drive_url, headers=req_headers, stream=True, timeout=30)
            if drive_res.status_code == 401:
                # Obnovenie tokenu v prípade expirácie
                creds.refresh(GRequest())
                req_headers["Authorization"] = f"Bearer {creds.token}"
                drive_res = requests.get(drive_url, headers=req_headers, stream=True, timeout=30)

            content_type = drive_res.headers.get("Content-Type") or default_mime

            # HEAD request (pre Meta Graph API validator / crawler)
            if request.method == "HEAD":
                resp = Response("", status=drive_res.status_code, mimetype=content_type)
                resp.headers["Accept-Ranges"] = "bytes"
                if "Content-Length" in drive_res.headers:
                    resp.headers["Content-Length"] = drive_res.headers["Content-Length"]
                if "Content-Range" in drive_res.headers:
                    resp.headers["Content-Range"] = drive_res.headers["Content-Range"]
                return resp

            def generate_stream():
                for chunk in drive_res.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        yield chunk

            resp = Response(stream_with_context(generate_stream()), status=drive_res.status_code, mimetype=content_type)
            resp.headers["Accept-Ranges"] = "bytes"
            if "Content-Length" in drive_res.headers:
                resp.headers["Content-Length"] = drive_res.headers["Content-Length"]
            if "Content-Range" in drive_res.headers:
                resp.headers["Content-Range"] = drive_res.headers["Content-Range"]
            return resp

        except Exception as e:
            logger.error(f"Chyba pri streamovaní z Drive: {e}")
            if video.get("gdrive_web_view_link"):
                return redirect(video["gdrive_web_view_link"])
            return f"Chyba streamu: {e}", 500
    else:
        return send_from_directory(VAULT_DIR, video.get("filename"), mimetype=default_mime, conditional=True)


@app.route("/api/vault/videos", methods=["GET"])
@auth_required
def api_vault_videos():
    """Vráti zoznam master videí a fotografií vo Vaulte (Google Drive aj lokálne)."""
    status_filter = request.args.get("status")
    media_filter = request.args.get("type")
    videos = db.get_all_vault_videos(status=status_filter)

    host = request.headers.get("X-Forwarded-Host") or request.host or "garcarzp.online"
    if "127.0.0.1" in host or "localhost" in host:
        host = "garcarzp.online"

    result = []
    for v in videos:
        m_type = v.get("media_type") or "video"
        if media_filter and m_type != media_filter:
            continue
        is_gdrive = (v.get("storage_type") == "gdrive")
        v["is_gdrive"] = is_gdrive
        v["media_type"] = m_type
        v["used_count"] = v.get("used_count") or 0
        v["used_by_accounts"] = v.get("used_by_accounts") or ""
        v["last_used_at"] = v.get("last_used_at")
        v["tag"] = v.get("tag") or ("Použité" if v["used_count"] > 0 else "Voľné")
        v["is_used"] = (v["used_count"] > 0) or (v.get("status") in ("used", "scheduled"))

        if is_gdrive:
            v["url"] = f"/ig/api/vault/stream/{v['id']}"
            v["public_stream_url"] = f"https://{host}/ig/api/vault/stream/{v['id']}"
            v["gdrive_link"] = v.get("gdrive_web_view_link")
        else:
            v["url"] = f"/ig/media/vault/{v['filename']}"
            v["public_stream_url"] = f"https://{host}/ig/media/vault/{v['filename']}"
            v["gdrive_link"] = None

        v["thumbnail_url"] = f"/ig/media/vault/thumbs/{v['thumbnail_path']}" if v.get("thumbnail_path") else None
        v["file_size_fmt"] = gdrive_vault.format_bytes(v.get("file_size", 0))
        result.append(v)

    return jsonify({"status": "ok", "count": len(result), "videos": result}), 200


@app.route("/api/vault/upload", methods=["POST"])
@auth_required
def api_vault_upload():
    """Hromadné alebo jednotlivé nahrávanie master Reels videí a fotografií do Google Drive Vaultu."""
    if "file" not in request.files and "video" not in request.files:
        return jsonify({"status": "error", "message": "Žiadny súbor nebol odoslaný."}), 400

    uploaded_files = request.files.getlist("file") or request.files.getlist("video")
    saved_records = []

    for f in uploaded_files:
        if not f or not f.filename:
            continue
        orig_name = f.filename
        ext = os.path.splitext(orig_name)[1].lower()
        if ext not in spoofer.ALL_MEDIA_EXT:
            continue

        is_photo = (ext in spoofer.IMAGE_EXT)
        media_type = "photo" if is_photo else "video"

        ts = int(time.time())
        rand_hex = uuid.uuid4().hex[:6]
        temp_upload_path = os.path.join(tempfile.gettempdir(), f"upload_{ts}_{rand_hex}{ext}")
        f.save(temp_upload_path)

        info = spoofer.probe_video_info(temp_upload_path)
        thumb_filename = f"thumb_{ts}_{rand_hex}.jpg"
        thumb_path = os.path.join(THUMBS_DIR, thumb_filename)
        has_thumb = spoofer.generate_thumbnail(temp_upload_path, thumb_path)

        # Určenie MIME typu
        if is_photo:
            mime_type = "image/png" if ext == ".png" else "image/webp" if ext == ".webp" else "image/jpeg"
        else:
            mime_type = "video/mp4" if ext == ".mp4" else "video/quicktime"

        # Upload na Google Drive s okamžitým zmazaním lokálneho temp súboru (0 MB záťaž VPS)
        try:
            drive_file = gdrive_vault.upload_file_to_drive(
                temp_upload_path,
                orig_name,
                mime_type=mime_type,
                delete_local=True
            )
            gdrive_id = drive_file["id"]
            gdrive_link = drive_file.get("webViewLink")
            storage_type = "gdrive"
            safe_filename = f"gdrive_{gdrive_id}"
        except Exception as e:
            logger.error(f"Zlyhal upload na Google Drive, fallback na lokálne: {e}")
            storage_type = "local"
            safe_filename = f"master_{ts}_{rand_hex}{ext}"
            local_vault_path = os.path.join(VAULT_DIR, safe_filename)
            if os.path.exists(temp_upload_path):
                import shutil
                shutil.move(temp_upload_path, local_vault_path)
            gdrive_id = None
            gdrive_link = None

        vid_id = db.add_vault_video(
            filename=safe_filename,
            original_name=orig_name,
            file_size=info.get("file_size", 0),
            duration_seconds=info.get("duration_seconds", 0.0),
            width=info.get("width", 0),
            height=info.get("height", 0),
            thumbnail_path=thumb_filename if has_thumb else None,
            storage_type=storage_type,
            gdrive_file_id=gdrive_id,
            gdrive_web_view_link=gdrive_link,
            media_type=media_type,
            tag='Voľné'
        )
        saved_records.append({
            "id": vid_id,
            "filename": safe_filename,
            "original_name": orig_name,
            "media_type": media_type,
            "duration": info.get("duration_seconds", 0.0),
            "size": info.get("file_size", 0),
            "storage": storage_type
        })

    return jsonify({
        "status": "ok",
        "message": f"Úspešne nahraných {len(saved_records)} médií do Google Drive Vaultu (0 MB záťaž disku na VPS).",
        "uploaded": saved_records
    }), 201


@app.route("/api/vault/videos/<int:video_id>/tag", methods=["POST"])
@auth_required
def api_vault_set_tag(video_id):
    """Manuálna úprava tagu média vo Vaulte."""
    data = request.get_json(silent=True) or request.form or {}
    new_tag = (data.get("tag") or "").strip()
    if not new_tag:
        return jsonify({"status": "error", "message": "Tag nesmie byť prázdny."}), 400
    db.update_vault_video_tag(video_id, new_tag)
    return jsonify({"status": "ok", "message": "Tag bol aktualizovaný.", "tag": new_tag}), 200


@app.route("/api/vault/videos/<int:video_id>", methods=["DELETE"])
@auth_required
def api_vault_delete(video_id):
    """Zmaže video z Vaultu, DB a Google Drive."""
    deleted = db.delete_vault_video(video_id)
    if deleted:
        if deleted.get("storage_type") == "gdrive" and deleted.get("gdrive_file_id"):
            try:
                gdrive_vault.delete_file_from_drive(deleted["gdrive_file_id"])
            except Exception as e:
                logger.warning(f"Chyba pri mazaní z Google Drive: {e}")
        else:
            fpath = os.path.join(VAULT_DIR, deleted.get("filename", ""))
            if os.path.exists(fpath):
                try: os.remove(fpath)
                except Exception: pass

        if deleted.get("thumbnail_path"):
            tpath = os.path.join(THUMBS_DIR, deleted["thumbnail_path"])
            if os.path.exists(tpath):
                try: os.remove(tpath)
                except Exception: pass

    return jsonify({"status": "ok", "message": "Video bolo zmazané z Vaultu."}), 200


@app.route("/api/spoofer/quick-spoof", methods=["POST"])
@auth_required
def api_quick_spoof():
    """
    Rychly manualny spoofing videa priamo cez webove rozhranie.
    Podporuje vyber z Vaultu (Google Drive / lokalne) aj priamy upload z PC.
    Aplikuje FFmpeg mikro-kontrast jitter + color grading (14 Mbps H.264, LUT, grain),
    EXIF smartphone fingerprint a GPS v LA/Vegas.
    """
    video_id   = request.form.get("video_id", type=int)
    region     = (request.form.get("region") or "us").lower()
    account_id = request.form.get("account_id", type=int)
    do_grade   = request.form.get("color_grade", "true").lower() not in ("false", "0", "no")
    grain      = min(20, max(1, int(request.form.get("grain") or 9)))
    lut_name   = (request.form.get("lut") or "").strip()
    lut_path   = None
    if lut_name:
        lut_path = os.path.join(BASE_DIR, "data", "luts", os.path.basename(lut_name))
        if not os.path.isfile(lut_path):
            lut_path = None

    if account_id:
        acc = db.get_account_by_id(account_id)
        if acc and acc.get("region"):
            region = acc["region"].lower()

    ts = int(time.time())
    rand_hex = uuid.uuid4().hex[:6]
    out_filename = f"quick_spoof_{region}_{ts}_{rand_hex}.mp4"
    out_path = os.path.join(SPOOFED_DIR, out_filename)
    thumb_filename = f"thumb_{os.path.splitext(out_filename)[0]}.jpg"
    thumb_path = os.path.join(THUMBS_DIR, thumb_filename)

    meta = {}
    orig_name = "video.mp4"

    try:
        # A) Z Vaultu
        if video_id:
            video = db.get_vault_video_by_id(video_id)
            if not video:
                return jsonify({"status": "error", "message": "Video vo Vaulte nebolo najdene."}), 404
            orig_name = video.get("original_name") or "vault_video.mp4"
            ext = os.path.splitext(orig_name)[1].lower() or ".mp4"

            if video.get("storage_type") == "gdrive" and video.get("gdrive_file_id"):
                with gdrive_vault.temporary_master(video["gdrive_file_id"], ext=ext) as temp_master_path:
                    meta = spoofer.spoof_video_for_account(
                        temp_master_path, out_path, region=region,
                        color_grade=do_grade, grain=grain, lut_path=lut_path
                    )
                    spoofer.generate_thumbnail(out_path, thumb_path)
            else:
                local_src = os.path.join(VAULT_DIR, video["filename"])
                if not os.path.exists(local_src):
                    return jsonify({"status": "error", "message": "Lokalny master subor neexistuje."}), 404
                meta = spoofer.spoof_video_for_account(
                    local_src, out_path, region=region,
                    color_grade=do_grade, grain=grain, lut_path=lut_path
                )
                spoofer.generate_thumbnail(out_path, thumb_path)

        # B) Z priameho uploadu suboru
        elif "file" in request.files and request.files["file"].filename:
            f = request.files["file"]
            orig_name = f.filename
            ext = os.path.splitext(orig_name)[1].lower() or ".mp4"
            temp_src = os.path.join(tempfile.gettempdir(), f"src_quick_{ts}_{rand_hex}{ext}")
            f.save(temp_src)
            try:
                meta = spoofer.spoof_video_for_account(
                    temp_src, out_path, region=region,
                    color_grade=do_grade, grain=grain, lut_path=lut_path
                )
                spoofer.generate_thumbnail(out_path, thumb_path)
            finally:
                if os.path.exists(temp_src):
                    try: os.remove(temp_src)
                    except Exception: pass
        else:
            return jsonify({"status": "error", "message": "Vyberte video z Vaultu alebo nahrajte subor z PC."}), 400

    except Exception as e:
        logger.exception(f"Chyba pri rychlom spoofovani: {e}")
        return jsonify({"status": "error", "message": f"Chyba pri spoofovani: {str(e)}"}), 500

    host = request.headers.get("X-Forwarded-Host") or request.host or "garcarzp.online"
    if "127.0.0.1" in host or "localhost" in host:
        host = "garcarzp.online"

    video_url    = f"/ig/media/vault/spoofed/{out_filename}"
    public_url   = f"https://{host}/ig/media/vault/spoofed/{out_filename}"
    thumb_url    = f"/ig/media/vault/thumbs/{thumb_filename}"
    download_url = f"/ig/api/spoofer/download/{out_filename}"

    return jsonify({
        "status":         "ok",
        "message":        f"Video spoofnute ({meta.get('device', 'Smartfon')}, GPS: {meta.get('city', region.upper())})!",
        "filename":       out_filename,
        "original_name":  orig_name,
        "video_url":      video_url,
        "public_url":     public_url,
        "thumbnail_url":  thumb_url,
        "download_url":   download_url,
        "vault_video_id": video_id,
        "meta":           meta,
        "color_grade":    do_grade,
        "grain":          grain,
        "lut":            lut_name or None,
    }), 200


@app.route("/api/spoofer/download/<filename>", methods=["GET"])
def download_spoofed_video(filename):
    """Priame stiahnutie naspoofovaneho MP4 videa do PC."""
    safe_name = os.path.basename(filename)
    return send_from_directory(SPOOFED_DIR, safe_name, as_attachment=True, download_name=safe_name)


@app.route("/api/spoofer/download-reel", methods=["POST"])
@auth_required
def api_download_reel():
    """
    Stiahne Reel / video z URL pomocou yt-dlp a volitelne ho spoofuje.
    Vstup JSON: { "url": "...", "spoof": true, "save_to_vault": false }
    """
    data         = request.get_json(silent=True) or request.form or {}
    url          = (data.get("url") or "").strip()
    do_spoof     = data.get("spoof", True)
    save_vault   = data.get("save_to_vault", False)
    do_grade     = data.get("color_grade", True)
    grain        = min(20, max(1, int(data.get("grain") or 9)))
    lut_name     = (data.get("lut") or "").strip()
    lut_path     = None
    if lut_name:
        candidate = os.path.join(BASE_DIR, "data", "luts", os.path.basename(lut_name))
        if os.path.isfile(candidate):
            lut_path = candidate

    if not url or not url.startswith("http"):
        return jsonify({"status": "error", "message": "Zadajte platny URL odkaz."}), 400

    dl_dir = os.path.join(SPOOFED_DIR, "downloads")
    os.makedirs(dl_dir, exist_ok=True)

    cookies_path = os.path.join(BASE_DIR, "data", "cookies.txt")
    if not os.path.isfile(cookies_path):
        cookies_path = None

    dl_path = spoofer.download_reel(url, dl_dir, cookies_path=cookies_path)
    if not dl_path:
        return jsonify({"status": "error", "message": "Stiahnutie zlyhalo. Skontrolujte URL alebo ci je yt-dlp nainstalovane."}), 500

    result_path = dl_path
    meta = {}

    if do_spoof:
        ts = int(time.time())
        tok = uuid.uuid4().hex[:6]
        out_name = f"reel_spoof_{ts}_{tok}.mp4"
        out_path = os.path.join(SPOOFED_DIR, out_name)
        try:
            meta = spoofer.spoof_video_for_account(
                dl_path, out_path, region="us",
                color_grade=do_grade, grain=grain, lut_path=lut_path
            )
            result_path = out_path
            # Vymaz stiahnuty original po uspesnom spoofovani
            try: os.remove(dl_path)
            except Exception: pass
        except Exception as e:
            logger.error(f"Spoof po download-reel zlyhal: {e}")
            # Pokracujeme s nespoofovanym suborom

    out_filename = os.path.basename(result_path)
    thumb_filename = f"thumb_{os.path.splitext(out_filename)[0]}.jpg"
    thumb_path = os.path.join(THUMBS_DIR, thumb_filename)
    spoofer.generate_thumbnail(result_path, thumb_path)

    vault_id = None
    if save_vault:
        try:
            vault_id = db.add_vault_video(
                filename=out_filename,
                original_name=os.path.basename(url)[:100],
                storage_type="local",
                file_size=os.path.getsize(result_path),
                region="us",
                tags="downloaded",
            )
        except Exception as e:
            logger.warning(f"Ulozenie do Vaultu zlyhalo: {e}")

    host = request.headers.get("X-Forwarded-Host") or request.host or "garcarzp.online"
    if "127.0.0.1" in host or "localhost" in host:
        host = "garcarzp.online"

    return jsonify({
        "status":       "ok",
        "message":      f"Reel stiahnuty a spoofovany! ({meta.get('device', 'N/A')} | GPS: {meta.get('city', 'N/A')})",
        "filename":     out_filename,
        "video_url":    f"/ig/media/vault/spoofed/{out_filename}",
        "public_url":   f"https://{host}/ig/media/vault/spoofed/{out_filename}",
        "thumbnail_url":f"/ig/media/vault/thumbs/{thumb_filename}",
        "download_url": f"/ig/api/spoofer/download/{out_filename}",
        "vault_id":     vault_id,
        "meta":         meta,
    }), 200


@app.route("/api/spoofer/luts", methods=["GET"])
@auth_required
def api_spoofer_luts():
    """Vrati zoznam dostupnych .cube LUT suborov z data/luts/."""
    luts_dir = os.path.join(BASE_DIR, "data", "luts")
    os.makedirs(luts_dir, exist_ok=True)
    luts = sorted([
        f for f in os.listdir(luts_dir)
        if f.lower().endswith(".cube")
    ])
    return jsonify({"status": "ok", "luts": luts}), 200


# ─── Auto-Planner & Review Studio API ──────────────────────────────────────────

@app.route("/api/planner/posts", methods=["GET"])
@auth_required
def api_planner_posts():
    """Zoznam naplánovaných postov pre daný deň alebo účet."""
    date_str = request.args.get("date")
    account_id = request.args.get("account_id", type=int)
    status = request.args.get("status")

    posts = db.get_planned_posts(date_str=date_str, account_id=account_id, status=status)
    for p in posts:
        if p.get("vault_video_id"):
            p["video_url"] = f"/ig/api/vault/stream/{p['vault_video_id']}/reel.mp4"
            p["thumbnail_url"] = f"/ig/media/vault/thumbs/{p['thumbnail_path']}" if p.get("thumbnail_path") else None
        else:
            p["video_url"] = f"/ig/media/vault/spoofed/{p['spoofed_video_path']}"
            p["thumbnail_url"] = f"/ig/media/vault/thumbs/{p['thumbnail_path']}" if p.get("thumbnail_path") else None

    all_upcoming = db.get_planned_posts()
    return jsonify({
        "status": "ok",
        "count": len(posts),
        "total_upcoming": len(all_upcoming),
        "posts": posts
    }), 200


@app.route("/api/planner/generate", methods=["POST"])
@auth_required
def api_planner_generate():
    """Spustí Auto-Planner engine a vygeneruje denný rozvrh so spoofingom."""
    data = request.get_json(silent=True) or request.form or {}
    target_date = data.get("target_date")
    posts_per_acc = int(data.get("posts_per_account") or 1)
    account_ids = data.get("account_ids")
    caption = data.get("caption") or ""
    hashtags = data.get("hashtags") or ""

    res = vault_planner.generate_auto_plan(
        target_date_str=target_date,
        posts_per_account=posts_per_acc,
        account_ids=account_ids,
        default_caption=caption,
        default_hashtags=hashtags,
        reuse_videos=True
    )
    code = 200 if res.get("status") == "ok" else 400
    return jsonify(res), code


@app.route("/api/planner/bulk-upload", methods=["POST"])
@auth_required
def api_planner_bulk_upload():
    """
    Hromadný upload sady hotových spoofnutých Reels pre jeden konkrétny účet.
    Uloží videá a automaticky ich naplánuje cez schedule_account_reel_set.
    """
    account_id = request.form.get("account_id", type=int)
    if not account_id:
        return jsonify({"status": "error", "message": "Chýba account_id."}), 400

    account = db.get_account_by_id(account_id)
    if not account:
        return jsonify({"status": "error", "message": "Účet nebol nájdený."}), 404

    username = account.get("username", "account")
    start_date = request.form.get("start_date")
    frequency = request.form.get("frequency") or "1_evening"
    caption = request.form.get("caption") or ""
    hashtags = request.form.get("hashtags") or ""

    uploaded_files = request.files.getlist("files") or request.files.getlist("files[]")
    if not uploaded_files:
        return jsonify({"status": "error", "message": "Neboli nahrané žiadne video súbory."}), 400

    saved_filenames = []
    for f in uploaded_files:
        if not f or not f.filename:
            continue
        orig_name = secure_filename(f.filename) or "reel.mp4"
        _, ext = os.path.splitext(orig_name)
        if ext.lower() not in (".mp4", ".mov", ".m4v", ".webm"):
            continue

        rand_token = uuid.uuid4().hex[:6]
        save_name = f"spoofed_{username}_{int(time.time())}_{rand_token}.mp4"
        dest_path = os.path.join(SPOOFED_DIR, save_name)
        f.save(dest_path)
        saved_filenames.append(save_name)

    if not saved_filenames:
        return jsonify({"status": "error", "message": "Žiadne platné MP4/MOV video súbory neboli nájdené."}), 400

    res = vault_planner.schedule_account_reel_set(
        account_id=account_id,
        saved_video_files=saved_filenames,
        start_date_str=start_date,
        frequency=frequency,
        default_caption=caption,
        default_hashtags=hashtags
    )
    code = 200 if res.get("status") == "ok" else 400
    return jsonify(res), code


@app.route("/api/planner/gdrive-summary", methods=["GET"])
@auth_required
def api_planner_gdrive_summary():
    """Vráti stav Google Drive IG_VAULT a počet dostupných/nepoužitých videí."""
    connected = gdrive_vault.is_connected()
    if not connected:
        return jsonify({
            "status": "ok",
            "connected": False,
            "message": "Google Drive nie je pripojený."
        }), 200

    account_id = request.args.get("account_id", type=int)
    target_user = ""
    if account_id:
        acc = db.get_account_by_id(account_id)
        if acc:
            target_user = f"@{acc.get('username', '').lstrip('@')}"

    # Rýchla synchronizácia
    try:
        gdrive_vault.sync_drive_vault_to_db(quick=True)
    except Exception as e:
        logger.warning(f"Sync error: {e}")

    videos = [v for v in db.get_all_vault_videos() if v.get("storage_type") == "gdrive"]
    total_count = len(videos)

    if target_user:
        unused_count = sum(1 for v in videos if target_user not in (v.get("used_by_accounts") or ""))
    else:
        unused_count = sum(1 for v in videos if (v.get("used_count") or 0) == 0)

    sample_videos = []
    for v in videos[:20]:
        sample_videos.append({
            "id": v["id"],
            "name": v.get("original_name") or v.get("filename"),
            "used_count": v.get("used_count", 0),
            "used_by": v.get("used_by_accounts", ""),
            "size_fmt": gdrive_vault.format_bytes(v.get("file_size", 0))
        })

    folders = gdrive_vault.get_vault_folders_summary(account_id=account_id)

    return jsonify({
        "status": "ok",
        "connected": True,
        "total_count": total_count,
        "unused_count": unused_count,
        "target_user": target_user,
        "sample_videos": sample_videos,
        "folders": folders
    }), 200


@app.route("/api/planner/gdrive-schedule", methods=["POST"])
@auth_required
def api_planner_gdrive_schedule():
    """Naplánuje sadu Reels priamo z Google Drive priečinka IG_VAULT."""
    data = request.get_json(silent=True) or request.form or {}
    account_id = data.get("account_id")
    try:
        account_id = int(account_id)
    except (ValueError, TypeError):
        return jsonify({"status": "error", "message": "Chýba platné account_id."}), 400

    count = data.get("count")
    try:
        count = int(count) if count else None
    except (ValueError, TypeError):
        count = None

    start_date = data.get("start_date")
    frequency = data.get("frequency") or "1_evening"
    randomize = str(data.get("randomize", "true")).lower() in ("true", "1", "yes")
    only_unused = str(data.get("only_unused", "true")).lower() in ("true", "1", "yes")
    folder_name = data.get("folder_name") or ""
    caption = data.get("caption") or ""
    hashtags = data.get("hashtags") or ""
    selected_ids = data.get("selected_ids") or []

    res = vault_planner.schedule_gdrive_reel_set(
        account_id=account_id,
        count=count,
        start_date_str=start_date,
        frequency=frequency,
        randomize=randomize,
        only_unused=only_unused,
        default_caption=caption,
        default_hashtags=hashtags,
        selected_video_ids=selected_ids,
        folder_name=folder_name
    )
    code = 200 if res.get("status") == "ok" else 400
    return jsonify(res), code


@app.route("/api/planner/posts/<int:post_id>", methods=["PUT", "DELETE"])
@auth_required
def api_planner_post_detail(post_id):
    """Úprava caption/hashtags alebo zmazanie naplánovaného slotu."""
    if request.method == "DELETE":
        deleted = db.delete_planned_post(post_id)
        if deleted and deleted.get("spoofed_video_path"):
            vpath = os.path.join(SPOOFED_DIR, deleted["spoofed_video_path"])
            if os.path.exists(vpath):
                try: os.remove(vpath)
                except Exception: pass
        return jsonify({"status": "ok", "message": "Slot bol zmazaný."}), 200

    data = request.get_json(silent=True) or request.form or {}
    db.update_planned_post(
        post_id=post_id,
        caption=data.get("caption"),
        hashtags=data.get("hashtags"),
        first_comment=data.get("first_comment"),
        scheduled_time=data.get("scheduled_time"),
        status=data.get("status")
    )
    post = db.get_planned_post_by_id(post_id)
    return jsonify({"status": "ok", "message": "Slot bol aktualizovaný.", "post": post}), 200


@app.route("/api/planner/posts/<int:post_id>/publish", methods=["POST"])
@auth_required
def api_planner_publish_now(post_id):
    """Okamžité manuálne publikovanie naplánovaného slotu na Instagram."""
    base_url = os.environ.get("BASE_PUBLIC_URL", "https://garcarzp.online/ig")
    res = vault_planner.publish_planned_post(post_id, base_public_url=base_url)
    code = 200 if res.get("status") == "ok" else 400
    return jsonify(res), code


# ─── Periodický Background Worker ──────────────────────────────────────────────

def background_sync_worker():
    """Spúšťa automatický sync každých 12 hodín pre všetky účty."""
    while True:
        time.sleep(12 * 3600)
        try:
            print("[IGTracker Worker] Spúšťam pravidelný 12h sync účtov...")
            accounts = db.get_all_accounts()
            if accounts:
                usernames = [a["username"] for a in accounts]
                batch_data = scraper.fetch_profiles_batch(usernames)
                for acc in accounts:
                    uname = acc["username"].lower()
                    scraped = batch_data.get(uname)
                    if scraped:
                        db.add_account(
                            username=uname,
                            full_name=scraped.get("full_name", uname),
                            avatar_url=scraped.get("avatar_url", "")
                        )
                        db.add_snapshot(
                            account_id=acc["id"],
                            followers=scraped.get("followers", 0),
                            following=scraped.get("following", 0),
                            posts_count=scraped.get("posts_count", 0),
                            top_reel_url=scraped.get("top_reel_url"),
                            top_reel_views=scraped.get("top_reel_views", 0),
                            top_reel_likes=scraped.get("top_reel_likes", 0),
                            total_views=scraped.get("total_views", 0),
                            avg_views=scraped.get("avg_views", 0),
                            engagement_rate=scraped.get("engagement_rate", 0.0),
                            last_post_date=scraped.get("last_post_date"),
                            last_post_views=scraped.get("last_post_views", 0),
                            last_post_url=scraped.get("last_post_url"),
                            last_post_likes=scraped.get("last_post_likes", 0),
                            usa_audience_pct=scraped.get("usa_audience_pct")
                        )
        except Exception as e:
            print(f"[IGTracker Worker] Všeobecná chyba workeru: {e}")


# Spustenie background workerov vo vedľajších vláknach
worker_thread = threading.Thread(target=background_sync_worker, daemon=True)
worker_thread.start()
health_monitor.start_background_health_worker(interval_seconds=7200)
vault_planner.start_background_planner_worker(interval_seconds=60)


if __name__ == "__main__":
    port = int(os.environ.get("IG_PORT", 5080))
    host = os.environ.get("IG_HOST", "0.0.0.0")
    debug = os.environ.get("IG_DEBUG") == "1"
    print("=" * 55)
    print("  📸 IG Analytics Tracker – Instagram Stats & Top Reels")
    print(f"  Lokálna URL:  http://127.0.0.1:{port}")
    print(f"  Predvolené heslo: {MASTER_PASSWORD}")
    print("=" * 55)
    app.run(host=host, port=port, debug=debug)
