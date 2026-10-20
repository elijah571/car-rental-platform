from secrets import compare_digest
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_optional_db
from app.repositories import NotificationRepository
from app.schemas.notification import EmailNotificationCreate, NotificationRead

router = APIRouter(prefix="/notifications", tags=["Notifications"])


def verify_service_key(
    service_key: str | None = Header(default=None, alias="X-Notification-Service-Key"),
) -> None:
    configured_key = get_settings().notification_service_api_key
    if configured_key is None:
        raise HTTPException(status_code=503, detail="Notification service access is not configured.")
    if service_key is None or not compare_digest(service_key, configured_key.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid notification service credentials.")


def _require_database(db: AsyncSession | None) -> AsyncSession:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Notification storage is not configured.",
        )
    return db


@router.post("/email", response_model=NotificationRead, status_code=status.HTTP_202_ACCEPTED)
async def send_email_notification(
    payload: EmailNotificationCreate,
    idempotency_key: str = Header(min_length=1, max_length=128, alias="Idempotency-Key"),
    _: None = Depends(verify_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    repository = NotificationRepository(session)
    existing = await repository.get_by_idempotency_key(idempotency_key)
    if existing is not None:
        if (
            existing.recipient != str(payload.recipient)
            or existing.subject != payload.subject
            or existing.text_body != payload.text_body
            or existing.html_body != payload.html_body
        ):
            raise HTTPException(status_code=409, detail="The idempotency key belongs to another notification.")
        return existing

    try:
        notification = await repository.create(idempotency_key, payload)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing = await repository.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            if (
                existing.recipient != str(payload.recipient)
                or existing.subject != payload.subject
                or existing.text_body != payload.text_body
                or existing.html_body != payload.html_body
            ):
                raise HTTPException(status_code=409, detail="The idempotency key belongs to another notification.") from exc
            return existing
        raise HTTPException(status_code=409, detail="The idempotency key is already in use.") from exc
    return notification


@router.get("/{notification_id}", response_model=NotificationRead)
async def get_notification(
    notification_id: UUID,
    _: None = Depends(verify_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    notification = await NotificationRepository(_require_database(db)).get(notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    return notification
