import re

from pydantic import BaseModel, field_validator, model_validator

from app.config import get_settings

_ZIP_RE = re.compile(r"^\d{5}$")


class SearchRequest(BaseModel):
    # --- location input: exactly one mode must be used ---
    latitude: float | None = None
    longitude: float | None = None
    address: str | None = None
    postal_code: str | None = None

    # --- filters ---
    radius_miles: float = 10.0
    services: list[str] = []
    store_types: list[str] = []
    open_now: bool = False

    @model_validator(mode="after")
    def validate_location_mode(self) -> "SearchRequest":
        has_coords = self.latitude is not None or self.longitude is not None
        has_address = bool(self.address and self.address.strip())
        has_postal = bool(self.postal_code and self.postal_code.strip())
        modes = sum([has_coords, has_address, has_postal])

        if modes == 0:
            raise ValueError(
                "Provide exactly one of: latitude+longitude, address, or postal_code."
            )
        if modes > 1:
            raise ValueError(
                "Provide only one of: latitude+longitude, address, or postal_code."
            )

        if has_coords:
            if self.latitude is None or self.longitude is None:
                raise ValueError("Both latitude and longitude are required together.")
            if not -90 <= self.latitude <= 90:
                raise ValueError("latitude must be between -90 and 90.")
            if not -180 <= self.longitude <= 180:
                raise ValueError("longitude must be between -180 and 180.")

        if has_postal and not _ZIP_RE.match(self.postal_code.strip()):
            raise ValueError("postal_code must be a 5-digit US ZIP code.")

        return self

    @field_validator("radius_miles")
    @classmethod
    def validate_radius(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("radius_miles must be greater than 0.")
        if v > get_settings().search_radius_max_miles:
            raise ValueError(
                f"radius_miles cannot exceed {get_settings().search_radius_max_miles}."
            )
        return v

    @field_validator("services")
    @classmethod
    def validate_services(cls, v: list[str]) -> list[str]:
        allowed = get_settings().allowed_services
        invalid = [s for s in v if s not in allowed]
        if invalid:
            raise ValueError(f"Invalid services: {invalid}. Allowed: {allowed}")
        return v

    @field_validator("store_types")
    @classmethod
    def validate_store_types(cls, v: list[str]) -> list[str]:
        allowed = get_settings().allowed_store_types
        invalid = [t for t in v if t not in allowed]
        if invalid:
            raise ValueError(f"Invalid store_types: {invalid}. Allowed: {allowed}")
        return v


# --- Response schemas ---

class StoreHours(BaseModel):
    mon: str | None
    tue: str | None
    wed: str | None
    thu: str | None
    fri: str | None
    sat: str | None
    sun: str | None


class StoreSearchResult(BaseModel):
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
    distance_miles: float
    is_open_now: bool


class SearchLocation(BaseModel):
    latitude: float
    longitude: float


class FiltersApplied(BaseModel):
    radius_miles: float
    services: list[str]
    store_types: list[str]
    open_now: bool


class SearchResponse(BaseModel):
    results: list[StoreSearchResult]
    count: int
    search_location: SearchLocation
    filters_applied: FiltersApplied
