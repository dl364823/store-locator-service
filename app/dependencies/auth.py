import logging

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import User
from app.exceptions import AuthenticationError
from app.services.auth import decode_token

logger = logging.getLogger(__name__)

# auto_error=False so we can return our own error envelope instead of FastAPI's
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Validate the Bearer token and return the active user.

    401 on: missing header, malformed token, expired token, wrong token type,
            user not found, user inactive.
    """
    if not credentials:
        raise AuthenticationError(
            "Authorization header is required.", code="MISSING_TOKEN"
        )

    payload = decode_token(credentials.credentials)

    if payload.get("type") != "access":
        raise AuthenticationError("Invalid token type.", code="INVALID_TOKEN")

    user = db.query(User).filter_by(user_id=payload.get("user_id")).first()
    if user is None or user.status != "active":
        # Don't distinguish "not found" from "inactive" to avoid user enumeration
        raise AuthenticationError("Invalid token.", code="INVALID_TOKEN")

    return user
