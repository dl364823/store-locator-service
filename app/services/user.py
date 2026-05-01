import logging
import re

from sqlalchemy.orm import Session

from app.db.models import Role, User
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.schemas.user import UserCreateRequest, UserResponse, UserUpdateRequest
from app.services.auth import hash_password

logger = logging.getLogger(__name__)

_USER_ID_RE = re.compile(r"^U(\d+)$")


def _next_user_id(db: Session) -> str:
    """Generate the next sequential user ID (U001, U002, …)."""
    users = db.query(User).all()
    max_num = 0
    for user in users:
        m = _USER_ID_RE.match(user.user_id)
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"U{max_num + 1:03d}"


def _get_role_or_400(db: Session, role_name: str) -> Role:
    role = db.query(Role).filter_by(name=role_name).first()
    if role is None:
        raise ValidationError(
            f"Role '{role_name}' not found. Have you run the seed script?",
            code="ROLE_NOT_FOUND",
        )
    return role


def _to_response(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.user_id,
        email=user.email,
        role=user.role_name,
        status=user.status,
        must_change_password=user.must_change_password,
        created_at=user.created_at,
    )


def _get_user_or_404(db: Session, user_id: str) -> User:
    user = db.query(User).filter_by(user_id=user_id).first()
    if user is None:
        raise NotFoundError(f"User '{user_id}' not found.", code="USER_NOT_FOUND")
    return user


def create_user(db: Session, data: UserCreateRequest) -> UserResponse:
    if db.query(User).filter_by(email=data.email).first():
        raise ConflictError(
            f"A user with email '{data.email}' already exists.", code="USER_ALREADY_EXISTS"
        )

    role = _get_role_or_400(db, data.role)
    user_id = _next_user_id(db)

    user = User(
        user_id=user_id,
        email=data.email,
        password_hash=hash_password(data.password),
        role_id=role.id,
        status="active",
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("Created user %s (%s) with role %s", user_id, data.email, data.role)
    return _to_response(user)


def list_users(db: Session) -> dict:
    users = db.query(User).all()
    return {"users": [_to_response(u) for u in users], "total": len(users)}


def update_user(db: Session, user_id: str, data: UserUpdateRequest) -> UserResponse:
    update_fields = data.model_dump(exclude_unset=True)
    if not update_fields:
        raise ValidationError("Request body must not be empty.", code="EMPTY_UPDATE")

    user = _get_user_or_404(db, user_id)

    if "role" in update_fields and data.role is not None:
        role = _get_role_or_400(db, data.role)
        user.role_id = role.id

    if "status" in update_fields and data.status is not None:
        user.status = data.status

    db.commit()
    db.refresh(user)
    logger.info("Updated user %s: %s", user_id, update_fields)
    return _to_response(user)


def deactivate_user(db: Session, user_id: str) -> dict:
    user = _get_user_or_404(db, user_id)
    # Idempotent: already-inactive is silently accepted
    user.status = "inactive"
    db.commit()
    return {"message": f"User '{user_id}' has been deactivated."}
