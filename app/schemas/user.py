import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.config import get_settings

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserCreateRequest(BaseModel):
    email: str
    password: str
    role: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or not _EMAIL_RE.match(v):
            raise ValueError("email must be a valid email address")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v or len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        allowed = get_settings().allowed_roles
        if v not in allowed:
            raise ValueError(f"role must be one of {allowed}")
        return v


class UserUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str | None = None
    status: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str | None) -> str | None:
        if v is not None:
            allowed = get_settings().allowed_roles
            if v not in allowed:
                raise ValueError(f"role must be one of {allowed}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None and v not in ("active", "inactive"):
            raise ValueError("status must be 'active' or 'inactive'")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdateRequest":
        provided = {k for k, val in self.model_dump(exclude_unset=True).items() if val is not None}
        if not provided:
            raise ValueError("At least one field (role or status) must be provided.")
        return self


class UserResponse(BaseModel):
    user_id: str
    email: str
    role: str
    status: str
    must_change_password: bool
    created_at: datetime


class UserListResponse(BaseModel):
    users: list[UserResponse]
    total: int
