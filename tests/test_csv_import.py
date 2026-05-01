"""Tests for POST /api/admin/stores/import."""
import io
from pathlib import Path
from unittest.mock import patch

import pytest

from app.db.models import Store, StoreService

IMPORT_URL = "/api/admin/stores/import"
STORES_1000 = Path(__file__).parent.parent / "stores_1000.csv"

HEADERS = (
    "store_id,name,store_type,status,latitude,longitude,"
    "address_street,address_city,address_state,address_postal_code,address_country,"
    "phone,services,"
    "hours_mon,hours_tue,hours_wed,hours_thu,hours_fri,hours_sat,hours_sun"
)

VALID_ROW = (
    "IMP001,Import Store,regular,active,42.3601,-71.0589,"
    "1 Main St,Boston,MA,02101,USA,"
    "617-555-0100,pharmacy|pickup,"
    "08:00-22:00,08:00-22:00,08:00-22:00,08:00-22:00,08:00-22:00,09:00-21:00,10:00-20:00"
)


def _csv_file(content: str, filename: str = "stores.csv") -> dict:
    return {
        "file": (filename, io.BytesIO(content.encode()), "text/csv"),
    }


def _post(client, content: str, headers: dict, filename: str = "stores.csv"):
    return client.post(
        IMPORT_URL,
        files={"file": (filename, io.BytesIO(content.encode()), "text/csv")},
        headers=headers,
    )


# ===== Auth / RBAC =====

def test_import_requires_auth(client, seeded_db):
    resp = client.post(IMPORT_URL, files={"file": ("f.csv", io.BytesIO(b""), "text/csv")})
    assert resp.status_code == 401


def test_import_viewer_gets_403(client, seeded_db, viewer_headers):
    resp = _post(client, f"{HEADERS}\n{VALID_ROW}", viewer_headers)
    assert resp.status_code == 403


def test_import_marketer_allowed(client, seeded_db, marketer_headers):
    resp = _post(client, f"{HEADERS}\n{VALID_ROW}", marketer_headers)
    assert resp.status_code == 200


# ===== Happy path =====

