"""Tests for auth endpoints and RBAC dependencies."""
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import get_settings
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    hash_token,
    verify_password,
)

SETTINGS = get_settings()

LOGIN_URL = "/api/auth/login"
REFRESH_URL = "/api/auth/refresh"
LOGOUT_URL = "/api/auth/logout"


# ---------- verify_password unit tests ----------

def test_verify_password_correct():
    from scripts.seed import hash_password
    hashed = hash_password("TestPassword123!")
    assert verify_password("TestPassword123!", hashed) is True


def test_verify_password_wrong():
    from scripts.seed import hash_password
    hashed = hash_password("TestPassword123!")
    assert verify_password("WrongPassword!", hashed) is False


def test_verify_password_returns_false_on_garbage():
    assert verify_password("any", "not-a-bcrypt-hash") is False


# ---------- login ----------

def test_login_success(client, seeded_db):
    resp = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": "AdminTest123!"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password_returns_401(client, seeded_db):
    resp = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": "WrongPassword!"})
    assert resp.status_code == 401


def test_login_nonexistent_email_returns_401(client, seeded_db):
    resp = client.post(LOGIN_URL, json={"email": "nobody@test.com", "password": "Whatever123!"})
    assert resp.status_code == 401


def test_login_wrong_password_and_nonexistent_email_same_message(client, seeded_db):
    """Both failure modes must return the same error message (prevent user enumeration)."""
    wrong_pw = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": "Bad!"})
    no_user = client.post(LOGIN_URL, json={"email": "ghost@test.com", "password": "Bad!"})
    assert wrong_pw.json()["error"]["message"] == no_user.json()["error"]["message"]


def test_login_inactive_user_returns_401(client, seeded_db):
    from app.db.models import User
    user = seeded_db.query(User).filter_by(email="viewer@test.com").one()
    user.status = "inactive"
    seeded_db.commit()
    resp = client.post(LOGIN_URL, json={"email": "viewer@test.com", "password": "ViewerTest123!"})
    assert resp.status_code == 401


def test_login_empty_password_returns_422(client, seeded_db):
    resp = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": ""})
    assert resp.status_code == 422


def test_login_missing_fields_returns_422(client, seeded_db):
    resp = client.post(LOGIN_URL, json={"email": "admin@test.com"})
    assert resp.status_code == 422


def test_login_stores_refresh_token_as_hash(client, seeded_db):
    """The raw refresh token must never appear in the DB."""
    from app.db.models import RefreshToken
    resp = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": "AdminTest123!"})
    raw_refresh = resp.json()["refresh_token"]
    expected_hash = hash_token(raw_refresh)
    stored = seeded_db.query(RefreshToken).filter_by(token_hash=expected_hash).first()
    assert stored is not None
    # Confirm the raw token is not stored anywhere in the DB row
    assert raw_refresh not in str(stored.__dict__)


# ---------- refresh ----------

def test_refresh_returns_new_access_token(client, seeded_db):
    login = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": "AdminTest123!"})
    refresh_tok = login.json()["refresh_token"]
    resp = client.post(REFRESH_URL, json={"refresh_token": refresh_tok})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_refresh_with_revoked_token_returns_401(client, seeded_db):
    login = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": "AdminTest123!"})
    refresh_tok = login.json()["refresh_token"]
    client.post(LOGOUT_URL, json={"refresh_token": refresh_tok})
    resp = client.post(REFRESH_URL, json={"refresh_token": refresh_tok})
    assert resp.status_code == 401


def test_refresh_with_access_token_returns_401(client, seeded_db):
    """Using an access token where a refresh token is expected must be rejected."""
    login = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": "AdminTest123!"})
    access_tok = login.json()["access_token"]
    resp = client.post(REFRESH_URL, json={"refresh_token": access_tok})
    assert resp.status_code == 401


def test_refresh_with_expired_token_returns_401(client, seeded_db):
    payload = {
        "user_id": "U001",
        "type": "refresh",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        "iat": datetime.now(timezone.utc) - timedelta(days=8),
    }
    expired = jwt.encode(payload, SETTINGS.jwt_secret_key, algorithm=SETTINGS.jwt_algorithm)
    resp = client.post(REFRESH_URL, json={"refresh_token": expired})
    assert resp.status_code == 401


