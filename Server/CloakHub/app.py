import os
import sys
from datetime import timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from werkzeug.middleware.proxy_fix import ProxyFix

import db
import engine
import domain_mgr

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_PASSWORD = os.environ.get("CLOAK_PASSWORD", "patrik3924")

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "cloakhub-secret-key-patrik3924")
app.permanent_session_lifetime = timedelta(days=30)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Inicializácia databázy
db.init_db()


def is_authenticated():
    return session.get("authenticated") is True


def auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        master_header = request.headers.get("X-Master-Password")
        if is_authenticated() or (master_header and master_header == MASTER_PASSWORD):
            return f(*args, **kwargs)

        if request.path.startswith("/api/admin"):
            return jsonify({"status": "error", "message": "Neautorizovaný prístup. Vyžaduje sa heslo."}), 401

        prefix_api = request.headers.get("X-Forwarded-Prefix", "")
        return render_template("login.html", prefix_api=prefix_api)
    return decorated_function


def get_request_headers_dict():
    return {k: v for k, v in request.headers.items()}


def get_client_ip():
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    return request.remote_addr or "127.0.0.1"


# ─── Verejná Bio Stránka s Cloakingom ──────────────────────────────────────────

@app.route("/", methods=["GET"])
@app.route("/<slug>", methods=["GET"])
def bio_page(slug="clara"):
    # Ignorovať interné routy
    if slug in ["admin", "api", "l", "static", "login", "logout"]:
        return redirect(url_for("admin_dashboard"))

    host = request.host.split(":")[0].lower()
    is_custom_domain = host not in ["garcarzp.online", "www.garcarzp.online", "127.0.0.1", "localhost", "35.209.172.238"]

    profile = None
    if is_custom_domain:
        profile = db.get_profile_by_domain(host)

    if not profile and slug:
        profile = db.get_profile(slug)
    if not profile:
        profile = db.get_profile("clara")
    if not profile:
        return "Profil nenájdený.", 404

    ua = request.headers.get("User-Agent", "")
    ip = get_client_ip()
    ip_h = engine.hash_ip(ip)
    headers = get_request_headers_dict()
    referrer = request.referrer or ""

    # 1. Kontrola, či ide o robota (Meta / TikTok / Googlebot crawler)
    bot_detected, bot_reason = engine.is_bot(ua, headers)
    device_type = engine.detect_device(ua)

    if bot_detected:
        db.log_event(
            profile_id=profile["id"],
            event_type="bot_blocked",
            ip_hash=ip_h,
            user_agent=ua,
            device_type="bot",
            referrer=referrer,
            bot_reason=bot_reason
        )
    else:
        db.log_event(
            profile_id=profile["id"],
            event_type="visit",
            ip_hash=ip_h,
            user_agent=ua,
            device_type=device_type,
            referrer=referrer
        )

    # Bezpečné sociálne odkazy (vždy prítomné pre botov)
    safe_links = db.get_safe_links(profile["id"])

    # Generovanie Proof-of-Work výzvy
    challenge = engine.generate_pow_challenge()

    # Nginx prefix pre volania (pre vlastnú doménu je root prázdny, inak /cloak)
    prefix_api = "" if is_custom_domain else request.headers.get("X-Forwarded-Prefix", "")

    return render_template(
        "bio.html",
        profile=profile,
        safe_links=safe_links,
        challenge=challenge,
        prefix_api=prefix_api
    )


# ─── API: Odomknutie Cloaked Odkazov po vyriešení PoW ──────────────────────────

