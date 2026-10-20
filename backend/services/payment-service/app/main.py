import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.payments import router as payment_router
from app.core.config import get_settings
from app.core.database import dispose_db_engine, get_engine, get_sessionmaker
from app.services.payment_delivery import process_next_delivery

logger = logging.getLogger(__name__)


async def _deliver_outbox_forever() -> None:
    while True:
        try:
            async with get_sessionmaker()() as session:
                worked = await process_next_delivery(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Payment delivery outbox worker failed")
            worked = False
        if not worked:
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    worker = None
    if get_settings().database_configured:
        worker = asyncio.create_task(_deliver_outbox_forever())
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
        await dispose_db_engine()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Car Rental Payment Service",
        description="Stripe payment intent and webhook service for the Car Rental Platform.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(payment_router)

    @application.get("/", tags=["General"])
    async def root() -> dict[str, str]:
        return {"message": "Car Rental Payment Service is running"}

    @application.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "payment-service"}

    @application.get("/ready", tags=["Health"])
    async def readiness():
        result = {"status": "ready", "service": "payment-service"}
        if not get_settings().database_configured:
            result["database"] = "not_configured"
            return result
        try:
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1 FROM payments LIMIT 0"))
                await connection.execute(text("SELECT 1 FROM payment_delivery_outbox LIMIT 0"))
        except (SQLAlchemyError, OSError, ValueError):
            logger.exception("Payment service readiness check failed")
            result["status"] = "not_ready"
            result["database"] = "unavailable"
            return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=result)
        result["database"] = "connected"
        return result

    return application


app = create_app()
