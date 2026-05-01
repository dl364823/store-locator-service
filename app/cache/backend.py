import logging
import pickle
import threading
from typing import Any

from cachetools import TTLCache

from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------- In-memory backend ----------

class InMemoryCache:
    """Thread-safe TTL cache. Redis-compatible interface for easy swapping."""

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


# ---------- Redis backend ----------

class RedisCache:
    """Redis-backed cache with the same interface as InMemoryCache.

    Fails open: any Redis error is logged and silently ignored so the
    application continues to work without caching rather than crashing.
    """

    def __init__(self, redis_url: str, ttl_seconds: int):
        self._ttl = ttl_seconds
        self._client = None
        try:
            import redis

            client = redis.from_url(redis_url, decode_responses=False)
            client.ping()  # confirm connectivity at startup
            self._client = client
            logger.info("Redis cache connected: %s", redis_url)
        except Exception:
            logger.warning(
                "Redis unavailable at '%s'; falling back to no-op caching.", redis_url
            )

    def _is_available(self) -> bool:
        return self._client is not None

    def get(self, key: str) -> Any | None:
        if not self._is_available():
            return None
        try:
            raw = self._client.get(key)
            return pickle.loads(raw) if raw is not None else None
        except Exception:
            logger.warning("Redis GET failed for key '%s'", key)
            return None

    def set(self, key: str, value: Any) -> None:
        if not self._is_available():
            return
        try:
            self._client.setex(key, self._ttl, pickle.dumps(value))
        except Exception:
            logger.warning("Redis SET failed for key '%s'", key)

    def delete(self, key: str) -> None:
        if not self._is_available():
            return
        try:
            self._client.delete(key)
        except Exception:
            logger.warning("Redis DELETE failed for key '%s'", key)

    def clear(self) -> None:
        if not self._is_available():
            return
        try:
            self._client.flushdb()
        except Exception:
            logger.warning("Redis FLUSHDB failed")


# ---------- Singletons ----------

_geocoding_cache: InMemoryCache | RedisCache | None = None
_search_cache: InMemoryCache | RedisCache | None = None


def _build_cache(ttl_seconds: int, redis_url: str | None, label: str):
    if redis_url:
        logger.info("Using Redis for %s cache", label)
        return RedisCache(redis_url=redis_url, ttl_seconds=ttl_seconds)
    return InMemoryCache(ttl_seconds=ttl_seconds)


def get_geocoding_cache() -> InMemoryCache | RedisCache:
    global _geocoding_cache
    if _geocoding_cache is None:
        settings = get_settings()
        _geocoding_cache = _build_cache(
            ttl_seconds=settings.geocoding_cache_ttl_days * 86_400,
            redis_url=settings.redis_url,
            label="geocoding",
        )
    return _geocoding_cache


def get_search_cache() -> InMemoryCache | RedisCache:
    global _search_cache
    if _search_cache is None:
        settings = get_settings()
        _search_cache = _build_cache(
            ttl_seconds=settings.search_cache_ttl_seconds,
            redis_url=settings.redis_url,
            label="search",
        )
    return _search_cache


def reset_caches() -> None:
    """Clear all caches — used in tests to prevent cross-test pollution."""
    global _geocoding_cache, _search_cache
    if _geocoding_cache:
        _geocoding_cache.clear()
    if _search_cache:
        _search_cache.clear()
