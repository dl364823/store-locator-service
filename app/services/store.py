import logging

from sqlalchemy.orm import Session

from app.db.models import Store, StoreService
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.store import StoreCreateRequest, StorePatchRequest, StoreResponse, StoreHours
from app.services.geocoding import geocode_address
from app.services.hours import get_hours_dict

logger = logging.getLogger(__name__)

_DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _to_response(store: Store) -> StoreResponse:
    return StoreResponse(
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
        services=[s.service_name for s in store.services],
        hours=StoreHours(**get_hours_dict(store)),
        created_at=store.created_at,
        updated_at=store.updated_at,
    )


def _replace_services(db: Session, store_id: str, service_names: list[str]) -> None:
    db.query(StoreService).filter_by(store_id=store_id).delete(synchronize_session=False)
    for name in service_names:
        db.add(StoreService(store_id=store_id, service_name=name))


def get_store_or_404(db: Session, store_id: str) -> Store:
    store = db.query(Store).filter_by(store_id=store_id).first()
    if store is None:
        raise NotFoundError(f"Store '{store_id}' not found.", code="STORE_NOT_FOUND")
    return store


def create_store(db: Session, data: StoreCreateRequest) -> StoreResponse:
    if db.query(Store).filter_by(store_id=data.store_id).first():
        raise ConflictError(
            f"Store '{data.store_id}' already exists.", code="STORE_ALREADY_EXISTS"
        )

    lat, lon = data.latitude, data.longitude
    if lat is None:
        # Auto-geocode from address fields
        address = f"{data.address_street}, {data.address_city}, {data.address_state} {data.address_postal_code}"
        lat, lon = geocode_address(address)
        logger.info("Auto-geocoded store %s → (%.4f, %.4f)", data.store_id, lat, lon)

    hours = {f"hours_{day}": data.hours.get(day) for day in _DAYS}
    store = Store(
        store_id=data.store_id,
        name=data.name,
        store_type=data.store_type,
        status=data.status,
        latitude=lat,
        longitude=lon,
        address_street=data.address_street,
        address_city=data.address_city,
        address_state=data.address_state,
        address_postal_code=data.address_postal_code,
        address_country=data.address_country,
        phone=data.phone,
        **hours,
    )
    db.add(store)
    db.flush()
    _replace_services(db, data.store_id, data.services)
    db.commit()
    db.refresh(store)
    return _to_response(store)


def list_stores(
    db: Session,
    page: int,
    per_page: int,
    status: str | None,
    store_type: str | None,
) -> dict:
    query = db.query(Store)
    if status:
        query = query.filter(Store.status == status)
    if store_type:
        query = query.filter(Store.store_type == store_type)

    total = query.count()
    stores = query.offset((page - 1) * per_page).limit(per_page).all()
    pages = max(1, (total + per_page - 1) // per_page)

    return {
        "stores": [_to_response(s) for s in stores],
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": pages,
    }


def get_store(db: Session, store_id: str) -> StoreResponse:
    return _to_response(get_store_or_404(db, store_id))


def patch_store(db: Session, store_id: str, data: StorePatchRequest) -> StoreResponse:
    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        raise ValidationError("Request body must not be empty.", code="EMPTY_PATCH")

    store = get_store_or_404(db, store_id)

    if "name" in update_data:
        store.name = data.name
    if "phone" in update_data:
        store.phone = data.phone
    if "status" in update_data:
        store.status = data.status
    if "services" in update_data:
        _replace_services(db, store_id, data.services)
    if "hours" in update_data:
        # Partial merge — only update days that are explicitly provided
        for day, value in data.hours.items():
            setattr(store, f"hours_{day}", value)

    db.commit()
    db.refresh(store)
    return _to_response(store)


def deactivate_store(db: Session, store_id: str) -> dict:
    store = get_store_or_404(db, store_id)
    # Idempotent: already inactive stores are silently accepted
    store.status = "inactive"
    db.commit()
    return {"message": f"Store '{store_id}' has been deactivated."}
