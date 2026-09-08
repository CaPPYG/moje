"""
IG Tracker & Publisher — Account Health Monitor Engine
Checks official Meta Graph API token validity, checks for checkpoints / 2FA challenges,
banned/404 profile states, and triggers alerts on status transitions.
"""
import time
import logging
import threading
import httpx
import db
import notifier

logger = logging.getLogger(__name__)


def check_account_health(account_id: int) -> dict:
    """
    Overí zdravotný stav jedného účtu:
    - 🟢 healthy: token platný, API odpovedá 200 OK
    - 🟡 action_required: checkpoint / challenge / SMS / selfie / 2FA výzva
    - 🔴 error: vypršaný token, ban, 404 na webe, zablokovaný účet
    """
    account = db.get_account_by_id(account_id)
    if not account:
        return {"account_id": account_id, "status": "error", "message": "Účet nebol nájdený"}

    old_status = account.get("health_status") or "healthy"
    token = (account.get("ig_access_token") or "").strip()
    username = account.get("username", "")

    new_status = "healthy"
    message = "API spojenie je 100% aktívne"
    details = ""

    if not token:
        new_status = "error"
        message = "Chýba Meta Access Token (potrebné autorizovať cez link)"
    else:
        # 1. Kontrola cez oficiálne Meta Graph API
        try:
            r = httpx.get(
                "https://graph.instagram.com/me",
                params={
                    "fields": "id,username,account_type,media_count",
                    "access_token": token,
                },
                timeout=12,
            )
            data = r.json()

            if r.status_code == 200 and "id" in data:
                acc_type = data.get("account_type", "Creator")
                media_cnt = data.get("media_count", 0)
                new_status = "healthy"
                message = f"Session aktívna ({acc_type}, {media_cnt} príspevkov)"
            else:
                err = data.get("error", {})
                err_msg = err.get("message", "Neznáma chyba API")
                err_code = err.get("code")
                err_subcode = err.get("error_subcode")
                details = f"Code: {err_code}, Subcode: {err_subcode}, Msg: {err_msg}"

                err_msg_lower = err_msg.lower()

                if "checkpoint" in err_msg_lower or "challenge" in err_msg_lower or err_subcode in (490, 491, 492):
                    new_status = "action_required"
                    message = "Detegovaný checkpoint / 2FA výzva (otvorte profil v Multilogine)"
                elif err_subcode == 458:
                    new_status = "error"
                    message = "Prístup bol odvolaný alebo bolo zmenené heslo"
                elif err_subcode == 463 or "expired" in err_msg_lower:
                    new_status = "error"
                    message = "Platnosť tokenu vypršala (potrebné znova autorizovať)"
                elif "disabled" in err_msg_lower or "restricted" in err_msg_lower or "not active" in err_msg_lower:
                    new_status = "error"
                    message = "Účet bol obmedzený alebo deaktivovaný Instagramom"
                elif "api access blocked" in err_msg_lower:
                    new_status = "error"
                    message = "Meta API blokované (Profil na mobile je 100% OK, chyba je v Meta Appke)"
                else:
                    new_status = "error"
                    message = f"Chyba Meta API: {err_msg[:120]}"

        except Exception as e:
            logger.warning(f"Graph API health check network exception pre {username}: {e}")
            new_status = "error"
            message = f"Chyba siete pri overovaní: {str(e)[:80]}"
            details = str(e)

    # 2. Rýchla webová kontrola dostupnosti profilu (detekcia 404 zmazania / banu)
    if new_status == "healthy" and username:
        try:
            head_res = httpx.get(
                f"https://www.instagram.com/{username}/",
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
                timeout=6,
                follow_redirects=True,
            )
            if head_res.status_code == 404:
                new_status = "error"
                message = "Verejný profil vracia 404 (účet neexistuje alebo bol zmazaný)"
        except Exception:
            pass  # Nechceme označiť chybu len kvôli web scraper timeoutu

    # 3. Zápis do databázy
    db.update_account_health(account_id, new_status, message)

    # 4. Webhook notifikácia pri zmene stavu na 🟡 alebo 🔴 (alebo návrate na 🟢)
    if old_status != new_status:
        logger.info(f"Health transition pre @{username}: {old_status} -> {new_status} ({message})")
        notifier.send_alert(account, old_status, new_status, message, details)

    return {
        "account_id": account_id,
        "username": username,
        "region": account.get("region", "sk"),
        "old_status": old_status,
        "new_status": new_status,
        "message": message,
        "details": details
    }


def check_all_accounts_health() -> list[dict]:
    """Prebehne všetky sledované účty a overí ich zdravie s bezpečnou pauzou."""
    accounts = db.get_all_accounts()
    results = []
    for acc in accounts:
        res = check_account_health(acc["id"])
        results.append(res)
        time.sleep(0.4)  # Šetrné k rate limitom Meta API
    return results


# ─── Background Periodic Worker ───────────────────────────────────────────────

_worker_thread = None
_worker_started = False


def _background_loop(interval_seconds=1800):
    """Beží na pozadí a každých 30 minút skontroluje stav všetkých účtov."""
    time.sleep(15)  # Počká na štart appky
    while True:
        try:
            logger.info("Spúšťam periodickú kontrolu zdravia účtov...")
            check_all_accounts_health()
        except Exception as e:
            logger.error(f"Chyba v periodickom health workeri: {e}")

        # Čakanie s možnosťou dynamického intervalu z databázy
        try:
            custom_interval = int(db.get_setting("auto_health_interval_seconds", interval_seconds))
            wait_time = max(300, custom_interval)
        except (ValueError, TypeError):
            wait_time = interval_seconds
        time.sleep(wait_time)


def start_background_health_worker(interval_seconds=1800):
    global _worker_thread, _worker_started
    if _worker_started:
        return
    _worker_started = True
    _worker_thread = threading.Thread(target=_background_loop, args=(interval_seconds,), daemon=True)
    _worker_thread.start()
    logger.info("Account Health Monitor background worker naštartovaný.")
