"""
BrainDump — Ultra-light Authentication
Supports:
- Password verification (default: patrik3924)
- Stateless HMAC tokens (0 RAM / DB overhead)
- Cookie session, Bearer token, X-Master-Password header, and query param
"""
import os
import hmac
import time
import base64
import hashlib
from typing import Optional
from fastapi import Request, HTTPException, Depends
from dotenv import load_dotenv

load_dotenv()

MASTER_PASSWORD = os.getenv("BRAINDUMP_PASSWORD", "patrik3924")
SECRET_KEY = os.getenv("SECRET_KEY", "braindump-patrik3924-secure-seed-key-v1").encode("utf-8")
TOKEN_MAX_AGE_SECONDS = 60 * 60 * 24 * 180  # 180 days


def verify_password(pw: str) -> bool:
    """Constant-time comparison with case-insensitivity fallback (prevents mobile auto-cap issues)."""
    if not pw:
        return False
    clean_pw = pw.strip()
    return hmac.compare_digest(clean_pw.encode("utf-8"), MASTER_PASSWORD.encode("utf-8")) or \
           hmac.compare_digest(clean_pw.lower().encode("utf-8"), MASTER_PASSWORD.lower().encode("utf-8"))


def create_token() -> str:
    """Generate a tamper-proof HMAC signed token."""
    timestamp = str(int(time.time()))
    payload = f"patrik:{timestamp}".encode("utf-8")
    sig = hmac.new(SECRET_KEY, payload, hashlib.sha256).hexdigest()
    raw = f"{timestamp}:{sig}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("utf-8")


def verify_token(token: Optional[str]) -> bool:
    """Verify HMAC signature and token expiration."""
    if not token:
        return False
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        timestamp_str, sig = raw.split(":", 1)
        created_at = int(timestamp_str)

        # Check expiration
        if time.time() - created_at > TOKEN_MAX_AGE_SECONDS:
            return False

        # Re-compute signature
        payload = f"patrik:{timestamp_str}".encode("utf-8")
        expected_sig = hmac.new(SECRET_KEY, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected_sig)
    except Exception:
        return False


async def require_auth(request: Request) -> bool:
    """
    FastAPI dependency to secure endpoints.
    Accepts:
    1. Header 'X-Master-Password'
    2. Header 'Authorization: Bearer <token>'
    3. Cookie 'braindump_session'
    4. Query param 'key' or 'password'
    """
    # 1. X-Master-Password header
    master_header = request.headers.get("X-Master-Password")
    if master_header and verify_password(master_header):
        return True

    # 2. Authorization Bearer header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
        if verify_token(token) or verify_password(token):
            return True

    # 3. Cookie
    session_cookie = request.cookies.get("braindump_session")
    if session_cookie and verify_token(session_cookie):
        return True

    # 4. Query param (?key=... or ?password=...)
    q_key = request.query_params.get("key") or request.query_params.get("password")
    if q_key and (verify_password(q_key) or verify_token(q_key)):
        return True

    raise HTTPException(
        status_code=401,
        detail="Neautorizovaný prístup. Zadajte platné heslo.",
        headers={"WWW-Authenticate": "Bearer"},
    )