@app.route("/api/links", methods=["POST"])
def api_unlock_links():
    """
    Overí klientsky Proof-of-Work a User-Agent.
    Ak je všetko v poriadku, vygeneruje HTML skutočných prémiových kariet.
    """
    data = request.get_json(silent=True) or {}
    challenge = (data.get("c") or "").strip()
    nonce = str(data.get("a") or "").strip()
    slug = (data.get("slug") or "clara").strip()

    ua = request.headers.get("User-Agent", "")
    headers = get_request_headers_dict()
    ip = get_client_ip()
    ip_h = engine.hash_ip(ip)

    # 1. Kontrola bota
    bot_detected, bot_reason = engine.is_bot(ua, headers)
    if bot_detected:
        db.log_event(event_type="bot_blocked", ip_hash=ip_h, user_agent=ua, device_type="bot", bot_reason=f"api_{bot_reason}")
        return jsonify({"status": "error", "message": "Security check failed"}), 403

    # 2. Kontrola Proof-of-Work
    if not engine.verify_pow(challenge, nonce):
        db.log_event(event_type="bot_blocked", ip_hash=ip_h, user_agent=ua, bot_reason="invalid_pow")
        return jsonify({"status": "error", "message": "PoW validation failed"}), 403

    # 3. Načítať skutočné prémiové odkazy
    host = request.host.split(":")[0].lower()
    is_custom_domain = host not in ["garcarzp.online", "www.garcarzp.online", "127.0.0.1", "localhost", "35.209.172.238"]

    profile = None
    if is_custom_domain:
        profile = db.get_profile_by_domain(host)
    if not profile:
        profile = db.get_profile(slug) or db.get_profile("clara")
    if not profile:
        return jsonify({"status": "error", "message": "Profile not found"}), 404

    cloaked_links = db.get_cloaked_links(profile["id"], only_active=True)

    prefix_api = "" if is_custom_domain else request.headers.get("X-Forwarded-Prefix", "")

    # Zostavenie prémiového HTML pre `#linksWrap`
    html_cards = []
    for l in cloaked_links:
        redirect_url = f"{prefix_api}/l/{l['slug']}"
        adult_attr = '1' if l.get("is_adult") else '0'
        photo_url = l.get("photo_url") or ""

        badge_html = f'<span class="badge"><i class="fas fa-{l.get("badge_icon") or "lock"}"></i></span>'
        if photo_url:
            card_html = f"""
            <a class="card" href="{redirect_url}" data-cloaked="1" data-adult="{adult_attr}">
              <img src="{photo_url}" class="ph" alt="{l['title']}" loading="lazy">
              {badge_html}
              <span class="cap">{l['title']}</span>
            </a>
            """
        else:
            card_html = f"""
            <a class="card plain" href="{redirect_url}" data-cloaked="1" data-adult="{adult_attr}">
              {badge_html}
              <span class="cap">{l['title']}</span>
            </a>
            """
        html_cards.append(card_html)

    # Pridať aj bezpečné sociálne ikony na koniec
    safe_links = db.get_safe_links(profile["id"])
    for s in safe_links:
        icon = 'link'
        if s['platform'] == 'instagram': icon = 'instagram'
        elif s['platform'] == 'tiktok': icon = 'tiktok'
        elif s['platform'] == 'x': icon = 'x-twitter'
        elif s['platform'] == 'youtube': icon = 'youtube'
        elif s['platform'] == 'facebook': icon = 'facebook-f'

        safe_card = f"""
        <a class="card plain" href="{s['url']}" target="_blank" rel="noopener" style="--accent: {s.get('accent_color', '#71767b')}">
          <span class="badge"><i class="fab fa-{icon}"></i></span>
          <span class="cap">{s['title']}</span>
        </a>
        """
        html_cards.append(safe_card)

    return jsonify({
        "status": "ok",
        "html": "\n".join(html_cards)
    })


# ─── Maskované Presmerovanie (/l/<slug>) ───────────────────────────────────────

@app.route("/l/<slug>", methods=["GET"])
def cloaked_redirect(slug):
    """
    Zaznamená kliknutie a bezpečne presmeruje na cieľovú URL.
    """
    link = db.get_cloaked_link_by_slug(slug)
    if not link or not link.get("is_active"):
        return redirect("/")

    ua = request.headers.get("User-Agent", "")
    ip = get_client_ip()
    ip_h = engine.hash_ip(ip)
    headers = get_request_headers_dict()
    referrer = request.referrer or ""

    bot_detected, bot_reason = engine.is_bot(ua, headers)
    if bot_detected:
        db.log_event(link_id=link["id"], event_type="bot_blocked", ip_hash=ip_h, user_agent=ua, bot_reason=f"click_{bot_reason}")
        return redirect("/")

    device_type = engine.detect_device(ua)

    # Zaznamenať skutočný klik
    db.log_event(
        profile_id=link["profile_id"],
        link_id=link["id"],
        event_type="click",
        ip_hash=ip_h,
        user_agent=ua,
        device_type=device_type,
        referrer=referrer
    )

    dest = link["destination_url"]
    return redirect(dest, code=302)


# ─── Auth: Prihlásenie & Odhlásenie ───────────────────────────────────────────

@app.route("/login", methods=["POST"])
def login():
    password = (request.form.get("password") or "").strip()
    prefix_api = request.headers.get("X-Forwarded-Prefix", "")

    if password == MASTER_PASSWORD:
        session.permanent = True
        session["authenticated"] = True
        target_url = f"{prefix_api}/admin" if prefix_api else "/admin"
        return redirect(target_url)
    else:
        flash("Nesprávne heslo. Skúste znova.")
        return render_template("login.html", prefix_api=prefix_api), 401


@app.route("/logout", methods=["GET"])
def logout():
    session.pop("authenticated", None)
    prefix_api = request.headers.get("X-Forwarded-Prefix", "")
    target_url = f"{prefix_api}/admin" if prefix_api else "/admin"
    return redirect(target_url)


