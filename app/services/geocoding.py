import logging

import httpx

from app.cache.backend import get_geocoding_cache
from app.cache.keys import geocoding_key
from app.exceptions import ExternalServiceError, ValidationError

logger = logging.getLogger(__name__)

_NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"
# Nominatim ToS requires a descriptive User-Agent
_HEADERS = {"User-Agent": "StoreLocatorAPI/1.0"}


def _fetch_nominatim(params: dict) -> list[dict]:
    """Call Nominatim and return the raw JSON list. Raises ExternalServiceError on failure."""
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(_NOMINATIM_BASE, params=params, headers=_HEADERS)
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        logger.error("Nominatim timeout with params: %s", params)
        raise ExternalServiceError("Geocoding service timed out. Please try again.")
    except httpx.HTTPStatusError as exc:
        logger.error("Nominatim HTTP %s for params: %s", exc.response.status_code, params)
        raise ExternalServiceError("Geocoding service returned an unexpected error.")
    except Exception:
        logger.exception("Unexpected error calling Nominatim")
        raise ExternalServiceError("Geocoding service is temporarily unavailable.")


def geocode_address(address: str) -> tuple[float, float]:
    """Convert a free-text address to (lat, lon), with 30-day caching."""
    if not address or not address.strip():
        raise ValidationError("Address must not be empty.", code="INVALID_ADDRESS")

    cache = get_geocoding_cache()
    key = geocoding_key(f"addr:{address}")
    cached = cache.get(key)
    if cached is not None:
        return cached

    results = _fetch_nominatim({"q": address.strip(), "format": "json", "limit": 1})
    if not results:
        raise ValidationError(
            f"Address not found: '{address}'. Try a more specific address.",
            code="LOCATION_NOT_FOUND",
        )

    coords = (float(results[0]["lat"]), float(results[0]["lon"]))
    cache.set(key, coords)
    return coords


def geocode_postal_code(postal_code: str) -> tuple[float, float]:
    """Convert a US 5-digit ZIP code to (lat, lon), with 30-day caching."""
    if not postal_code or not postal_code.strip():
        raise ValidationError("Postal code must not be empty.", code="INVALID_POSTAL_CODE")

    cache = get_geocoding_cache()
    key = geocoding_key(f"zip:{postal_code}")
    cached = cache.get(key)
    if cached is not None:
        return cached

    results = _fetch_nominatim(
        {"postalcode": postal_code.strip(), "countrycodes": "us", "format": "json", "limit": 1}
    )
    if not results:
        raise ValidationError(
            f"Postal code not found: '{postal_code}'.",
            code="LOCATION_NOT_FOUND",
        )

    coords = (float(results[0]["lat"]), float(results[0]["lon"]))
    cache.set(key, coords)
    return coords
