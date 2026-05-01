import logging

from sqlalchemy.orm import Session

from app.db.models import Store
from app.schemas.search import (
    FiltersApplied,
    SearchLocation,
    SearchRequest,
    SearchResponse,
    StoreHours,
    StoreSearchResult,
)
from app.services.distance import calculate_bounding_box, calculate_distance
from app.services.geocoding import geocode_address, geocode_postal_code
from app.services.hours import get_hours_dict, is_store_open

logger = logging.getLogger(__name__)


def _resolve_coordinates(req: SearchRequest) -> tuple[float, float]:
    if req.latitude is not None and req.longitude is not None:
        return req.latitude, req.longitude
    if req.address:
        return geocode_address(req.address)
    return geocode_postal_code(req.postal_code)  # type: ignore[arg-type]


def _query_bbox(
    db: Session,
    min_lat: float,
    max_lat: float,
    min_lon: float,
    max_lon: float,
    store_types: list[str],
) -> list[Store]:
    query = db.query(Store).filter(
        Store.status == "active",
        Store.latitude >= min_lat,
        Store.latitude <= max_lat,
        Store.longitude >= min_lon,
        Store.longitude <= max_lon,
    )
    if store_types:
        query = query.filter(Store.store_type.in_(store_types))
    return query.all()


def _to_result(store: Store, distance: float) -> StoreSearchResult:
    service_names = [s.service_name for s in store.services]
    hours = get_hours_dict(store)
    return StoreSearchResult(
        store_id=store.store_id,
        name=store.name,
        store_type=store.store_type,
        status=store.status,
        latitude=float(store.latitude),
        longitude=float(store.longitude),
        address_street=store.address_street,
        address_city=store.address_city,
        address_state=store.address_state,
        address_postal_code=store.address_postal_code,
        address_country=store.address_country,
        phone=store.phone,
        services=service_names,
        hours=StoreHours(**hours),
        distance_miles=round(distance, 4),
        is_open_now=is_store_open(store),
    )


def execute_search(db: Session, req: SearchRequest) -> SearchResponse:
    lat, lon = _resolve_coordinates(req)

    min_lat, max_lat, min_lon, max_lon = calculate_bounding_box(lat, lon, req.radius_miles)
    candidates = _query_bbox(db, min_lat, max_lat, min_lon, max_lon, req.store_types)

    # Haversine exact-distance filter (bounding box is a square, not a circle)
    within_radius: list[tuple[Store, float]] = []
    for store in candidates:
        dist = calculate_distance(lat, lon, float(store.latitude), float(store.longitude))
        if dist <= req.radius_miles:
            within_radius.append((store, dist))

    # Services AND filter — store must have every requested service
    if req.services:
        req_svcs = set(req.services)
        within_radius = [
            (s, d)
            for s, d in within_radius
            if req_svcs.issubset({svc.service_name for svc in s.services})
        ]

    # open_now filter
    if req.open_now:
        within_radius = [(s, d) for s, d in within_radius if is_store_open(s)]

    within_radius.sort(key=lambda x: x[1])

    results = [_to_result(store, dist) for store, dist in within_radius]

    return SearchResponse(
        results=results,
        count=len(results),
        search_location=SearchLocation(latitude=lat, longitude=lon),
        filters_applied=FiltersApplied(
            radius_miles=req.radius_miles,
            services=req.services,
            store_types=req.store_types,
            open_now=req.open_now,
        ),
    )
