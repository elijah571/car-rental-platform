import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import router as auth_router
from app.api.kyc import router as kyc_router
from app.api.support import router as support_router
from app.core.config import get_settings
from app.core.database import dispose_db_engine, get_engine
from app.core.redis import close_redis, get_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Release database and Redis clients on shutdown."""
    try:
        yield
    finally:
        try:
            await dispose_db_engine()
        finally:
            await close_redis()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Car Rental Auth Service",
        description="Authentication and identity service for the Car Rental Platform.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in get_settings().cors_allowed_origins.split(",") if origin.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )
    application.include_router(auth_router)
    application.include_router(kyc_router)
    application.include_router(support_router)

    @application.get("/", tags=["General"])
    async def root() -> dict[str, str]:
        return {"message": "Car Rental Auth Service is running"}

    @application.get("/health", tags=["Health"])
    async def health_check() -> dict[str, str]:
        """Liveness check: confirms the process can serve requests."""
        return {"status": "healthy", "service": "auth-service"}

    @application.get("/ready", tags=["Health"], status_code=status.HTTP_200_OK)
    async def readiness_check():
        """Readiness check, including PostgreSQL when profile persistence is enabled."""
        settings = get_settings()
        result = {"status": "ready", "service": "auth-service"}
        if not settings.database_configured:
            result["database"] = "not_configured"
            return result

        try:
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1 FROM users LIMIT 0"))
        except (SQLAlchemyError, OSError, ValueError):
            logger.exception("Auth service readiness check failed")
            result["status"] = "not_ready"
            result["database"] = "unavailable"
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=result,
            )

        result["database"] = "connected"
        try:
            await get_redis().ping()
        except Exception:
            logger.exception("Auth service Redis readiness check failed")
            result["status"] = "not_ready"
            result["redis"] = "unavailable"
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=result)
        result["redis"] = "connected"
        return result

    return application


app = create_app()
