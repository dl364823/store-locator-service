from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://localhost/store_locator"

    # JWT
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Rate limiting (per IP)
    rate_limit_per_hour: int = 100
    rate_limit_per_minute: int = 10

    # Cache TTLs
    geocoding_cache_ttl_days: int = 30
    search_cache_ttl_seconds: int = 300

    # Redis (None = use in-memory cache)
    redis_url: str | None = None

    # CORS
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8080"]

    # Logging
    log_level: str = "INFO"

    # Allowed store values — single source of truth
    allowed_store_types: list[str] = ["flagship", "regular", "outlet", "express"]
    allowed_store_statuses: list[str] = ["active", "inactive", "temporarily_closed"]
    allowed_services: list[str] = [
        "pharmacy", "pickup", "returns", "optical",
        "photo_printing", "gift_wrapping", "automotive", "garden_center",
    ]
    allowed_roles: list[str] = ["admin", "marketer", "viewer"]

    # Search limits
    search_radius_max_miles: float = 100.0
    search_radius_default_miles: float = 10.0

    # PATCH allowlist — fields that may be updated via PATCH /admin/stores/{id}
    store_patch_allowed_fields: list[str] = ["name", "phone", "services", "status", "hours"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