# ─── Admin Dashboard ──────────────────────────────────────────────────────────

@app.route("/admin", methods=["GET"])
@auth_required
def admin_dashboard():
    profile = db.get_profile("clara")
    cloaked_links = db.get_cloaked_links(profile["id"], only_active=False) if profile else []
    stats = db.get_analytics_summary(profile["id"] if profile else None)

    prefix_api = request.headers.get("X-Forwarded-Prefix", "")

    current_domain = (profile.get("custom_domain") or "claragarz.com") if profile else "claragarz.com"
    dns_info = domain_mgr.check_dns_status(current_domain)

    return render_template(
        "admin.html",
        profile=profile,
        cloaked_links=cloaked_links,
        stats=stats,
        prefix_api=prefix_api,
        current_domain=current_domain,
        dns_info=dns_info,
        server_ip=domain_mgr.SERVER_IP
    )


# ─── Admin API: Vlastná Doména ────────────────────────────────────────────────

@app.route("/api/admin/domain", methods=["POST"])
@auth_required
def api_admin_save_domain():
    data = request.get_json(silent=True) or {}
    domain = (data.get("domain") or "").strip()

    profile = db.get_profile("clara")
    if not profile:
        return jsonify({"status": "error", "message": "Profil neexistuje."}), 400

    saved_domain = db.update_custom_domain(profile["id"], domain)
    if saved_domain:
        domain_mgr.setup_nginx_for_domain(saved_domain)

    dns_info = domain_mgr.check_dns_status(saved_domain)
    return jsonify({
        "status": "ok",
        "message": f"Doména {saved_domain or 'odstránená'} úspešne uložená!",
        "domain": saved_domain,
        "dns": dns_info
    })


@app.route("/api/admin/domain/check", methods=["GET"])
@auth_required
def api_admin_check_domain():
    profile = db.get_profile("clara")
    domain = profile.get("custom_domain") or "claragarz.com" if profile else "claragarz.com"
    dns_info = domain_mgr.check_dns_status(domain)
    return jsonify({"status": "ok", "dns": dns_info})


@app.route("/api/admin/domain/activate-ssl", methods=["POST"])
@auth_required
def api_admin_activate_ssl():
    profile = db.get_profile("clara")
    domain = profile.get("custom_domain") or "" if profile else ""
    if not domain:
        return jsonify({"status": "error", "message": "Najprv zadajte a uložte doménu."}), 400

    dns_info = domain_mgr.check_dns_status(domain)
    if not dns_info.get("is_pointing"):
        ips = ", ".join(dns_info.get("root_ips") or ["žiadna odpoveď"])
        return jsonify({
            "status": "error",
            "message": f"Doména {domain} zatiaľ nesmeruje na tento server ({domain_mgr.SERVER_IP}). Aktuálne v DNS: {ips}. Nastavte DNS A záznam a počkajte chvíľu na propagáciu."
        }), 400

    ok, msg = domain_mgr.issue_certbot_ssl(domain)
    if ok:
        return jsonify({"status": "ok", "message": msg})
    else:
        return jsonify({"status": "error", "message": msg}), 500


# ─── Admin API ────────────────────────────────────────────────────────────────

@app.route("/api/admin/links", methods=["POST"])
@auth_required
def api_admin_add_link():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    destination_url = (data.get("destination_url") or "").strip()
    slug = (data.get("slug") or "").strip()
    photo_url = (data.get("photo_url") or "").strip()
    is_adult = 1 if data.get("is_adult") else 0

    if not title or not destination_url or not slug:
        return jsonify({"status": "error", "message": "Vyplňte názov, cieľovú URL a slug."}), 400

    profile = db.get_profile("clara")
    if not profile:
        return jsonify({"status": "error", "message": "Profil neexistuje."}), 400

    try:
        link_id = db.add_cloaked_link(
            profile_id=profile["id"],
            slug=slug,
            title=title,
            destination_url=destination_url,
            photo_url=photo_url,
            is_adult=is_adult
        )
        return jsonify({"status": "ok", "message": "Odkaz úspešne pridaný!", "link_id": link_id}), 201
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/admin/links/<int:link_id>", methods=["DELETE"])
@auth_required
def api_admin_delete_link(link_id):
    try:
        db.delete_cloaked_link(link_id)
        return jsonify({"status": "ok", "message": "Odkaz vymazaný."}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == "__main__":
    port = int(os.environ.get("CLOAK_PORT", 5100))
    host = os.environ.get("CLOAK_HOST", "0.0.0.0")
    debug = os.environ.get("CLOAK_DEBUG") == "1"
    print(f"🔒 CloakHub beží na http://{host}:{port}")
    app.run(host=host, port=port, debug=debug)
