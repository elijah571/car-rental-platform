import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.vehicles import router as vehicle_router
from app.core.config import get_settings
from app.core.database import dispose_db_engine, get_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        await dispose_db_engine()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Car Rental Car Service",
        description="Vehicle inventory and catalog service for the Car Rental Platform.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in get_settings().cors_allowed_origins.split(",") if origin.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    application.include_router(vehicle_router)

    @application.get("/", tags=["General"])
    async def root() -> dict[str, str]:
        return {"message": "Car Rental Car Service is running"}

    @application.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "car-service"}

    @application.get("/ready", tags=["Health"])
    async def readiness():
        result = {"status": "ready", "service": "car-service"}
        if not get_settings().database_configured:
            result["database"] = "not_configured"
            return result
        try:
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1 FROM vehicles LIMIT 0"))
        except (SQLAlchemyError, OSError, ValueError):
            logger.exception("Car service readiness check failed")
            result["status"] = "not_ready"
            result["database"] = "unavailable"
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content=result,
            )
        result["database"] = "connected"
        return result

    return application


app = create_app()
