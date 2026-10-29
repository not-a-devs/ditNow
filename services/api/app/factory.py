from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import Settings
from app.core.db_connection import create_database_engine
from app.core.errors import (
    ApiError,
    api_error_handler,
    http_error_handler,
    validation_error_handler,
)
from app.core.logging import SafeRequestMiddleware, configure_logging
from app.integrations.chatbot.assistant import build_assistant
from app.integrations.platform_runtime.runtime import PlatformRuntime
from app.schemas.common import ErrorResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level)
    platform_runtime = None
    if (
        settings.p0_runtime_enabled
        and settings.p0_schema_approved
        and settings.database_configured
        and settings.p0_identity_approval_ids
    ):
        platform_runtime = PlatformRuntime(
            create_database_engine(settings), frozenset(settings.p0_identity_approval_ids)
        )
    assistant = build_assistant(settings, platform_runtime)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if assistant.engine is not None:
                await assistant.engine.dispose()

    application = FastAPI(
        title="DIT NOW API",
        version="0.1.0",
        description=(
            "DIT NOW 통합 API. 학번 로그인과 AI 답변은 가상(DEMO) 학적 데이터를 사용한다."
        ),
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
        responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    application.state.assistant = assistant
    application.state.platform_runtime = platform_runtime
    application.add_exception_handler(ApiError, api_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(HTTPException, http_error_handler)
    application.include_router(health_router)
    application.include_router(v1_router)
    if settings.p0_runtime_enabled:
        # Thin async transport only; never mount synchronous feature routers over AsyncSession.
        from app.api.v1.p0 import router as p0_router

        application.include_router(p0_router, prefix="/api/v1")
    application.add_middleware(SafeRequestMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "If-Match", "Idempotency-Key"],
        expose_headers=["X-Request-ID", "Idempotent-Replayed"],
    )
    return application
