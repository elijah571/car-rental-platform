from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Notification
from app.schemas.notification import EmailNotificationCreate


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_idempotency_key(self, key: str) -> Notification | None:
        result = await self.session.execute(
            select(Notification).where(Notification.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def claim_next(self) -> Notification | None:
        now = datetime.now(UTC)
        eligible = or_(
            and_(
                Notification.status.in_(("pending", "failed")),
                or_(Notification.next_attempt_at.is_(None), Notification.next_attempt_at <= now),
            ),
            and_(Notification.status == "sending", Notification.locked_until <= now),
        )
        result = await self.session.execute(
            select(Notification)
            .where(eligible)
            .order_by(Notification.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        notification = result.scalar_one_or_none()
        if notification is None:
            return None
        notification.status = "sending"
        notification.attempt_count += 1
        notification.locked_until = now + timedelta(minutes=2)
        notification.error_message = None
        await self.session.commit()
        return notification

    async def create(
        self,
        key: str,
        payload: EmailNotificationCreate,
    ) -> Notification:
        notification = Notification(
            idempotency_key=key,
            recipient=str(payload.recipient),
            subject=payload.subject,
            text_body=payload.text_body,
            html_body=payload.html_body,
            status="pending",
        )
        self.session.add(notification)
        await self.session.flush()
        return notification

    async def get(self, notification_id: UUID) -> Notification | None:
        return await self.session.get(Notification, notification_id)

    async def mark_sent(self, notification: Notification, provider_message_id: str) -> None:
        notification.status = "sent"
        notification.provider_message_id = provider_message_id
        notification.error_message = None
        notification.locked_until = None
        notification.next_attempt_at = None
        await self.session.flush()

    async def mark_failed(self, notification: Notification, message: str) -> None:
        notification.status = "failed"
        notification.error_message = message[:500]
        notification.locked_until = None
        backoff_seconds = min(30 * (2 ** max(notification.attempt_count - 1, 0)), 3600)
        notification.next_attempt_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
        await self.session.flush()
