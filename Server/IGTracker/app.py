import os
import logging
from functools import wraps
from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
from werkzeug.middleware.proxy_fix import ProxyFix

import db
import scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("IGTracker")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_PASSWORD = os.environ.get("IG_TRACKER_PASSWORD", "patrik3924")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ig-tracker-secret-key-patrik3924")

# ProxyFix pre beh za Nginx reverzným proxy pod prefixom /ig
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Inicializácia databázy
db.init_db()


def is_authenticated():
    return session.get("authenticated") is True


def auth_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        auth_header = request.headers.get("X-Master-Password")
        auth_query = request.args.get("pwd") or request.args.get("token") or request.args.get("password")
        if is_authenticated() or auth_header == MASTER_PASSWORD or auth_query == MASTER_PASSWORD:
            return f(*a, **kw)
        if request.path.startswith("/api/"):
            return jsonify({"status": "error", "message": "Neautorizovaný prístup. Vyžaduje sa heslo."}), 401
        return redirect(url_for("index"))
    return wrapper


# ─── Hlavná stránka & Autentifikácia ──────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    if not is_authenticated():
        return render_template("login.html")
    accounts = db.get_accounts_with_metrics()
    total_followers = sum(a["followers"] for a in accounts if a.get("has_data"))
    total_views = sum(a["total_views"] for a in accounts if a.get("has_data"))
    top_farm_reel, latest_farm_reel = db.get_farm_reels_summary(accounts)
    comparison = db.get_comparison_data()

    return render_template(
        "index.html",
        accounts=accounts,
        total_followers_fmt=db.format_number(total_followers),
        total_views_fmt=db.format_number(total_views),
        top_farm_reel=top_farm_reel,
        latest_farm_reel=latest_farm_reel,
        comparison=comparison
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


# ─── REST API: IG Tracker ─────────────────────────────────────────────────────

@app.route("/api/ig-tracker", methods=["GET"])
@auth_required
def api_get_tracker():
    """Vráti zoznam sledovaných profilov, ich metriky, delty a TOP reels."""
    accounts = db.get_accounts_with_metrics()
    total_followers = sum(a["followers"] for a in accounts if a.get("has_data"))
    total_views = sum(a["total_views"] for a in accounts if a.get("has_data"))
    top_farm_reel, latest_farm_reel = db.get_farm_reels_summary(accounts)

    return jsonify({
        "status": "ok",
        "count": len(accounts),
        "total_followers": total_followers,
        "total_followers_fmt": db.format_number(total_followers),
        "total_views": total_views,
        "total_views_fmt": db.format_number(total_views),
        "top_farm_reel": top_farm_reel,
        "latest_farm_reel": latest_farm_reel,
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
        db.add_account(
            username=username,
            full_name=scraped.get("full_name", username),
            avatar_url=scraped.get("avatar_url", "")
        )
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
        logger.error(f"Chyba pri scrapovaní nového profilu @{username}: {e}")

    accounts = db.get_accounts_with_metrics()
    return jsonify({
        "status": "ok",
        "message": f"Účet @{username} bol úspešne pridaný.",
        "accounts": accounts
    }), 201


@app.route("/api/ig-tracker/<int:account_id>", methods=["DELETE"])
@auth_required
def api_delete_account(account_id):
    """Zmaže účet a jeho históriu zo sledovania."""
    db.delete_account(account_id)
    accounts = db.get_accounts_with_metrics()
    return jsonify({
        "status": "ok",
        "message": "Účet bol odstránený zo sledovania.",
        "accounts": accounts
    }), 200


@app.route("/api/ig-tracker/sync", methods=["POST"])
@auth_required
def api_sync():
    """
    Manuálny force-refresh všetkých sledovaných účtov naraz v jednom Apify batchi.
    Spúšťa sa výhradne manuálne na kliknutie používateľa cez Sync tlačidlo.
    """
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
                logger.error(f"Chyba pri ukladaní snapshote pre @{uname}: {e}")

    updated_accounts = db.get_accounts_with_metrics()
    return jsonify({
        "status": "ok",
        "message": f"Úspešne synchronizovaných {synced_count} z {len(accounts)} účtov.",
        "accounts": updated_accounts
    }), 200


@app.route("/api/ig-tracker/<int:account_id>/history", methods=["GET"])
@auth_required
def api_account_history(account_id):
    """Vráti históriu snapshotov profilu pre grafy vývoja (followers, views)."""
    limit = request.args.get("limit", default=30, type=int)
    snapshots = db.get_account_snapshots(account_id, limit=limit)
    account = db.get_account_by_id(account_id)
    return jsonify({
        "status": "ok",
        "account": account,
        "snapshots": snapshots
    }), 200


@app.route("/api/ig-tracker/compare", methods=["GET"])
@auth_required
def api_compare():
    """Vráti usporiadané rebríčky pre porovnávanie progressu účtov."""
    comparison = db.get_comparison_data()
    return jsonify({
        "status": "ok",
        "comparison": comparison
    }), 200


@app.route("/api/ig-tracker/<int:account_id>/audience", methods=["POST"])
@auth_required
def api_update_account_audience(account_id):
    """Aktualizuje manuálny odhad podielu USA publika pre daný účet."""
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


# ─── Spustenie Aplikácie ───────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("IG_PORT", 5080))
    host = os.environ.get("IG_HOST", "0.0.0.0")
    print(f"🚀 Spúšťam IG Analytics Tracker na http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
