from fastapi import Depends

from app.db.models import User
from app.dependencies.auth import get_current_user
from app.exceptions import AuthorizationError


def require_permission(permission: str):
    """Dependency factory. Injects the current user and checks a named permission.

    Usage:
        @router.post("/admin/stores")
        def create_store(user: User = Depends(require_permission("stores:write"))):
            ...

    Raises:
        AuthenticationError (401) — propagated from get_current_user if token invalid
        AuthorizationError  (403) — if user's role lacks the required permission
    """
    def _check(current_user: User = Depends(get_current_user)) -> User:
        if permission not in current_user.permission_names:
            raise AuthorizationError(
                f"You do not have permission to perform this action.",
                code="FORBIDDEN",
            )
        return current_user

    # Give the inner function a unique name per permission so FastAPI's
    # dependency graph treats each call as a distinct dependency.
    _check.__name__ = f"require_{permission.replace(':', '_')}"
    return _check
