import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.bookings import router as booking_router
from app.core.config import get_settings
from app.core.database import dispose_db_engine, get_engine, get_sessionmaker
from app.repositories import BookingRepository

logger = logging.getLogger(__name__)


async def _expire_holds_forever() -> None:
    while True:
        try:
            async with get_sessionmaker()() as session:
                await BookingRepository(session).expire_pending_holds()
                await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Pending booking hold expiration failed")
        await asyncio.sleep(15)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    expiry_task = None
    if get_settings().database_configured:
        expiry_task = asyncio.create_task(_expire_holds_forever())
    try:
        yield
    finally:
        if expiry_task is not None:
            expiry_task.cancel()
            try:
                await expiry_task
            except asyncio.CancelledError:
                pass
        await dispose_db_engine()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Car Rental Booking Service",
        description="Booking lifecycle and vehicle reservation service.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in get_settings().cors_allowed_origins.split(",") if origin.strip()],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )
    application.include_router(booking_router)

    @application.get("/", tags=["General"])
    async def root() -> dict[str, str]:
        return {"message": "Car Rental Booking Service is running"}

    @application.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "booking-service"}

    @application.get("/ready", tags=["Health"])
    async def readiness():
        result = {"status": "ready", "service": "booking-service"}
        if not get_settings().database_configured:
            result["database"] = "not_configured"
            return result
        try:
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1 FROM bookings LIMIT 0"))
        except (SQLAlchemyError, OSError, ValueError):
            logger.exception("Booking service readiness check failed")
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
