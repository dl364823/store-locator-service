"""API tests for POST /api/stores/search. Geocoding is mocked throughout."""
from unittest.mock import patch

import pytest

from app.db.models import Store, StoreService
from app.cache.backend import reset_caches
from scripts.seed import seed_roles_and_permissions, seed_users

# Coordinates for Boston — used as the mock geocoding result
BOSTON = (42.3601, -71.0589)


def _make_store(db, store_id, lat, lon, services=None, store_type="regular",
                status="active", hours_mon="08:00-22:00"):
    store = Store(
        store_id=store_id, name=f"Store {store_id}",
        store_type=store_type, status=status,
        latitude=lat, longitude=lon,
        address_street="1 Main St", address_city="Boston",
        address_state="MA", address_postal_code="02101", address_country="USA",
        phone="617-555-0100",
        hours_mon=hours_mon, hours_tue=hours_mon, hours_wed=hours_mon,
        hours_thu=hours_mon, hours_fri=hours_mon, hours_sat=hours_mon,
        hours_sun=hours_mon,
    )
    db.add(store)
    db.flush()
    for svc in (services or []):
        db.add(StoreService(store_id=store_id, service_name=svc))
    db.commit()
    return store


@pytest.fixture(autouse=True)
def clear_caches():
    reset_caches()
    yield
    reset_caches()


@pytest.fixture()
def nearby_store(db_session):
    return _make_store(db_session, "S0001", 42.3601, -71.0589,
                       services=["pharmacy", "pickup"])


@pytest.fixture()
def far_store(db_session):
    # New York — ~215 miles from Boston
    return _make_store(db_session, "S0002", 40.7128, -74.0060, services=["pharmacy"])


# ---------- search by coordinates ----------

def test_search_by_coords_returns_200(client, nearby_store):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589
    })
    assert resp.status_code == 200


def test_search_finds_nearby_store(client, nearby_store, far_store):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589, "radius_miles": 10
    })
    data = resp.json()
    ids = [r["store_id"] for r in data["results"]]
    assert "S0001" in ids
    assert "S0002" not in ids


def test_search_includes_distance_and_is_open_now(client, nearby_store):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589
    })
    result = resp.json()["results"][0]
    assert "distance_miles" in result
    assert "is_open_now" in result


def test_search_sorted_nearest_first(client, db_session):
    _make_store(db_session, "NEAR", 42.3601, -71.0589)   # distance ≈ 0
    _make_store(db_session, "MED", 42.4001, -71.0589)    # ~2.7 miles away
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589, "radius_miles": 20
    })
    distances = [r["distance_miles"] for r in resp.json()["results"]]
    assert distances == sorted(distances)


def test_search_empty_result_when_no_stores_in_radius(client, far_store):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589, "radius_miles": 10
    })
    data = resp.json()
    assert resp.status_code == 200
    assert data["results"] == []
    assert data["count"] == 0


def test_search_excludes_inactive_stores(client, db_session):
    _make_store(db_session, "INACTIVE", 42.3601, -71.0589, status="inactive")
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589
    })
    ids = [r["store_id"] for r in resp.json()["results"]]
    assert "INACTIVE" not in ids


# ---------- search by address (mocked geocoding) ----------

def test_search_by_address(client, nearby_store):
    with patch("app.services.search.geocode_address", return_value=BOSTON):
        resp = client.post("/api/stores/search", json={"address": "123 Main St, Boston, MA"})
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


def test_search_by_address_not_found_returns_400(client):
    from app.exceptions import ValidationError
    with patch(
        "app.services.search.geocode_address",
        side_effect=ValidationError("Address not found", code="LOCATION_NOT_FOUND"),
    ):
        resp = client.post("/api/stores/search", json={"address": "Nowhere Land"})
    assert resp.status_code == 400


def test_search_geocoding_failure_returns_502(client):
    from app.exceptions import ExternalServiceError
    with patch(
        "app.services.search.geocode_address",
        side_effect=ExternalServiceError("Nominatim down"),
    ):
        resp = client.post("/api/stores/search", json={"address": "Boston"})
    assert resp.status_code == 502


# ---------- search by postal code ----------

def test_search_by_postal_code(client, nearby_store):
    with patch("app.services.search.geocode_postal_code", return_value=BOSTON):
        resp = client.post("/api/stores/search", json={"postal_code": "02101"})
    assert resp.status_code == 200


