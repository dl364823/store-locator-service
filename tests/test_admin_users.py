"""Tests for /api/admin/users endpoints (admin only)."""
import pytest

from app.db.models import User

BASE = "/api/admin/users"

VALID_USER = {
    "email": "newuser@test.com",
    "password": "SecurePass123!",
    "role": "viewer",
}


# ===== Auth / RBAC =====

def test_create_requires_auth(client, seeded_db):
    resp = client.post(BASE, json=VALID_USER)
    assert resp.status_code == 401


def test_create_marketer_gets_403(client, seeded_db, marketer_headers):
    resp = client.post(BASE, json=VALID_USER, headers=marketer_headers)
    assert resp.status_code == 403


def test_create_viewer_gets_403(client, seeded_db, viewer_headers):
    resp = client.post(BASE, json=VALID_USER, headers=viewer_headers)
    assert resp.status_code == 403


def test_list_requires_auth(client, seeded_db):
    resp = client.get(BASE)
    assert resp.status_code == 401


def test_list_marketer_gets_403(client, seeded_db, marketer_headers):
    resp = client.get(BASE, headers=marketer_headers)
    assert resp.status_code == 403


def test_update_marketer_gets_403(client, seeded_db, marketer_headers):
    resp = client.put(f"{BASE}/U001", json={"role": "viewer"}, headers=marketer_headers)
    assert resp.status_code == 403


def test_delete_marketer_gets_403(client, seeded_db, marketer_headers):
    resp = client.delete(f"{BASE}/U001", headers=marketer_headers)
    assert resp.status_code == 403


# ===== CREATE =====

def test_create_user_201(client, seeded_db, admin_headers):
    resp = client.post(BASE, json=VALID_USER, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@test.com"
    assert data["role"] == "viewer"
    assert data["status"] == "active"
    assert data["must_change_password"] is True
    assert "user_id" in data


def test_create_user_id_sequential(client, seeded_db, admin_headers, db_session):
    """New user gets next U### ID after the seed users (U001-U003)."""
    resp = client.post(BASE, json=VALID_USER, headers=admin_headers)
    assert resp.json()["user_id"] == "U004"


def test_create_password_not_in_response(client, seeded_db, admin_headers):
    resp = client.post(BASE, json=VALID_USER, headers=admin_headers)
    assert "password" not in resp.json()
    assert "password_hash" not in resp.json()


def test_create_duplicate_email_409(client, seeded_db, admin_headers):
    client.post(BASE, json=VALID_USER, headers=admin_headers)
    resp = client.post(BASE, json=VALID_USER, headers=admin_headers)
    assert resp.status_code == 409


def test_create_duplicate_email_case_insensitive(client, seeded_db, admin_headers):
    client.post(BASE, json=VALID_USER, headers=admin_headers)
    upper_email = {**VALID_USER, "email": "NEWUSER@TEST.COM"}
    resp = client.post(BASE, json=upper_email, headers=admin_headers)
    assert resp.status_code == 409


def test_create_invalid_role_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_USER, "role": "superadmin"}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_invalid_email_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_USER, "email": "not-an-email"}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_short_password_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_USER, "password": "short"}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_missing_field_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={"email": "x@test.com"}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_all_valid_roles(client, seeded_db, admin_headers):
    for i, role in enumerate(("admin", "marketer", "viewer")):
        resp = client.post(
            BASE,
            json={"email": f"role{i}@test.com", "password": "Password123!", "role": role},
            headers=admin_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["role"] == role


# ===== LIST =====

def test_list_users_200(client, seeded_db, admin_headers):
    resp = client.get(BASE, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert "total" in data


def test_list_contains_seed_users(client, seeded_db, admin_headers):
    resp = client.get(BASE, headers=admin_headers)
    emails = {u["email"] for u in resp.json()["users"]}
    assert "admin@test.com" in emails
    assert "marketer@test.com" in emails
    assert "viewer@test.com" in emails


def test_list_passwords_not_exposed(client, seeded_db, admin_headers):
    resp = client.get(BASE, headers=admin_headers)
    for user in resp.json()["users"]:
        assert "password" not in user
        assert "password_hash" not in user


# ===== UPDATE (PUT) =====

def test_update_role(client, seeded_db, admin_headers):
    resp = client.put(f"{BASE}/U003", json={"role": "marketer"}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["role"] == "marketer"


def test_update_status_to_inactive(client, seeded_db, admin_headers):
    resp = client.put(f"{BASE}/U003", json={"status": "inactive"}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"


def test_update_both_role_and_status(client, seeded_db, admin_headers):
    resp = client.put(f"{BASE}/U003", json={"role": "marketer", "status": "inactive"}, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["role"] == "marketer"
    assert data["status"] == "inactive"


def test_update_empty_body_returns_422(client, seeded_db, admin_headers):
    resp = client.put(f"{BASE}/U003", json={}, headers=admin_headers)
    assert resp.status_code == 422


def test_update_invalid_role_returns_422(client, seeded_db, admin_headers):
    resp = client.put(f"{BASE}/U003", json={"role": "superuser"}, headers=admin_headers)
    assert resp.status_code == 422


def test_update_invalid_status_returns_422(client, seeded_db, admin_headers):
    resp = client.put(f"{BASE}/U003", json={"status": "suspended"}, headers=admin_headers)
    assert resp.status_code == 422


def test_update_disallowed_field_returns_422(client, seeded_db, admin_headers):
    """PUT must reject fields not in the schema (extra='forbid')."""
    resp = client.put(f"{BASE}/U003", json={"email": "hacker@test.com"}, headers=admin_headers)
    assert resp.status_code == 422


def test_update_nonexistent_user_404(client, seeded_db, admin_headers):
    resp = client.put(f"{BASE}/U999", json={"role": "viewer"}, headers=admin_headers)
    assert resp.status_code == 404


# ===== DELETE =====

def test_delete_user_200(client, seeded_db, admin_headers):
    resp = client.delete(f"{BASE}/U003", headers=admin_headers)
    assert resp.status_code == 200


def test_delete_sets_status_inactive(client, seeded_db, admin_headers, db_session):
    client.delete(f"{BASE}/U003", headers=admin_headers)
    user = db_session.query(User).filter_by(user_id="U003").first()
    assert user.status == "inactive"


def test_delete_does_not_physically_remove_row(client, seeded_db, admin_headers, db_session):
    client.delete(f"{BASE}/U003", headers=admin_headers)
    assert db_session.query(User).filter_by(user_id="U003").first() is not None


def test_delete_already_inactive_is_idempotent(client, seeded_db, admin_headers):
    client.delete(f"{BASE}/U003", headers=admin_headers)
    resp = client.delete(f"{BASE}/U003", headers=admin_headers)
    assert resp.status_code == 200


def test_delete_nonexistent_user_404(client, seeded_db, admin_headers):
    resp = client.delete(f"{BASE}/U999", headers=admin_headers)
    assert resp.status_code == 404
