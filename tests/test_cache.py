"""Tests for caching behaviour and rate limiting."""
from unittest.mock import MagicMock, patch

import pytest

from app.cache.backend import InMemoryCache, RedisCache, reset_caches, get_geocoding_cache
from app.cache.keys import geocoding_key, search_key
from app.middleware.rate_limit import limiter

SEARCH_URL = "/api/stores/search"
BOSTON_COORDS = {"latitude": 42.3601, "longitude": -71.0589}


@pytest.fixture(autouse=True)
def clear_caches_fixture():
    reset_caches()
    yield
    reset_caches()


# ===== InMemoryCache unit tests =====

def test_inmemory_get_miss():
    cache = InMemoryCache(ttl_seconds=60)
    assert cache.get("missing") is None


def test_inmemory_set_and_get():
    cache = InMemoryCache(ttl_seconds=60)
    cache.set("k", {"value": 42})
    assert cache.get("k") == {"value": 42}


def test_inmemory_delete():
    cache = InMemoryCache(ttl_seconds=60)
    cache.set("k", "v")
    cache.delete("k")
    assert cache.get("k") is None


def test_inmemory_clear():
    cache = InMemoryCache(ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_inmemory_overwrite():
    cache = InMemoryCache(ttl_seconds=60)
    cache.set("k", "first")
    cache.set("k", "second")
    assert cache.get("k") == "second"


# ===== RedisCache fallback behaviour =====

def test_redis_cache_get_returns_none_when_unavailable():
    """If Redis connection fails at init, get() must return None (not crash)."""
    cache = RedisCache(redis_url="redis://localhost:9999/0", ttl_seconds=60)
    assert cache.get("any-key") is None


def test_redis_cache_set_is_noop_when_unavailable():
    cache = RedisCache(redis_url="redis://localhost:9999/0", ttl_seconds=60)
    cache.set("k", "v")  # must not raise


def test_redis_cache_clear_is_noop_when_unavailable():
    cache = RedisCache(redis_url="redis://localhost:9999/0", ttl_seconds=60)
    cache.clear()  # must not raise


def test_redis_cache_get_error_returns_none():
    """If Redis raises on GET, return None instead of crashing."""
    cache = RedisCache.__new__(RedisCache)
    mock_client = MagicMock()
    mock_client.get.side_effect = Exception("connection lost")
    cache._client = mock_client
    cache._ttl = 60
    assert cache.get("k") is None


def test_redis_cache_set_error_is_silent():
    cache = RedisCache.__new__(RedisCache)
    mock_client = MagicMock()
    mock_client.setex.side_effect = Exception("connection lost")
    cache._client = mock_client
    cache._ttl = 60
    cache.set("k", "v")  # must not raise


# ===== Geocoding cache =====

def test_geocoding_cache_hit_avoids_second_network_call():
    """Calling geocode_address twice with the same input hits Nominatim once."""
    from app.services.geocoding import geocode_address

    with patch(
        "app.services.geocoding._fetch_nominatim",
        return_value=[{"lat": "42.36", "lon": "-71.05"}],
    ) as mock:
        result1 = geocode_address("123 Main St, Boston, MA")
        result2 = geocode_address("123 Main St, Boston, MA")

    assert result1 == result2
    mock.assert_called_once()  # network called only on first miss


def test_geocoding_cache_different_queries_both_called():
    from app.services.geocoding import geocode_address

    with patch(
        "app.services.geocoding._fetch_nominatim",
        return_value=[{"lat": "42.36", "lon": "-71.05"}],
    ) as mock:
        geocode_address("123 Main St, Boston")
        geocode_address("456 Oak Ave, Cambridge")

    assert mock.call_count == 2


def test_geocoding_cache_key_is_case_insensitive():
    key1 = geocoding_key("addr:123 Main St, Boston")
    key2 = geocoding_key("addr:123 MAIN ST, BOSTON")
    assert key1 == key2


# ===== Search result caching =====

def test_search_cache_hit_returns_same_result(client, db_session):
    """Second identical search should return same result from cache."""
    from app.db.models import Store
    store = Store(
        store_id="CACHETEST", name="Cache Store", store_type="regular", status="active",
        latitude=42.3601, longitude=-71.0589,
        address_street="1 St", address_city="Boston", address_state="MA",
        address_postal_code="02101", address_country="USA", phone="617-555-0100",
        hours_mon="08:00-22:00", hours_tue=None, hours_wed=None,
        hours_thu=None, hours_fri=None, hours_sat=None, hours_sun=None,
    )
    db_session.add(store)
    db_session.commit()

    r1 = client.post(SEARCH_URL, json=BOSTON_COORDS)
    r2 = client.post(SEARCH_URL, json=BOSTON_COORDS)
    assert r1.status_code == r2.status_code == 200
    assert r1.json() == r2.json()


def test_search_cache_invalidated_after_store_deactivated(client, seeded_db, admin_headers, db_session):
    """After deactivating a store, the next search must reflect the change."""
    from app.db.models import Store
    store = Store(
        store_id="INVALTEST", name="To Deactivate", store_type="regular", status="active",
        latitude=42.3601, longitude=-71.0589,
        address_street="1 St", address_city="Boston", address_state="MA",
        address_postal_code="02101", address_country="USA", phone="617-555-0100",
        hours_mon=None, hours_tue=None, hours_wed=None,
        hours_thu=None, hours_fri=None, hours_sat=None, hours_sun=None,
    )
    db_session.add(store)
    db_session.commit()

    # First search — populates cache
    r1 = client.post(SEARCH_URL, json=BOSTON_COORDS)
    assert any(s["store_id"] == "INVALTEST" for s in r1.json()["results"])

    # Deactivate via admin endpoint (must clear cache)
    client.delete("/api/admin/stores/INVALTEST", headers=admin_headers)

    # Second search — cache was cleared, so DB is re-queried
    r2 = client.post(SEARCH_URL, json=BOSTON_COORDS)
    assert not any(s["store_id"] == "INVALTEST" for s in r2.json()["results"])


def test_search_cache_invalidated_after_store_patched(client, seeded_db, admin_headers, db_session):
    """After patching a store, search results reflect the updated name."""
    from app.db.models import Store
    store = Store(
        store_id="PATCHCACHE", name="Original Name", store_type="regular", status="active",
        latitude=42.3601, longitude=-71.0589,
        address_street="1 St", address_city="Boston", address_state="MA",
        address_postal_code="02101", address_country="USA", phone="617-555-0100",
        hours_mon=None, hours_tue=None, hours_wed=None,
        hours_thu=None, hours_fri=None, hours_sat=None, hours_sun=None,
    )
    db_session.add(store)
    db_session.commit()

    # Populate cache
    client.post(SEARCH_URL, json=BOSTON_COORDS)

    # PATCH the store (clears cache)
    client.patch(
        "/api/admin/stores/PATCHCACHE",
        json={"name": "Updated Name"},
        headers=admin_headers,
    )

    # New search hits DB and returns updated name
    r = client.post(SEARCH_URL, json=BOSTON_COORDS)
    names = [s["name"] for s in r.json()["results"] if s["store_id"] == "PATCHCACHE"]
    assert names == ["Updated Name"]


def test_open_now_results_not_cached(client, db_session):
    """open_now=True searches must never be cached (time-sensitive)."""
    from app.cache.backend import get_search_cache
    from app.cache.keys import search_key

    r = client.post(SEARCH_URL, json={**BOSTON_COORDS, "open_now": True})
    assert r.status_code == 200

    cache = get_search_cache()
    key = search_key(42.3601, -71.0589, 10.0, [], [], True)
    assert cache.get(key) is None  # must not have been stored


# ===== Rate limiting =====

def test_rate_limit_returns_429_after_limit_exceeded(client, db_session):
    """Exceeding 10 req/min must return 429 with Retry-After header."""
    limiter.enabled = True
    try:
        # Reset the in-memory storage counters
        limiter._storage.reset()
    except Exception:
        pass

    try:
        responses = [
            client.post(SEARCH_URL, json=BOSTON_COORDS)
            for _ in range(12)  # 10/minute limit
        ]
        status_codes = [r.status_code for r in responses]
        assert 429 in status_codes, f"Expected 429 in {status_codes}"

        rate_limited = [r for r in responses if r.status_code == 429]
        assert "Retry-After" in rate_limited[0].headers
        body = rate_limited[0].json()
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    finally:
        limiter.enabled = False
        try:
            limiter._storage.reset()
        except Exception:
            pass


def test_search_cache_key_rounds_coordinates():
    """Same location at sub-11m precision should hit the same cache entry."""
    k1 = search_key(42.36010, -71.05890, 10.0, [], [], False)
    k2 = search_key(42.36011, -71.05891, 10.0, [], [], False)
    assert k1 == k2  # 4 decimal places → same key
