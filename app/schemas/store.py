import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.config import get_settings
from app.schemas.search import StoreHours

_PHONE_RE = re.compile(r"^\d{3}-\d{3}-\d{4}$")
_VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}


def _validate_phone(v: str) -> str:
    if not _PHONE_RE.match(v):
        raise ValueError("phone must match format XXX-XXX-XXXX")
    return v


def _validate_services(v: list[str]) -> list[str]:
    allowed = get_settings().allowed_services
    invalid = [s for s in v if s not in allowed]
    if invalid:
        raise ValueError(f"Invalid services: {invalid}. Allowed: {allowed}")
    return v


def _validate_store_type(v: str) -> str:
    allowed = get_settings().allowed_store_types
    if v not in allowed:
        raise ValueError(f"store_type must be one of {allowed}")
    return v


def _validate_status(v: str) -> str:
    allowed = get_settings().allowed_store_statuses
    if v not in allowed:
        raise ValueError(f"status must be one of {allowed}")
    return v


def _validate_hours_dict(v: dict) -> dict:
    from app.services.hours import validate_hours_string

    invalid_days = [d for d in v if d not in _VALID_DAYS]
    if invalid_days:
        raise ValueError(f"Invalid day keys: {invalid_days}. Must be one of {sorted(_VALID_DAYS)}")

    for day, val in v.items():
        if val is not None and not validate_hours_string(val):
            raise ValueError(
                f"hours.{day}: invalid format '{val}'. Use 'closed' or 'HH:MM-HH:MM' "
                "with close time strictly after open time."
            )
    return v


# ---------- Create ----------

class StoreCreateRequest(BaseModel):
    store_id: str
    name: str
    store_type: str
    status: str = "active"
    latitude: float | None = None
    longitude: float | None = None
    address_street: str
    address_city: str
    address_state: str
    address_postal_code: str
    address_country: str = "USA"
    phone: str
    services: list[str] = []
    hours: dict[str, str | None] = {}

    @field_validator("store_id")
    @classmethod
    def store_id_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("store_id must not be empty")
        if len(v) > 10:
            raise ValueError("store_id must be 10 characters or fewer")
        return v

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name must not be empty")
        if len(v) > 255:
            raise ValueError("name must be 255 characters or fewer")
        return v

    @field_validator("store_type")
    @classmethod
    def validate_store_type(cls, v: str) -> str:
        return _validate_store_type(v)

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        return _validate_status(v)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone(v)

    @field_validator("services")
    @classmethod
    def validate_services(cls, v: list[str]) -> list[str]:
        return _validate_services(v)

    @field_validator("address_state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        if len(v) != 2:
            raise ValueError("address_state must be a 2-letter state code")
        return v.upper()

    @field_validator("address_postal_code")
    @classmethod
    def validate_postal(cls, v: str) -> str:
        if not re.match(r"^\d{5}$", v):
            raise ValueError("address_postal_code must be a 5-digit ZIP code")
        return v

    @field_validator("latitude")
    @classmethod
    def validate_lat(cls, v: float | None) -> float | None:
        if v is not None and not -90 <= v <= 90:
            raise ValueError("latitude must be between -90 and 90")
        return v

    @field_validator("longitude")
    @classmethod
    def validate_lon(cls, v: float | None) -> float | None:
        if v is not None and not -180 <= v <= 180:
            raise ValueError("longitude must be between -180 and 180")
        return v

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, v: dict) -> dict:
        return _validate_hours_dict(v)

    @model_validator(mode="after")
    def lat_lon_both_or_neither(self) -> "StoreCreateRequest":
        has_lat = self.latitude is not None
        has_lon = self.longitude is not None
        if has_lat != has_lon:
            raise ValueError("Provide both latitude and longitude, or neither (address will be geocoded).")
        return self


# ---------- Patch ----------

class StorePatchRequest(BaseModel):
    # extra="forbid" causes Pydantic to raise a validation error if any field
    # not in this list is present — this is the explicit rejection of disallowed
    # fields (store_id, latitude, longitude, address_*) required by the spec.
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    phone: str | None = None
    services: list[str] | None = None
    status: str | None = None
    # hours: partial update — only days provided are changed; others preserved
    hours: dict[str, str | None] | None = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("name must not be empty")
            if len(v) > 255:
                raise ValueError("name must be 255 characters or fewer")
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_phone(v)
        return v

    @field_validator("services")
    @classmethod
    def validate_services(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            return _validate_services(v)
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        if v is not None:
            return _validate_status(v)
        return v

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, v: dict | None) -> dict | None:
        if v is not None:
            return _validate_hours_dict(v)
        return v


# ---------- Responses ----------

class StoreResponse(BaseModel):
    store_id: str
    name: str
    store_type: str
    status: str
    latitude: float
    longitude: float
    address_street: str
    address_city: str
    address_state: str
    address_postal_code: str
    address_country: str
    phone: str
    services: list[str]
    hours: StoreHours
    created_at: datetime
    updated_at: datetime


class StoreListResponse(BaseModel):
    stores: list[StoreResponse]
    total: int
    page: int
    per_page: int
    pages: int
