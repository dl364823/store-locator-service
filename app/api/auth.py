import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import RefreshToken, User
from app.exceptions import AuthenticationError
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenResponse,
)
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
    refresh_token_expires_at,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Auth"])

# Generic message used for ALL login failures — never reveal whether email exists
_INVALID_CREDENTIALS_MSG = "Invalid email or password."


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login",
    description="Authenticate with email and password. Returns access + refresh tokens.",
)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user: User | None = db.query(User).filter_by(email=body.email).first()

    # Verify password even when user doesn't exist to maintain constant-time behaviour.
    # bcrypt.checkpw against a dummy hash ensures the same CPU time either way.
    _dummy_hash = "$2b$12$KIXzMEGmyoK6yZ1hB.WJUuiDKOQJFNqKbgUXd8Xr/ZPdBpJn6L./2"
    password_ok = verify_password(body.password, user.password_hash if user else _dummy_hash)

    if not user or not password_ok or user.status != "active":
        # Same error for wrong email, wrong password, and inactive account
        raise AuthenticationError(_INVALID_CREDENTIALS_MSG, code="INVALID_CREDENTIALS")

    raw_refresh = create_refresh_token(user.user_id)
    db.add(
        RefreshToken(
            token_hash=hash_token(raw_refresh),
            user_id=user.user_id,
            expires_at=refresh_token_expires_at(),
            revoked=False,
        )
    )
    db.commit()

    logger.info("User %s logged in", user.user_id)
    return TokenResponse(
        access_token=create_access_token(user.user_id, user.email, user.role_name),
        refresh_token=raw_refresh,
        must_change_password=user.must_change_password,
    )


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Refresh access token",
    description="Exchange a valid refresh token for a new access token.",
)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)) -> AccessTokenResponse:
    # decode_token raises AuthenticationError on expired or malformed tokens
    payload = decode_token(body.refresh_token)

    if payload.get("type") != "refresh":
        raise AuthenticationError("Invalid token type.", code="INVALID_TOKEN")

    stored: RefreshToken | None = (
        db.query(RefreshToken)
        .filter_by(token_hash=hash_token(body.refresh_token))
        .first()
    )
    if not stored or stored.revoked:
        raise AuthenticationError("Token has been revoked.", code="TOKEN_REVOKED")

    user: User | None = db.query(User).filter_by(user_id=stored.user_id).first()
    if not user or user.status != "active":
        raise AuthenticationError("Invalid token.", code="INVALID_TOKEN")

    return AccessTokenResponse(
        access_token=create_access_token(user.user_id, user.email, user.role_name)
    )


@router.post(
    "/logout",
    summary="Logout",
    description="Revoke a refresh token. Idempotent — always returns 200.",
)
def logout(body: LogoutRequest, db: Session = Depends(get_db)) -> dict:
    stored: RefreshToken | None = (
        db.query(RefreshToken)
        .filter_by(token_hash=hash_token(body.refresh_token))
        .first()
    )
    if stored and not stored.revoked:
        stored.revoked = True
        db.commit()
        logger.info("Refresh token revoked for user %s", stored.user_id)

    # Always return 200 — don't reveal whether the token existed
    return {"message": "Successfully logged out."}
