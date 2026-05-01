import hashlib
import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings
from app.exceptions import AuthenticationError

logger = logging.getLogger(__name__)


# ---------- Password helpers ----------

def hash_password(password: str) -> str:
    """bcrypt-hash a plaintext password. Each call produces a unique salt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt comparison. Returns False on any error."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ---------- Token creation ----------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_access_token(user_id: str, email: str, role: str) -> str:
    settings = get_settings()
    exp = _utc_now() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "user_id": user_id,
        "email": email,
        "role": role,
        "type": "access",
        "exp": exp,
        "iat": _utc_now(),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    settings = get_settings()
    exp = _utc_now() + timedelta(days=settings.refresh_token_expire_days)
    payload = {
        "user_id": user_id,
        "type": "refresh",
        "exp": exp,
        "iat": _utc_now(),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def refresh_token_expires_at() -> datetime:
    """Return the expiry datetime for a refresh token (naive UTC)."""
    settings = get_settings()
    return _utc_now() + timedelta(days=settings.refresh_token_expire_days)


# ---------- Token decoding ----------

def decode_token(token: str) -> dict:
    """Decode and verify a JWT. Raises AuthenticationError on any failure."""
    settings = get_settings()
    try:
        return jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token has expired.", code="TOKEN_EXPIRED")
    except jwt.InvalidTokenError:
        # Covers tampered signature, wrong algorithm, malformed token, etc.
        raise AuthenticationError("Invalid token.", code="INVALID_TOKEN")


# ---------- Token hash ----------

def hash_token(raw_token: str) -> str:
    """SHA-256 hex digest of a raw JWT — this is what gets stored in the DB."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
