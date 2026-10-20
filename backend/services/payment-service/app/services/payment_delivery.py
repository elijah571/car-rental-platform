import logging

import httpx
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Payment, PaymentDeliveryOutbox
from app.repositories import PaymentRepository
from app.services.email_templates import render_receipt_email

logger = logging.getLogger(__name__)


class BookingCannotApplyPayment(Exception):
    """Stripe charged successfully, but this payment cannot confirm its booking."""


class DeliveryUnavailable(Exception):
    """A downstream delivery step failed and should be retried."""


def _secret(value: SecretStr | None) -> str | None:
    return value.get_secret_value() if value is not None else None


async def deliver_successful_payment(
    session: AsyncSession,
    entry: PaymentDeliveryOutbox,
) -> None:
    settings = get_settings()
    payment = await session.get(Payment, entry.payment_id)
    if payment is None:
        raise DeliveryUnavailable("Payment record is missing.")
    if not settings.booking_service_url or not settings.payment_to_booking_api_key:
        raise DeliveryUnavailable("Booking payment callback is not configured.")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{settings.booking_service_url.rstrip('/')}/bookings/internal/payment-confirmations",
                headers={"X-Payment-Service-Key": _secret(settings.payment_to_booking_api_key)},
                json={
                    "booking_id": str(payment.booking_id),
                    "payment_id": str(payment.id),
                    "stripe_payment_intent_id": payment.stripe_payment_intent_id,
                    "amount_minor": payment.amount_minor,
                    "currency": payment.currency,
                    "stripe_event_id": entry.event_id,
                },
            )
            if response.status_code in {404, 409}:
                raise BookingCannotApplyPayment("Booking hold cannot be confirmed.")
            if response.status_code >= 400:
                raise DeliveryUnavailable("Booking confirmation service rejected the request.")
            booking = response.json()

            if not settings.receipt_service_url or not settings.receipt_service_api_key:
                raise DeliveryUnavailable("Receipt creation is not configured.")
            receipt_response = await client.post(
                f"{settings.receipt_service_url.rstrip('/')}/receipts",
                headers={
                    "X-Receipt-Service-Key": _secret(settings.receipt_service_api_key),
                    "Idempotency-Key": payment.stripe_payment_intent_id,
                },
                json={
                    "booking_id": str(booking["id"]),
                    "payment_id": str(payment.id),
                    "stripe_payment_intent_id": payment.stripe_payment_intent_id,
                    "customer_id": str(booking["customer_id"]),
                    "rental_start": booking["pickup_at"],
                    "rental_end": booking["return_at"],
                    "amount_minor": payment.amount_minor,
                    "currency": payment.currency,
                    "vehicle_make": booking["vehicle_make"],
                    "vehicle_model": booking["vehicle_model"],
                    "vehicle_color": booking["vehicle_color"],
                    "vehicle_license_plate": booking["vehicle_license_plate"],
                },
            )
            if receipt_response.status_code >= 400:
                raise DeliveryUnavailable("Receipt could not be created.")
            receipt = receipt_response.json()

            if not settings.auth_service_url or not settings.auth_service_api_key:
                raise DeliveryUnavailable("Customer contact lookup is not configured.")
            contact_response = await client.get(
                f"{settings.auth_service_url.rstrip('/')}/auth/internal/users/{booking['customer_id']}/contact",
                headers={"X-Auth-Service-Key": _secret(settings.auth_service_api_key)},
            )
            if contact_response.status_code == 404:
                logger.warning("Receipt email skipped because no verified customer contact exists")
                return
            if contact_response.status_code >= 400:
                raise DeliveryUnavailable("Customer contact lookup is unavailable.")

            if not settings.notification_service_url or not settings.notification_service_api_key:
                raise DeliveryUnavailable("Notification delivery is not configured.")
            amount = f"{chr(36)}{payment.amount_minor // 100}.{payment.amount_minor % 100:02d}"
            text_body, html_body = render_receipt_email(
                receipt_number=receipt["receipt_number"],
                booking_id=booking["id"],
                vehicle=f"{booking['vehicle_make']} {booking['vehicle_model']}",
                vehicle_details=f"{booking['vehicle_color']}, {booking['vehicle_license_plate']}",
                rental_start=booking["pickup_at"],
                rental_end=booking["return_at"],
                amount=amount,
            )
            notification_response = await client.post(
                f"{settings.notification_service_url.rstrip('/')}/notifications/email",
                headers={
                    "X-Notification-Service-Key": _secret(settings.notification_service_api_key),
                    "Idempotency-Key": f"receipt-email:{payment.id}",
                },
                json={
                    "recipient": contact_response.json()["email"],
                    "subject": f"Your car rental receipt {receipt['receipt_number']}",
                    "text_body": text_body,
                    "html_body": html_body,
                },
            )
            if notification_response.status_code >= 400:
                raise DeliveryUnavailable("Receipt email could not be queued.")
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise DeliveryUnavailable("A downstream payment delivery service is unavailable.") from exc


async def process_next_delivery(session: AsyncSession) -> bool:
    repository = PaymentRepository(session)
    entry = await repository.claim_next_delivery()
    if entry is None:
        return False
    try:
        await deliver_successful_payment(session, entry)
    except BookingCannotApplyPayment:
        logger.error("Successful Stripe payment needs booking reconciliation: event=%s", entry.event_id)
        await repository.mark_reconciliation_required(entry)
    except Exception as exc:
        logger.exception("Payment delivery failed: event=%s", entry.event_id)
        await repository.mark_delivery_failed(entry, str(exc))
    else:
        await repository.mark_delivery_complete(entry)
    return True
