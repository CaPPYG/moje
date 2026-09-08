import re
import hashlib
import secrets
from typing import Tuple, Optional

# Zoznam regexov pre crawlerov a botov sociálnych sietí a vyhľadávačov
BOT_UA_PATTERNS = [
    r'facebookexternalhit',
    r'facebot',
    r'meta-externalagent',
    r'tiktokbot',
    r'bytedance',
    r'twitterbot',
    r'x-crawler',
    r'googlebot',
    r'bingbot',
    r'yandex',
    r'baiduspider',
    r'duckduckbot',
    r'applebot',
    r'headlesschrome',
    r'phantomjs',
    r'puppeteer',
    r'playwright',
    r'selenium',
    r'webdriver',
    r'scrapy',
    r'python-requests',
    r'aiohttp',
    r'httpx',
    r'curl\/',
    r'wget\/',
    r'go-http-client',
    r'java\/',
    r'apache-httpclient',
    r'telegrambot',
    r'discordbot',
    r'slackbot',
    r'whatsapp',
]

BOT_REGEX = re.compile('|'.join(BOT_UA_PATTERNS), re.IGNORECASE)


def is_bot(user_agent: str, headers: dict) -> Tuple[bool, Optional[str]]:
    """
    Overí, či je požiadavka od bota/crawlera alebo reálneho používateľa.
    Vráti (is_bot: bool, reason: str).
    """
    ua = (user_agent or '').strip()

    if not ua:
        return True, "empty_user_agent"

    # 1. Kontrola podľa User-Agent regexu
    if BOT_REGEX.search(ua):
        match = BOT_REGEX.search(ua).group(0)
        return True, f"ua_match:{match}"

    # 2. Kontrola podozrivých chýbajúcich hlavičiek typických pre bežný prehliadač
    accept_lang = headers.get('Accept-Language', '')
    if not accept_lang and 'Mozilla' in ua:
        # Skutočný moderný prehliadač takmer vždy posiela Accept-Language
        return True, "missing_accept_language"

    return False, None


def detect_device(user_agent: str) -> str:
    """Deteguje typ zariadenia: 'ios', 'android', 'desktop'."""
    ua = user_agent.lower()
    if 'iphone' in ua or 'ipad' in ua or 'ipod' in ua:
        return 'ios'
    elif 'android' in ua:
        return 'android'
    return 'desktop'


def hash_ip(ip: str) -> str:
    """Hashuje IP adresu s pevnou soľou pre anonymizované štatistiky."""
    salt = "cloakhub-garcarzp-2026"
    return hashlib.sha256(f"{salt}-{ip}".encode('utf-8')).hexdigest()[:16]


# ─── Proof-of-Work Challenge Engine ───────────────────────────────────────────

POW_PREFIX = "000"  # Náročnosť: hash musí začínať na '000' (cca 16^3 = 4096 iterácií, ~20-80ms v JS)


def generate_pow_challenge() -> str:
    """Vygeneruje náhodný challenge reťazec pre klientský skript."""
    return secrets.token_urlsafe(9)


def verify_pow(challenge: str, nonce: str) -> bool:
    """
    Overí, či klient správne vyriešil Proof-of-Work.
    sha256(challenge + ':' + nonce) musí začínať na POW_PREFIX.
    """
    if not challenge or not nonce:
        return False
    data = f"{challenge}:{nonce}".encode('utf-8')
    h = hashlib.sha256(data).hexdigest()
    return h.startswith(POW_PREFIX)


# ─── In-App Browser Escape Engine ─────────────────────────────────────────────

def build_chrome_intent_url(target_url: str) -> str:
    """
    Zostaví Android Chrome Intent URL pre vynútené otvorenie v Google Chrome.
    """
    clean_url = re.sub(r'^https?:\/\/', '', target_url)
    return (
        f"intent://{clean_url}#Intent;scheme=https;package=com.android.chrome;"
        f"S.browser_fallback_url={target_url};end"
    )
