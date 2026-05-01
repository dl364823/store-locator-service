import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.exceptions import StoreLocatorError
from app.logging_config import setup_logging
from app.middleware.rate_limit import limiter

logger = logging.getLogger(__name__)

# OpenAPI tag groups — controls sidebar order in Swagger UI
_TAGS = [
    {
        "name": "Health",
        "description": "Service health and readiness check.",
    },
    {
        "name": "Search",
        "description": (
            "**Public** store search. Rate-limited to **10 req/min** and "
            "**100 req/hour** per IP. No authentication required."
        ),
    },
    {
        "name": "Auth",
        "description": (
            "JWT two-token authentication.\n\n"
            "**Flow:** `POST /login` → receive `access_token` (15 min) + `refresh_token` (7 days). "
            "Send `access_token` as `Authorization: Bearer <token>` on protected endpoints. "
            "Use `POST /refresh` to obtain a new access token without re-logging in. "
            "`POST /logout` revokes the refresh token."
        ),
    },
    {
        "name": "Admin — Stores",
        "description": (
            "Authenticated store management (CRUD + PATCH).\n\n"
            "**Required permission:** `stores:read` (GET) or `stores:write` (POST/PATCH/DELETE).\n\n"
            "PATCH only accepts: `name`, `phone`, `services`, `status`, `hours`. "
            "Attempts to update `store_id`, coordinates, or address fields are rejected."
        ),
    },
    {
        "name": "Admin — Import",
        "description": (
            "Bulk CSV import (upsert). **Required permission:** `import:write`.\n\n"
            "The import is **all-or-nothing**: if any row fails validation, nothing is written. "
            "Existing `store_id`s are updated; new ones are created."
        ),
    },
    {
        "name": "Admin — Users",
        "description": (
            "User management. **Admin only** (`users:read` / `users:write`).\n\n"
            "Soft delete only — users are deactivated, never physically removed."
        ),
    },
]

_DESCRIPTION = """
## Store Locator API

Production-ready store search and management service for a multi-location retail business.

### Public endpoints
- `POST /api/stores/search` — find nearby stores by coordinates, address, or ZIP code

### Authenticated endpoints (JWT Bearer token required)
All `/api/auth/*` and `/api/admin/*` endpoints require a valid access token.

### Role-based access
| Role | Permissions |
|------|-------------|
| **admin** | Full access to all endpoints |
| **marketer** | Store management + CSV import |
| **viewer** | Read-only store access |

### Error format
All errors use a consistent envelope:
```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable description"
  }
}
```

### Distance calculation
Bounding-box pre-filter (SQL) → exact Haversine distance (geopy) → sorted by nearest first.
"""


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Store Locator API",
        description=_DESCRIPTION,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=_TAGS,
        contact={"name": "Store Locator", "email": "admin@test.com"},
    )

    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Exception handlers (most-specific first) ---

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please slow down and try again.",
                }
            },
            headers={"Retry-After": "60"},
        )

    @app.exception_handler(StoreLocatorError)
    async def store_locator_error_handler(
        request: Request, exc: StoreLocatorError
    ) -> JSONResponse:
        logger.error(
            "Application error: %s",
            exc.message,
            extra={"path": str(request.url.path), "error_code": exc.code},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = [
            {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        logger.warning("Request validation failed", extra={"path": str(request.url.path)})
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "REQUEST_VALIDATION_ERROR",
                    "message": "Request body or parameters failed validation.",
                    "details": errors,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again later.",
                }
            },
        )

    # --- Health check ---
    @app.get(
        "/health",
        tags=["Health"],
        summary="Health check",
        response_description="Returns service status and version",
        responses={200: {"content": {"application/json": {"example": {"status": "healthy", "version": "1.0.0"}}}}},
    )
    async def health_check() -> dict:
        return {"status": "healthy", "version": "1.0.0"}

    # --- Routers ---
    from app.api.search import router as search_router
    from app.api.auth import router as auth_router
    from app.api.admin_stores import router as admin_stores_router
    from app.api.admin_import import router as admin_import_router
    from app.api.admin_users import router as admin_users_router

    app.include_router(search_router, prefix="/api")
    app.include_router(auth_router, prefix="/api/auth")
    app.include_router(admin_stores_router, prefix="/api/admin")
    app.include_router(admin_import_router, prefix="/api/admin")
    app.include_router(admin_users_router, prefix="/api/admin")

    return app


app = create_app()
