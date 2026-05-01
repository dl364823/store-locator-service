import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.base import get_db
from app.db.models import User
from app.dependencies.rbac import require_permission
from app.schemas.user import UserCreateRequest, UserListResponse, UserResponse, UserUpdateRequest
from app.services.user import create_user, deactivate_user, list_users, update_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["Admin — Users"])


@router.post(
    "",
    response_model=UserResponse,
    status_code=201,
    summary="Create user (admin only)",
)
def create(
    body: UserCreateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("users:write")),
) -> UserResponse:
    return create_user(db, body)


@router.get(
    "",
    response_model=UserListResponse,
    summary="List users (admin only)",
)
def list_(
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("users:read")),
) -> UserListResponse:
    return UserListResponse(**list_users(db))


@router.put(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user role or status (admin only)",
)
def update(
    user_id: str,
    body: UserUpdateRequest,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("users:write")),
) -> UserResponse:
    return update_user(db, user_id, body)


@router.delete(
    "/{user_id}",
    summary="Deactivate user (admin only, soft delete)",
)
def delete(
    user_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_permission("users:write")),
) -> dict:
    return deactivate_user(db, user_id)
