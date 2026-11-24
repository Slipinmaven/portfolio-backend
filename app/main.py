import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import close_logging, configure_logging
from app.infrastructure.database.session import dispose_database_engine
from app.presentation.api.router import router
from app.presentation.middleware.exception_handling import ExceptionHandlingMiddleware
from app.presentation.middleware.request_logging import RequestLoggingMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info(
        "Application startup complete",
        extra={
            "event": "application.started",
            "environment": settings.environment,
            "database_pool_size": settings.database_pool_size,
            "database_max_overflow": settings.database_max_overflow,
            "database_connections_per_process": settings.database_connections_per_process,
        },
    )
    try:
        yield
    finally:
        try:
            await dispose_database_engine()
        finally:
            logger.info(
                "Application shutdown",
                extra={"event": "application.stopped"},
            )
            close_logging()


app = FastAPI(
    title=settings.app_name,
    description="A portfolio project showcasing my skills and experience.",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)
app.add_middleware(ExceptionHandlingMiddleware)
app.add_middleware(RequestLoggingMiddleware)
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
app.include_router(router)