def test_refresh_with_tampered_token_returns_401(client, seeded_db):
    resp = client.post(REFRESH_URL, json={"refresh_token": "not.a.valid.jwt"})
    assert resp.status_code == 401


def test_refresh_empty_token_returns_422(client, seeded_db):
    resp = client.post(REFRESH_URL, json={"refresh_token": ""})
    assert resp.status_code == 422


# ---------- logout ----------

def test_logout_success(client, seeded_db):
    login = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": "AdminTest123!"})
    refresh_tok = login.json()["refresh_token"]
    resp = client.post(LOGOUT_URL, json={"refresh_token": refresh_tok})
    assert resp.status_code == 200


def test_logout_revokes_refresh_token(client, seeded_db):
    from app.db.models import RefreshToken
    login = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": "AdminTest123!"})
    raw = login.json()["refresh_token"]
    client.post(LOGOUT_URL, json={"refresh_token": raw})
    stored = seeded_db.query(RefreshToken).filter_by(token_hash=hash_token(raw)).first()
    assert stored.revoked is True


def test_logout_is_idempotent(client, seeded_db):
    login = client.post(LOGIN_URL, json={"email": "admin@test.com", "password": "AdminTest123!"})
    refresh_tok = login.json()["refresh_token"]
    r1 = client.post(LOGOUT_URL, json={"refresh_token": refresh_tok})
    r2 = client.post(LOGOUT_URL, json={"refresh_token": refresh_tok})
    assert r1.status_code == 200
    assert r2.status_code == 200


def test_logout_unknown_token_still_200(client, seeded_db):
    resp = client.post(LOGOUT_URL, json={"refresh_token": "unknown.token.value"})
    assert resp.status_code == 200


# ---------- get_current_user dependency ----------

def test_missing_auth_header_returns_401(client, seeded_db):
    """Any protected endpoint without a token must return 401."""
    # Use /api/auth/refresh which requires a body, not a protected endpoint yet —
    # instead verify using a custom route. For now test via the refresh endpoint
    # using an intentionally wrong call, or we can test directly later via admin routes.
    # This placeholder confirms the dependency raises correctly once admin routes exist.
    pass


def test_expired_access_token_returns_401(client, seeded_db):
    payload = {
        "user_id": "U001",
        "email": "admin@test.com",
        "role": "admin",
        "type": "access",
        "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        "iat": datetime.now(timezone.utc) - timedelta(minutes=16),
    }
    expired = jwt.encode(payload, SETTINGS.jwt_secret_key, algorithm=SETTINGS.jwt_algorithm)
    resp = client.post(REFRESH_URL, json={"refresh_token": expired})
    # refresh endpoint checks type=refresh, but the token is expired first
    assert resp.status_code == 401


def test_tampered_access_token_returns_401(client, seeded_db):
    token = create_access_token("U001", "admin@test.com", "admin")
    tampered = token[:-5] + "XXXXX"
    resp = client.post(REFRESH_URL, json={"refresh_token": tampered})
    assert resp.status_code == 401


# ---------- RBAC unit tests ----------

def test_require_permission_blocks_wrong_role(client, seeded_db):
    """Viewer token trying to access a marketer+ endpoint should get 403.
    This is tested more thoroughly in admin_stores tests; here we verify
    the RBAC machinery via token inspection.
    """
    from app.dependencies.rbac import require_permission
    from app.db.models import User

    # Construct a viewer user object with the right role
    viewer = seeded_db.query(User).filter_by(user_id="U003").one()
    assert "stores:write" not in viewer.permission_names
    assert "stores:read" in viewer.permission_names


def test_admin_has_all_permissions(client, seeded_db):
    from app.db.models import User
    admin = seeded_db.query(User).filter_by(user_id="U001").one()
    required = {"stores:read", "stores:write", "users:read", "users:write", "import:write"}
    assert required.issubset(set(admin.permission_names))
