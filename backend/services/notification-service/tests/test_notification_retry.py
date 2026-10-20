import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import Notification
from app.repositories import NotificationRepository


def test_notification_claim_and_retry_schedule():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            session.add(
                Notification(
                    idempotency_key="receipt-test",
                    recipient="customer@example.com",
                    subject="Receipt",
                    text_body="Your receipt",
                    status="pending",
                )
            )
            await session.commit()
            repository = NotificationRepository(session)
            notification = await repository.claim_next()
            assert notification is not None
            assert notification.status == "sending"
            assert notification.attempt_count == 1
            await repository.mark_failed(notification, "temporary failure")
            await session.commit()
            assert notification.status == "failed"
            assert notification.next_attempt_at is not None
            assert await repository.claim_next() is None
        await engine.dispose()

    asyncio.run(run())
