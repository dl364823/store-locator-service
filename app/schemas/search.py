import re

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config import get_settings

_ZIP_RE = re.compile(r"^\d{5}$")


class SearchRequest(BaseModel):
    # --- location input: exactly one mode must be used ---
    latitude: float | None = Field(
        None,
        description="Search latitude (-90 to 90). Must be provided with longitude.",
        examples=[42.3601],
    )
    longitude: float | None = Field(
        None,
        description="Search longitude (-180 to 180). Must be provided with latitude.",
        examples=[-71.0589],
    )
    address: str | None = Field(
        None,
        description="Free-text address to geocode (Nominatim). Mutually exclusive with other location modes.",
        examples=["100 Cambridge St, Boston, MA"],
    )
    postal_code: str | None = Field(
        None,
        description="5-digit US ZIP code. Mutually exclusive with other location modes.",
        examples=["02114"],
    )

    # --- filters ---
    radius_miles: float = Field(
        10.0,
        description="Search radius in miles. Must be > 0 and ≤ 100.",
        examples=[10.0],
    )
    services: list[str] = Field(
        [],
        description=(
            "AND filter — store must have ALL listed services. "
            "Allowed: pharmacy, pickup, returns, optical, photo_printing, "
            "gift_wrapping, automotive, garden_center."
        ),
        examples=[["pharmacy", "pickup"]],
    )
    store_types: list[str] = Field(
        [],
        description="OR filter — store matches ANY listed type. Allowed: flagship, regular, outlet, express.",
        examples=[["regular", "flagship"]],
    )
    open_now: bool = Field(
        False,
        description=(
            "When true, return only stores currently open (compared in UTC). "
            "Results with open_now=true are never cached."
        ),
    )

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
    mon: str | None = Field(None, examples=["08:00-22:00"])
    tue: str | None = Field(None, examples=["08:00-22:00"])
    wed: str | None = Field(None, examples=["08:00-22:00"])
    thu: str | None = Field(None, examples=["08:00-22:00"])
    fri: str | None = Field(None, examples=["08:00-23:00"])
    sat: str | None = Field(None, examples=["09:00-23:00"])
    sun: str | None = Field(None, examples=["10:00-20:00"])


class StoreSearchResult(BaseModel):
    store_id: str = Field(..., examples=["S0001"])
    name: str = Field(..., examples=["Boston Downtown Store"])
    store_type: str = Field(..., examples=["flagship"])
    status: str = Field(..., examples=["active"])
    latitude: float = Field(..., examples=[42.3555])
    longitude: float = Field(..., examples=[-71.0602])
    address_street: str = Field(..., examples=["100 Cambridge St"])
    address_city: str = Field(..., examples=["Boston"])
    address_state: str = Field(..., examples=["MA"])
    address_postal_code: str = Field(..., examples=["02114"])
    address_country: str = Field(..., examples=["USA"])
    phone: str = Field(..., examples=["617-555-0100"])
    services: list[str] = Field(..., examples=[["pharmacy", "pickup", "optical"]])
    hours: StoreHours
    distance_miles: float = Field(
        ..., description="Haversine distance in miles from search location", examples=[0.3]
    )
    is_open_now: bool = Field(..., description="Whether the store is currently open (UTC)")


class SearchLocation(BaseModel):
    latitude: float = Field(..., examples=[42.3601])
    longitude: float = Field(..., examples=[-71.0589])


class FiltersApplied(BaseModel):
    radius_miles: float = Field(..., examples=[10.0])
    services: list[str] = Field(..., examples=[[]])
    store_types: list[str] = Field(..., examples=[[]])
    open_now: bool = Field(..., examples=[False])


class SearchResponse(BaseModel):
    results: list[StoreSearchResult]
    count: int = Field(..., description="Number of stores returned", examples=[5])
    search_location: SearchLocation
    filters_applied: FiltersApplied
