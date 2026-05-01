"""Tests for /api/admin/stores CRUD endpoints."""
from unittest.mock import patch

import pytest

from app.db.models import Store, StoreService

BASE = "/api/admin/stores"

VALID_STORE = {
    "store_id": "T0001",
    "name": "Test Store",
    "store_type": "regular",
    "status": "active",
    "latitude": 42.3601,
    "longitude": -71.0589,
    "address_street": "1 Main St",
    "address_city": "Boston",
    "address_state": "MA",
    "address_postal_code": "02101",
    "address_country": "USA",
    "phone": "617-555-0100",
    "services": ["pharmacy", "pickup"],
    "hours": {"mon": "08:00-22:00", "tue": "08:00-22:00"},
}


@pytest.fixture()
def existing_store(db_session):
    """Insert a store directly into the DB."""
    from scripts.seed import upsert_store
    upsert_store(db_session, {
        "store_id": "E0001", "name": "Existing Store",
        "store_type": "regular", "status": "active",
        "latitude": "42.3601", "longitude": "-71.0589",
        "address_street": "1 Test St", "address_city": "Boston",
        "address_state": "MA", "address_postal_code": "02101",
        "address_country": "USA", "phone": "617-555-0100",
        "services": "pharmacy|pickup",
        "hours_mon": "08:00-22:00", "hours_tue": "08:00-22:00",
        "hours_wed": None, "hours_thu": None, "hours_fri": None,
        "hours_sat": None, "hours_sun": None,
    })
    db_session.commit()


# ===== CREATE =====

def test_create_store_201(client, seeded_db, admin_headers):
    resp = client.post(BASE, json=VALID_STORE, headers=admin_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["store_id"] == "T0001"
    assert set(data["services"]) == {"pharmacy", "pickup"}


def test_create_store_requires_auth(client, seeded_db):
    resp = client.post(BASE, json=VALID_STORE)
    assert resp.status_code == 401


def test_create_store_viewer_gets_403(client, seeded_db, viewer_headers):
    resp = client.post(BASE, json=VALID_STORE, headers=viewer_headers)
    assert resp.status_code == 403


def test_create_store_marketer_allowed(client, seeded_db, marketer_headers):
    resp = client.post(BASE, json=VALID_STORE, headers=marketer_headers)
    assert resp.status_code == 201


def test_create_duplicate_store_id_409(client, seeded_db, admin_headers, existing_store):
    body = {**VALID_STORE, "store_id": "E0001"}
    resp = client.post(BASE, json=body, headers=admin_headers)
    assert resp.status_code == 409


def test_create_auto_geocodes_when_no_coords(client, seeded_db, admin_headers):
    body = {k: v for k, v in VALID_STORE.items() if k not in ("latitude", "longitude")}
    with patch("app.services.store.geocode_address", return_value=(42.36, -71.05)):
        resp = client.post(BASE, json=body, headers=admin_headers)
    assert resp.status_code == 201
    assert resp.json()["latitude"] == 42.36


def test_create_invalid_phone_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_STORE, "phone": "bad-phone"}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_invalid_store_type_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_STORE, "store_type": "hypermarket"}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_invalid_status_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_STORE, "status": "broken"}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_invalid_service_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_STORE, "services": ["invalid_svc"]}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_invalid_hours_format_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_STORE, "hours": {"mon": "bad"}}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_hours_close_before_open_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_STORE, "hours": {"mon": "22:00-08:00"}}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_lat_out_of_range_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_STORE, "latitude": 91.0}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_only_lat_without_lon_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_STORE, "longitude": None}, headers=admin_headers)
    assert resp.status_code == 422


def test_create_long_name_returns_422(client, seeded_db, admin_headers):
    resp = client.post(BASE, json={**VALID_STORE, "name": "x" * 256}, headers=admin_headers)
    assert resp.status_code == 422


# ===== LIST =====

