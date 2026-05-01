import threading
from typing import Any

from cachetools import TTLCache

from app.config import get_settings


class InMemoryCache:
    """Thread-safe TTL cache backed by cachetools.TTLCache.

    The Redis-ready interface (get/set/delete/clear) means swapping to a Redis
    backend in production only requires a new class that satisfies this same
    interface.
    """

    def __init__(self, ttl_seconds: int, maxsize: int = 10_000):
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl_seconds)
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._cache[key] = value

    def delete(self, key: str) -> None:
        with self._lock:
            self._cache.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()


# Module-level singletons — created once per process
_geocoding_cache: InMemoryCache | None = None
_search_cache: InMemoryCache | None = None


def get_geocoding_cache() -> InMemoryCache:
    global _geocoding_cache
    if _geocoding_cache is None:
        ttl = get_settings().geocoding_cache_ttl_days * 86_400
        _geocoding_cache = InMemoryCache(ttl_seconds=ttl)
    return _geocoding_cache


def get_search_cache() -> InMemoryCache:
    global _search_cache
    if _search_cache is None:
        _search_cache = InMemoryCache(ttl_seconds=get_settings().search_cache_ttl_seconds)
    return _search_cache


def reset_caches() -> None:
    """Clear all caches — used in tests to prevent cross-test pollution."""
    global _geocoding_cache, _search_cache
    if _geocoding_cache:
        _geocoding_cache.clear()
    if _search_cache:
        _search_cache.clear()
