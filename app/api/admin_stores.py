import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import User
from app.dependencies.rbac import require_permission
from app.schemas.store import (
    StoreCreateRequest,
    StoreListResponse,
    StorePatchRequest,
    StoreResponse,
)
from app.services.store import (
    create_store,
    deactivate_store,
    get_store,
    list_stores,
    patch_store,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stores", tags=["Admin — Stores"])


@router.post(
    "",
    response_model=StoreResponse,
    status_code=201,
    summary="Create store",
)
def create(
    body: StoreCreateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("stores:write")),
) -> StoreResponse:
    return create_store(db, body)


@router.get(
    "",
    response_model=StoreListResponse,
    summary="List stores (paginated)",
)
def list_(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Results per page"),
    status: str | None = Query(None, description="Filter by status"),
    store_type: str | None = Query(None, description="Filter by store type"),
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("stores:read")),
) -> StoreListResponse:
    return StoreListResponse(**list_stores(db, page, per_page, status, store_type))


@router.get(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Get store by ID",
)
def get_one(
    store_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("stores:read")),
) -> StoreResponse:
    return get_store(db, store_id)


@router.patch(
    "/{store_id}",
    response_model=StoreResponse,
    summary="Partial update store",
    description=(
        "Update allowed fields only: name, phone, services, status, hours. "
        "Disallowed fields (store_id, latitude, longitude, address_*) are rejected."
    ),
)
def patch(
    store_id: str,
    body: StorePatchRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("stores:write")),
) -> StoreResponse:
    return patch_store(db, store_id, body)


@router.delete(
    "/{store_id}",
    summary="Deactivate store (soft delete)",
)
def delete(
    store_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("stores:write")),
) -> dict:
    return deactivate_store(db, store_id)