def test_list_stores_200(client, seeded_db, admin_headers, existing_store):
    resp = client.get(BASE, headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "stores" in data
    assert "total" in data
    assert "page" in data


def test_list_stores_requires_auth(client, seeded_db):
    resp = client.get(BASE)
    assert resp.status_code == 401


def test_list_stores_viewer_allowed(client, seeded_db, viewer_headers, existing_store):
    resp = client.get(BASE, headers=viewer_headers)
    assert resp.status_code == 200


def test_list_pagination(client, seeded_db, admin_headers, db_session):
    from scripts.seed import upsert_store
    for i in range(5):
        upsert_store(db_session, {
            "store_id": f"P{i:04d}", "name": f"Page Store {i}",
            "store_type": "regular", "status": "active",
            "latitude": "42.0", "longitude": "-71.0",
            "address_street": "1 St", "address_city": "Boston",
            "address_state": "MA", "address_postal_code": "02101",
            "address_country": "USA", "phone": "617-555-0100",
            "services": "", "hours_mon": None, "hours_tue": None,
            "hours_wed": None, "hours_thu": None, "hours_fri": None,
            "hours_sat": None, "hours_sun": None,
        })
    db_session.commit()
    resp = client.get(f"{BASE}?page=1&per_page=2", headers=admin_headers)
    assert resp.json()["per_page"] == 2
    assert len(resp.json()["stores"]) == 2


def test_list_filter_by_status(client, seeded_db, admin_headers, db_session):
    from scripts.seed import upsert_store
    upsert_store(db_session, {
        "store_id": "INACT01", "name": "Inactive Store",
        "store_type": "regular", "status": "inactive",
        "latitude": "42.0", "longitude": "-71.0",
        "address_street": "1 St", "address_city": "Boston",
        "address_state": "MA", "address_postal_code": "02101",
        "address_country": "USA", "phone": "617-555-0100",
        "services": "", "hours_mon": None, "hours_tue": None,
        "hours_wed": None, "hours_thu": None, "hours_fri": None,
        "hours_sat": None, "hours_sun": None,
    })
    db_session.commit()
    resp = client.get(f"{BASE}?status=inactive", headers=admin_headers)
    for s in resp.json()["stores"]:
        assert s["status"] == "inactive"


# ===== GET SINGLE =====

def test_get_store_200(client, seeded_db, admin_headers, existing_store):
    resp = client.get(f"{BASE}/E0001", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["store_id"] == "E0001"


def test_get_nonexistent_store_404(client, seeded_db, admin_headers):
    resp = client.get(f"{BASE}/NOPE", headers=admin_headers)
    assert resp.status_code == 404


def test_get_store_requires_auth(client, seeded_db):
    resp = client.get(f"{BASE}/E0001")
    assert resp.status_code == 401


# ===== PATCH =====

def test_patch_name(client, seeded_db, admin_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={"name": "Renamed Store"}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Renamed Store"


def test_patch_phone(client, seeded_db, admin_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={"phone": "800-555-1234"}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["phone"] == "800-555-1234"


def test_patch_services_replaces_all(client, seeded_db, admin_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={"services": ["returns"]}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["services"] == ["returns"]


def test_patch_status_to_inactive(client, seeded_db, admin_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={"status": "inactive"}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"


def test_patch_hours_partial_merge(client, seeded_db, admin_headers, existing_store):
    """Only the days in the payload should change; others should be untouched."""
    resp = client.patch(f"{BASE}/E0001", json={"hours": {"mon": "09:00-21:00"}}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["hours"]["mon"] == "09:00-21:00"
    assert resp.json()["hours"]["tue"] == "08:00-22:00"  # unchanged


def test_patch_empty_body_returns_400(client, seeded_db, admin_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={}, headers=admin_headers)
    assert resp.status_code == 400


def test_patch_disallowed_field_store_id_returns_422(client, seeded_db, admin_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={"store_id": "HACK"}, headers=admin_headers)
    assert resp.status_code == 422


def test_patch_disallowed_field_latitude_returns_422(client, seeded_db, admin_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={"latitude": 0.0}, headers=admin_headers)
    assert resp.status_code == 422


def test_patch_disallowed_address_field_returns_422(client, seeded_db, admin_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={"address_city": "New York"}, headers=admin_headers)
    assert resp.status_code == 422


def test_patch_invalid_phone_returns_422(client, seeded_db, admin_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={"phone": "bad"}, headers=admin_headers)
    assert resp.status_code == 422


def test_patch_invalid_hours_returns_422(client, seeded_db, admin_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={"hours": {"mon": "22:00-08:00"}}, headers=admin_headers)
    assert resp.status_code == 422


def test_patch_nonexistent_store_404(client, seeded_db, admin_headers):
    resp = client.patch(f"{BASE}/NOPE", json={"name": "X"}, headers=admin_headers)
    assert resp.status_code == 404


def test_patch_viewer_gets_403(client, seeded_db, viewer_headers, existing_store):
    resp = client.patch(f"{BASE}/E0001", json={"name": "X"}, headers=viewer_headers)
    assert resp.status_code == 403


# ===== DELETE =====

def test_delete_sets_status_inactive(client, seeded_db, admin_headers, existing_store):
    resp = client.delete(f"{BASE}/E0001", headers=admin_headers)
    assert resp.status_code == 200
    # Confirm via GET that status is now inactive
    get_resp = client.get(f"{BASE}/E0001", headers=admin_headers)
    assert get_resp.json()["status"] == "inactive"


def test_delete_already_inactive_is_idempotent(client, seeded_db, admin_headers, existing_store):
    client.delete(f"{BASE}/E0001", headers=admin_headers)
    resp = client.delete(f"{BASE}/E0001", headers=admin_headers)
    assert resp.status_code == 200


def test_delete_nonexistent_404(client, seeded_db, admin_headers):
    resp = client.delete(f"{BASE}/NOPE", headers=admin_headers)
    assert resp.status_code == 404


def test_delete_does_not_physically_remove_row(client, seeded_db, admin_headers, existing_store, db_session):
    client.delete(f"{BASE}/E0001", headers=admin_headers)
    store = db_session.query(Store).filter_by(store_id="E0001").first()
    assert store is not None
    assert store.status == "inactive"


def test_delete_viewer_gets_403(client, seeded_db, viewer_headers, existing_store):
    resp = client.delete(f"{BASE}/E0001", headers=viewer_headers)
    assert resp.status_code == 403