def test_import_creates_new_store(client, seeded_db, admin_headers, db_session):
    resp = _post(client, f"{HEADERS}\n{VALID_ROW}", admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["created"] == 1
    assert data["updated"] == 0
    assert db_session.query(Store).filter_by(store_id="IMP001").first() is not None


def test_import_updates_existing_store(client, seeded_db, admin_headers, db_session):
    # First import creates the store
    _post(client, f"{HEADERS}\n{VALID_ROW}", admin_headers)
    # Second import with changed name updates it
    updated_row = VALID_ROW.replace("Import Store", "Updated Store Name")
    resp = _post(client, f"{HEADERS}\n{updated_row}", admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["updated"] == 1
    assert data["created"] == 0
    store = db_session.query(Store).filter_by(store_id="IMP001").first()
    assert store.name == "Updated Store Name"


def test_import_mix_of_create_and_update(client, seeded_db, admin_headers, db_session):
    _post(client, f"{HEADERS}\n{VALID_ROW}", admin_headers)
    row2 = VALID_ROW.replace("IMP001", "IMP002")
    resp = _post(client, f"{HEADERS}\n{VALID_ROW}\n{row2}", admin_headers)
    data = resp.json()
    assert data["created"] == 1
    assert data["updated"] == 1


def test_import_services_stored_correctly(client, seeded_db, admin_headers, db_session):
    _post(client, f"{HEADERS}\n{VALID_ROW}", admin_headers)
    svcs = {
        s.service_name
        for s in db_session.query(StoreService).filter_by(store_id="IMP001").all()
    }
    assert svcs == {"pharmacy", "pickup"}


def test_import_report_has_required_fields(client, seeded_db, admin_headers):
    resp = _post(client, f"{HEADERS}\n{VALID_ROW}", admin_headers)
    data = resp.json()
    for field in ("total", "created", "updated", "failed", "errors", "success"):
        assert field in data


# ===== File-level errors =====

def test_import_empty_file_returns_400(client, seeded_db, admin_headers):
    resp = client.post(
        IMPORT_URL,
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_import_headers_only_returns_400(client, seeded_db, admin_headers):
    resp = _post(client, HEADERS, admin_headers)
    assert resp.status_code == 400


def test_import_wrong_file_extension_returns_400(client, seeded_db, admin_headers):
    resp = client.post(
        IMPORT_URL,
        files={"file": ("data.xlsx", io.BytesIO(b"some data"), "application/vnd.openxmlformats")},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_import_missing_headers_returns_400(client, seeded_db, admin_headers):
    bad_headers = "store_id,name,store_type"  # missing many required columns
    resp = _post(client, f"{bad_headers}\nS0001,Test Store,regular", admin_headers)
    assert resp.status_code == 400
    assert "missing" in resp.json()["error"]["message"].lower()


# ===== Row-level validation errors =====

def _bad_row(field_index: int, bad_value: str) -> str:
    """Replace a specific field in VALID_ROW by position."""
    parts = VALID_ROW.split(",")
    parts[field_index] = bad_value
    return ",".join(parts)


def test_import_invalid_store_type_returns_200_with_errors(client, seeded_db, admin_headers):
    row = VALID_ROW.replace(",regular,", ",hypermarket,")
    resp = _post(client, f"{HEADERS}\n{row}", admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert len(data["errors"]) > 0


def test_import_invalid_status_captured(client, seeded_db, admin_headers):
    row = VALID_ROW.replace(",active,", ",broken,")
    resp = _post(client, f"{HEADERS}\n{row}", admin_headers)
    assert resp.json()["success"] is False


def test_import_invalid_phone_captured(client, seeded_db, admin_headers):
    row = VALID_ROW.replace("617-555-0100", "bad-phone")
    resp = _post(client, f"{HEADERS}\n{row}", admin_headers)
    assert resp.json()["success"] is False


def test_import_lat_out_of_range_captured(client, seeded_db, admin_headers):
    row = VALID_ROW.replace("42.3601", "91.0")
    resp = _post(client, f"{HEADERS}\n{row}", admin_headers)
    assert resp.json()["success"] is False


def test_import_invalid_service_captured(client, seeded_db, admin_headers):
    row = VALID_ROW.replace("pharmacy|pickup", "pharmacy|invalid_svc")
    resp = _post(client, f"{HEADERS}\n{row}", admin_headers)
    assert resp.json()["success"] is False


def test_import_hours_close_before_open_captured(client, seeded_db, admin_headers):
    row = VALID_ROW.replace("08:00-22:00,08:00-22:00", "22:00-08:00,08:00-22:00")
    resp = _post(client, f"{HEADERS}\n{row}", admin_headers)
    assert resp.json()["success"] is False


def test_import_invalid_zip_captured(client, seeded_db, admin_headers):
    row = VALID_ROW.replace("02101", "ABCDE")
    resp = _post(client, f"{HEADERS}\n{row}", admin_headers)
    assert resp.json()["success"] is False


def test_import_missing_name_captured(client, seeded_db, admin_headers):
    row = VALID_ROW.replace("Import Store", "")
    resp = _post(client, f"{HEADERS}\n{row}", admin_headers)
    assert resp.json()["success"] is False


def test_import_all_errors_collected_not_just_first(client, seeded_db, admin_headers):
    """If both row 2 and row 3 are invalid, both errors must appear in the report."""
    bad1 = VALID_ROW.replace("regular", "bad_type")
    bad2 = VALID_ROW.replace("IMP001", "IMP002").replace("617-555-0100", "bad")
    resp = _post(client, f"{HEADERS}\n{bad1}\n{bad2}", admin_headers)
    data = resp.json()
    assert data["success"] is False
    row_numbers = {e["row"] for e in data["errors"]}
    assert 2 in row_numbers
    assert 3 in row_numbers


def test_import_error_report_includes_row_number(client, seeded_db, admin_headers):
    row = VALID_ROW.replace("regular", "bad_type")
    resp = _post(client, f"{HEADERS}\n{row}", admin_headers)
    error = resp.json()["errors"][0]
    assert "row" in error
    assert error["row"] == 2  # row 1 = headers, row 2 = first data row


def test_import_nothing_committed_if_any_row_invalid(client, seeded_db, admin_headers, db_session):
    """All-or-nothing: one bad row means no stores are written."""
    good_row = VALID_ROW
    bad_row = VALID_ROW.replace("IMP001", "IMP002").replace("regular", "bad_type")
    _post(client, f"{HEADERS}\n{good_row}\n{bad_row}", admin_headers)
    assert db_session.query(Store).filter_by(store_id="IMP001").first() is None
    assert db_session.query(Store).filter_by(store_id="IMP002").first() is None


def test_import_duplicate_store_id_in_csv_captured(client, seeded_db, admin_headers):
    """Same store_id appearing twice in one CSV must be rejected."""
    resp = _post(client, f"{HEADERS}\n{VALID_ROW}\n{VALID_ROW}", admin_headers)
    data = resp.json()
    assert data["success"] is False
    dup_errors = [e for e in data["errors"] if "Duplicate" in e["message"]]
    assert len(dup_errors) > 0


def test_import_missing_lat_triggers_geocoding(client, seeded_db, admin_headers, db_session):
    """If latitude/longitude are empty, geocoding must be called."""
    row = VALID_ROW.replace("42.3601,-71.0589", ",")
    with patch("app.services.csv_import.geocode_address", return_value=(42.36, -71.05)) as mock_geo:
        resp = _post(client, f"{HEADERS}\n{row}", admin_headers)
    assert resp.json()["success"] is True
    store = db_session.query(Store).filter_by(store_id="IMP001").first()
    assert store is not None
    mock_geo.assert_called_once()


@pytest.mark.skipif(not STORES_1000.exists(), reason="stores_1000.csv not present")
def test_import_1000_rows(client, seeded_db, admin_headers, db_session):
    content = STORES_1000.read_bytes()
    resp = client.post(
        IMPORT_URL,
        files={"file": ("stores_1000.csv", io.BytesIO(content), "text/csv")},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["total"] == 1000
    assert db_session.query(Store).count() == 1000
