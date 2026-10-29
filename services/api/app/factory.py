from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import Settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    validation_error_handler,
)
from app.core.logging import SafeRequestMiddleware, configure_logging
from app.schemas.common import ErrorResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    application = FastAPI(
        title="DIT NOW API",
        version="0.1.0",
        description=(
            "Public liveness foundation. Authentication and persistence are not implemented."
        ),
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    application.add_exception_handler(ApiError, api_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(HTTPException, http_error_handler)
    application.include_router(health_router)
    application.include_router(v1_router)
    application.add_middleware(SafeRequestMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    return application
