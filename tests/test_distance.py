"""Unit tests for distance calculation — no DB or network needed."""
import pytest
from app.services.distance import calculate_bounding_box, calculate_distance


def test_bounding_box_returns_four_values():
    result = calculate_bounding_box(42.3601, -71.0589, 10.0)
    assert len(result) == 4


def test_bounding_box_ordering():
    min_lat, max_lat, min_lon, max_lon = calculate_bounding_box(42.3601, -71.0589, 10.0)
    assert min_lat < max_lat
    assert min_lon < max_lon


def test_bounding_box_clamps_lat_at_poles():
    min_lat, max_lat, _, _ = calculate_bounding_box(89.9, 0.0, 100.0)
    assert max_lat <= 90.0
    min_lat2, _, _, _ = calculate_bounding_box(-89.9, 0.0, 100.0)
    assert min_lat2 >= -90.0


def test_bounding_box_clamps_lon():
    _, _, min_lon, max_lon = calculate_bounding_box(0.0, 179.9, 100.0)
    assert max_lon <= 180.0
    _, _, min_lon2, _ = calculate_bounding_box(0.0, -179.9, 100.0)
    assert min_lon2 >= -180.0


def test_bounding_box_larger_radius_means_bigger_box():
    small = calculate_bounding_box(42.0, -71.0, 10.0)
    large = calculate_bounding_box(42.0, -71.0, 50.0)
    small_lat_span = small[1] - small[0]
    large_lat_span = large[1] - large[0]
    assert large_lat_span > small_lat_span


def test_calculate_distance_known_cities():
    # Boston to NYC geodesic (straight-line) ≈ 190 miles (driving ~215)
    dist = calculate_distance(42.3601, -71.0589, 40.7128, -74.0060)
    assert 185 < dist < 200


def test_calculate_distance_same_point():
    dist = calculate_distance(42.0, -71.0, 42.0, -71.0)
    assert dist == pytest.approx(0.0, abs=0.001)


def test_calculate_distance_is_symmetric():
    d1 = calculate_distance(42.0, -71.0, 40.0, -74.0)
    d2 = calculate_distance(40.0, -74.0, 42.0, -71.0)
    assert d1 == pytest.approx(d2, rel=1e-6)
