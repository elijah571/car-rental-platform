import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.notifications import router as notification_router
from app.core.config import get_settings
from app.core.database import dispose_db_engine, get_engine, get_sessionmaker
from app.repositories import NotificationRepository
from app.services import email_sender

logger = logging.getLogger(__name__)


async def _deliver_notifications() -> None:
    while True:
        try:
            async with get_sessionmaker()() as session:
                repository = NotificationRepository(session)
                notification = await repository.claim_next()
                if notification is not None:
                    try:
                        provider_message_id = await run_in_threadpool(
                            email_sender.send_email,
                            recipient=notification.recipient,
                            subject=notification.subject,
                            text_body=notification.text_body,
                            html_body=notification.html_body,
                        )
                    except Exception:
                        logger.exception("Email delivery attempt failed; it will be retried")
                        await repository.mark_failed(notification, "Email delivery failed; retry scheduled")
                        await session.commit()
                    else:
                        await repository.mark_sent(notification, provider_message_id)
                        await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Notification worker iteration failed")
        await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    worker = None
    if get_settings().database_configured:
        worker = asyncio.create_task(_deliver_notifications())
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
        try:
            await dispose_db_engine()
        finally:
            email_sender.close_client()


def create_app() -> FastAPI:
    application = FastAPI(
        title="Car Rental Notification Service",
        description="Email notification delivery service for the Car Rental Platform.",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(notification_router)

    @application.get("/", tags=["General"])
    async def root() -> dict[str, str]:
        return {"message": "Car Rental Notification Service is running"}

    @application.get("/health", tags=["Health"])
    async def health() -> dict[str, str]:
        return {"status": "healthy", "service": "notification-service"}

    @application.get("/ready", tags=["Health"])
    async def readiness():
        result = {"status": "ready", "service": "notification-service"}
        if not get_settings().database_configured:
            result["database"] = "not_configured"
            return result
        try:
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1 FROM notifications LIMIT 0"))
        except (SQLAlchemyError, OSError, ValueError):
            logger.exception("Notification service readiness check failed")
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
