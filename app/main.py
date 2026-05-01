import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.config import get_settings
from app.exceptions import StoreLocatorError
from app.logging_config import setup_logging
from app.middleware.rate_limit import limiter

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Store Locator API",
        description=(
            "Production-ready Store Locator service supporting public store search "
            "and authenticated store management with role-based access control."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Wire slowapi limiter into the app state so decorators can access it
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
    @app.get("/health", tags=["Health"], summary="Health check")
    async def health_check() -> dict:
        return {"status": "healthy", "version": "1.0.0"}

    # --- Routers ---
    from app.api.search import router as search_router

    app.include_router(search_router, prefix="/api")

    # Registered as tasks are completed:
    # from app.api.auth import router as auth_router
    # from app.api.admin_stores import router as admin_stores_router
    # from app.api.admin_import import router as admin_import_router
    # from app.api.admin_users import router as admin_users_router
    # app.include_router(auth_router, prefix="/api/auth")
    # app.include_router(admin_stores_router, prefix="/api/admin")
    # app.include_router(admin_import_router, prefix="/api/admin")
    # app.include_router(admin_users_router, prefix="/api/admin")

    return app


app = create_app()