# ---------- filters ----------

def test_filter_services_and_logic(client, db_session):
    """Store must have ALL requested services."""
    _make_store(db_session, "BOTH", 42.3601, -71.0589, services=["pharmacy", "pickup"])
    _make_store(db_session, "PHARM_ONLY", 42.3601, -71.0589, services=["pharmacy"])
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589,
        "services": ["pharmacy", "pickup"],
    })
    ids = [r["store_id"] for r in resp.json()["results"]]
    assert "BOTH" in ids
    assert "PHARM_ONLY" not in ids


def test_filter_store_types_or_logic(client, db_session):
    """OR: store matches any of the requested types."""
    _make_store(db_session, "FLAG", 42.3601, -71.0589, store_type="flagship")
    _make_store(db_session, "EXPR", 42.3601, -71.0589, store_type="express")
    _make_store(db_session, "REG",  42.3601, -71.0589, store_type="regular")
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589,
        "store_types": ["flagship", "express"],
    })
    ids = [r["store_id"] for r in resp.json()["results"]]
    assert "FLAG" in ids
    assert "EXPR" in ids
    assert "REG" not in ids


def test_filter_open_now_excludes_closed_stores(client, db_session):
    _make_store(db_session, "OPEN",  42.3601, -71.0589, hours_mon="00:00-23:59")
    _make_store(db_session, "SHUT",  42.3601, -71.0589, hours_mon="closed")
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589, "open_now": True,
    })
    ids = [r["store_id"] for r in resp.json()["results"]]
    assert "OPEN" in ids
    assert "SHUT" not in ids


def test_combined_filters(client, db_session):
    _make_store(db_session, "MATCH",    42.3601, -71.0589,
                services=["pharmacy"], store_type="regular", hours_mon="00:00-23:59")
    _make_store(db_session, "NO_SVC",   42.3601, -71.0589,
                services=[], store_type="regular", hours_mon="00:00-23:59")
    _make_store(db_session, "WRONG_TYPE", 42.3601, -71.0589,
                services=["pharmacy"], store_type="flagship", hours_mon="00:00-23:59")
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589,
        "services": ["pharmacy"], "store_types": ["regular"], "open_now": True,
    })
    ids = [r["store_id"] for r in resp.json()["results"]]
    assert "MATCH" in ids
    assert "NO_SVC" not in ids
    assert "WRONG_TYPE" not in ids


# ---------- input validation ----------

def test_missing_location_returns_422(client):
    resp = client.post("/api/stores/search", json={"radius_miles": 10})
    assert resp.status_code == 422


def test_ambiguous_location_returns_422(client):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.0, "longitude": -71.0, "address": "Boston"
    })
    assert resp.status_code == 422


def test_radius_zero_returns_422(client):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.0, "longitude": -71.0, "radius_miles": 0
    })
    assert resp.status_code == 422


def test_radius_negative_returns_422(client):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.0, "longitude": -71.0, "radius_miles": -5
    })
    assert resp.status_code == 422


def test_radius_over_100_returns_422(client):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.0, "longitude": -71.0, "radius_miles": 101
    })
    assert resp.status_code == 422


def test_lat_out_of_range_returns_422(client):
    resp = client.post("/api/stores/search", json={
        "latitude": 91.0, "longitude": -71.0
    })
    assert resp.status_code == 422


def test_lon_out_of_range_returns_422(client):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.0, "longitude": 181.0
    })
    assert resp.status_code == 422


def test_invalid_service_returns_422(client):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.0, "longitude": -71.0, "services": ["invalid_service"]
    })
    assert resp.status_code == 422


def test_invalid_store_type_returns_422(client):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.0, "longitude": -71.0, "store_types": ["hypermarket"]
    })
    assert resp.status_code == 422


def test_invalid_postal_code_format_returns_422(client):
    resp = client.post("/api/stores/search", json={"postal_code": "ABCDE"})
    assert resp.status_code == 422


def test_only_lat_without_lon_returns_422(client):
    resp = client.post("/api/stores/search", json={"latitude": 42.0})
    assert resp.status_code == 422


def test_response_metadata(client, nearby_store):
    resp = client.post("/api/stores/search", json={
        "latitude": 42.3601, "longitude": -71.0589, "radius_miles": 5
    })
    data = resp.json()
    assert "search_location" in data
    assert "filters_applied" in data
    assert data["filters_applied"]["radius_miles"] == 5
