import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.exceptions import StoreLocatorError
from app.logging_config import setup_logging

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
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
        # Normalize Pydantic/FastAPI validation errors to our error envelope
        errors = [
            {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
            for e in exc.errors()
        ]
        logger.warning(
            "Request validation failed",
            extra={"path": str(request.url.path), "errors": errors},
        )
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
        # Log full traceback internally; never expose it to the caller
        logger.exception(
            "Unhandled exception on %s", request.url.path
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred. Please try again later.",
                }
            },
        )

    # ---------- Health check ----------
    @app.get(
        "/health",
        tags=["Health"],
        summary="Health check",
        response_description="Service health status",
    )
    async def health_check() -> dict:
        return {"status": "healthy", "version": "1.0.0"}

    # Routers are registered here as they are built in later tasks
    # from app.api import search, auth, admin_stores, admin_import, admin_users
    # app.include_router(search.router, prefix="/api")
    # app.include_router(auth.router, prefix="/api/auth")
    # app.include_router(admin_stores.router, prefix="/api/admin")
    # app.include_router(admin_import.router, prefix="/api/admin")
    # app.include_router(admin_users.router, prefix="/api/admin")

    return app


app = create_app()
