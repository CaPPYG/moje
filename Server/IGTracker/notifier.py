"""
IG Tracker & Publisher — Webhook Alert System
Sends instant alerts via Discord, Telegram or generic HTTP Webhook
when an account transitions into Action Required (🟡) or Error/Banned (🔴).
"""
import logging
import httpx
from datetime import datetime, timezone
import db

logger = logging.getLogger(__name__)


def send_alert(account: dict, old_status: str, new_status: str, message: str, details: str = ""):
    """
    Sends notification via configured webhooks.
    Non-blocking / catches exceptions so main workflow is never affected.
    """
    try:
        discord_url = db.get_setting("discord_webhook_url") or db.get_setting("webhook_url")
        telegram_token = db.get_setting("telegram_bot_token")
        telegram_chat_id = db.get_setting("telegram_chat_id")

        if discord_url and ("discord.com" in discord_url or "discordapp.com" in discord_url):
            _send_discord_alert(discord_url, account, old_status, new_status, message, details)
        elif discord_url:
            # Generic JSON webhook
            _send_generic_webhook(discord_url, account, old_status, new_status, message, details)

        if telegram_token and telegram_chat_id:
            _send_telegram_alert(telegram_token, telegram_chat_id, account, old_status, new_status, message, details)

    except Exception as e:
        logger.error(f"Failed to send webhook alert: {e}")


def _send_discord_alert(webhook_url: str, account: dict, old_status: str, new_status: str, message: str, details: str):
    username = account.get("username", "neznámy")
    region = account.get("region", "sk").upper()
    flag = "🇺🇸" if region == "US" else "🇸🇰"

    if new_status == "healthy":
        color = 0x10B981  # Green
        status_text = "🟢 Zdravý / Online"
        title = f"{flag} Účet @{username} je opäť aktívny"
    elif new_status == "action_required":
        color = 0xF59E0B  # Amber
        status_text = "🟡 Vyžaduje sa akcia (Checkpoint / 2FA)"
        title = f"⚠️ {flag} Pozor: @{username} vyžaduje overenie"
    else:
        color = 0xEF4444  # Red
        status_text = "🔴 Chyba / Odpojený / Ban"
        title = f"🚨 {flag} Problém s účtom @{username}"

    embed = {
        "title": title,
        "description": f"**Dôvod:** {message}",
        "color": color,
        "fields": [
            {"name": "Profil", "value": f"[@{username}](https://instagram.com/{username})", "inline": True},
            {"name": "Región", "value": f"{flag} {region}", "inline": True},
            {"name": "Nový stav", "value": status_text, "inline": True},
        ],
        "footer": {"text": "GarcArzP HUB • IG Tracker & Publisher Monitor"},
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

    if details:
        embed["fields"].append({"name": "Technické detaily", "value": f"`{details[:500]}`", "inline": False})

    if new_status == "action_required":
        embed["fields"].append({
            "name": "Odporúčaný krok",
            "value": "Otvorte tento profil v Multilogin cloud mobile a potvrďte výzvu (SMS / Selfie / 2FA).",
            "inline": False
        })

    payload = {
        "username": "IG Health Monitor",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/2111/2111463.png",
        "embeds": [embed]
    }

    try:
        r = httpx.post(webhook_url, json=payload, timeout=8)
        logger.info(f"Discord alert sent for @{username} (status={r.status_code})")
    except Exception as e:
        logger.warning(f"Discord alert failed: {e}")


def _send_telegram_alert(token: str, chat_id: str, account: dict, old_status: str, new_status: str, message: str, details: str):
    username = account.get("username", "neznámy")
    region = account.get("region", "sk").upper()
    flag = "🇺🇸" if region == "US" else "🇸🇰"

    icon = "🟢" if new_status == "healthy" else ("🟡" if new_status == "action_required" else "🔴")
    text = (
        f"{icon} <b>IG Health Monitor: {flag} @{username}</b>\n\n"
        f"<b>Stav:</b> {new_status.upper()}\n"
        f"<b>Dôvod:</b> {message}\n"
    )
    if details:
        text += f"<i>{details[:300]}</i>\n"
    if new_status == "action_required":
        text += "\n👉 <i>Otvorte profil v Multilogine a potvrďte výzvu.</i>"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        r = httpx.post(url, json=payload, timeout=8)
        logger.info(f"Telegram alert sent for @{username} (status={r.status_code})")
    except Exception as e:
        logger.warning(f"Telegram alert failed: {e}")


def _send_generic_webhook(url: str, account: dict, old_status: str, new_status: str, message: str, details: str):
    payload = {
        "event": "ig_account_health_change",
        "account_id": account.get("id"),
        "username": account.get("username"),
        "region": account.get("region"),
        "old_status": old_status,
        "new_status": new_status,
        "message": message,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    try:
        httpx.post(url, json=payload, timeout=8)
    except Exception as e:
        logger.warning(f"Generic webhook failed: {e}")
