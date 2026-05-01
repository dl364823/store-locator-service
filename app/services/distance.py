from math import cos, radians

from geopy.distance import geodesic


def calculate_bounding_box(
    lat: float, lon: float, radius_miles: float
) -> tuple[float, float, float, float]:
    """Return (min_lat, max_lat, min_lon, max_lon) for a bounding box.

    Clamps to valid coordinate ranges so queries near the poles or date line
    don't produce out-of-range values. Longitude wrapping (stores across the
    International Date Line) is not handled — irrelevant for US stores.
    """
    lat_delta = radius_miles / 69.0
    lon_delta = radius_miles / (69.0 * cos(radians(lat))) if cos(radians(lat)) != 0 else 180.0

    min_lat = max(-90.0, lat - lat_delta)
    max_lat = min(90.0, lat + lat_delta)
    min_lon = max(-180.0, lon - lon_delta)
    max_lon = min(180.0, lon + lon_delta)

    return min_lat, max_lat, min_lon, max_lon


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in miles using geopy."""
    return geodesic((lat1, lon1), (lat2, lon2)).miles
