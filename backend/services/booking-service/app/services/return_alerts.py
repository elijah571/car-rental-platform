import asyncio
import hashlib
import html
import logging
from datetime import UTC, datetime, timedelta

import httpx

from app.core.config import get_settings
from app.core.database import get_sessionmaker
from app.repositories import BookingRepository

logger = logging.getLogger(__name__)
_accepted_alert_keys: set[str] = set()


def _format_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%A, %B %-d at %-I:%M %p UTC")


async def _queue_email(
    client: httpx.AsyncClient,
    *,
    recipient: str,
    subject: str,
    text_body: str,
    html_body: str,
    idempotency_key: str,
) -> None:
    settings = get_settings()
    if idempotency_key in _accepted_alert_keys:
        return
    if settings.notification_service_api_key is None:
        raise RuntimeError("Notification service credentials are not configured")
    response = await client.post(
        f"{settings.notification_service_url.rstrip('/')}/notifications/email",
        headers={
            "X-Notification-Service-Key": settings.notification_service_api_key.get_secret_value(),
            "Idempotency-Key": idempotency_key,
        },
        json={
            "recipient": recipient,
            "subject": subject,
            "text_body": text_body,
            "html_body": html_body,
        },
    )
    response.raise_for_status()
    _accepted_alert_keys.add(idempotency_key)


async def _customer_email(
    client: httpx.AsyncClient,
    customer_id: str,
) -> str | None:
    settings = get_settings()
    if settings.auth_service_api_key is None:
        raise RuntimeError("Auth service credentials are not configured")
    response = await client.get(
        f"{settings.auth_service_url.rstrip('/')}/auth/internal/users/{customer_id}/contact",
        headers={"X-Auth-Service-Key": settings.auth_service_api_key.get_secret_value()},
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return str(response.json()["email"])


async def _notify_booking(client: httpx.AsyncClient, booking, *, overdue: bool) -> None:
    booking_id = str(booking.id)
    vehicle = " ".join(part for part in (booking.vehicle_make, booking.vehicle_model) if part) or "your rental vehicle"
    due = _format_utc(booking.return_at)
    escaped_vehicle = html.escape(vehicle)
    escaped_due = html.escape(due)
    if overdue:
        subject = f"Overdue rental: return {vehicle} now"
        text_body = (
            f"The scheduled return time for {vehicle} was {due}. "
            "Please contact Drivewell support now to arrange the vehicle's safe return. "
            "The vehicle is blocked from new rentals. Any recovery service or additional fee "
            "will be reviewed by operations under your rental agreement before it is applied."
        )
        html_body = (
            f"<p>The scheduled return time for <strong>{escaped_vehicle}</strong> was "
            f"{escaped_due}.</p><p>Please contact Drivewell support now to arrange the vehicle's "
            "safe return. The vehicle is blocked from new rentals.</p><p>Any recovery service or "
            "additional fee will be reviewed by operations under your rental agreement before it is applied.</p>"
        )
        kind = "overdue-customer"
    else:
        subject = f"Return reminder: {vehicle} is due soon"
        text_body = (
            f"Your rental of {vehicle} is scheduled to end at {due}. "
            "Please return the vehicle by that time. If you expect a delay, contact Drivewell support "
            "as soon as possible so the team can help."
        )
        html_body = (
            f"<p>Your rental of <strong>{escaped_vehicle}</strong> is scheduled to end at "
            f"{escaped_due}.</p><p>Please return the vehicle by that time. If you expect a delay, "
            "contact Drivewell support as soon as possible.</p>"
        )
        kind = "return-reminder"

    try:
        email = await _customer_email(client, str(booking.customer_id))
        if email:
            await _queue_email(
                client,
                recipient=email,
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                idempotency_key=f"booking:{booking_id}:{kind}",
            )
    except Exception:
        logger.exception("Could not queue rental return email for booking %s", booking_id)

    if overdue:
        settings = get_settings()
        recovery_text = (
            f"Booking {booking_id} for {vehicle} passed its scheduled return time ({due}). "
            "The booking still blocks the vehicle from new rentals. Please review the customer "
            "contact and rental agreement, then decide whether a recovery case is appropriate. "
            "No vehicle immobilizer, location tracker, recovery dispatch, or law-enforcement action "
            "is triggered automatically."
        )
        recovery_html = (
            f"<p>Booking <strong>{html.escape(booking_id)}</strong> for "
            f"<strong>{escaped_vehicle}</strong> passed its scheduled return time ({escaped_due}).</p>"
            "<p>The booking still blocks the vehicle from new rentals. Review customer contact and "
            "the rental agreement before deciding whether a recovery case is appropriate.</p>"
            "<p>No vehicle immobilizer, location tracker, recovery dispatch, or law-enforcement action "
            "is triggered automatically.</p>"
        )
        for recipient in (item.strip() for item in settings.platform_admin_emails.replace(";", ",").split(",")):
            if not recipient:
                continue
            recipient_hash = hashlib.sha256(recipient.lower().encode()).hexdigest()[:24]
            try:
                await _queue_email(
                    client,
                    recipient=recipient,
                    subject=f"Overdue rental requires review: {vehicle}",
                    text_body=recovery_text,
                    html_body=recovery_html,
                    idempotency_key=f"booking:{booking_id}:recovery-review:{recipient_hash}",
                )
            except Exception:
                logger.exception("Could not queue overdue rental review alert for booking %s", booking_id)


async def process_return_alerts() -> None:
    settings = get_settings()
    if not settings.auth_service_api_key or not settings.notification_service_api_key:
        logger.warning("Return alert job is idle: auth or notification service credentials are missing")
        return
    now = datetime.now(UTC)
    async with get_sessionmaker()() as session:
        repository = BookingRepository(session)
        async def load_all(*, cutoff: datetime, after: datetime | None = None):
            bookings = []
            offset = 0
            while True:
                page = await repository.list_active_returns_due_before(
                    cutoff, after=after, limit=100, offset=offset
                )
                bookings.extend(page)
                if len(page) < 100:
                    return bookings
                offset += len(page)

        upcoming = await load_all(cutoff=now + timedelta(minutes=settings.return_reminder_minutes), after=now)
        overdue = await load_all(cutoff=now)

    async with httpx.AsyncClient(timeout=6.0) as client:
        for booking in upcoming:
            await _notify_booking(client, booking, overdue=False)
        for booking in overdue:
            await _notify_booking(client, booking, overdue=True)


async def run_return_alert_job() -> None:
    while True:
        try:
            await process_return_alerts()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Rental return alert job failed")
        await asyncio.sleep(60)
