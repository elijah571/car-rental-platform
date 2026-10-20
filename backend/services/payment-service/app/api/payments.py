from secrets import compare_digest
from uuid import UUID
import httpx

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_optional_db
from app.repositories import PaymentRepository
from app.schemas.payment import PaymentCreate, PaymentIntentRead, PaymentRead
from app.services import stripe_gateway

router = APIRouter(prefix="/payments", tags=["Payments"])


def _require_database(db: AsyncSession | None) -> AsyncSession:
    if db is None:
        raise HTTPException(status_code=503, detail="Payment storage is not configured.")
    return db


def _require_stripe_key() -> None:
    if not get_settings().stripe_secret_key:
        raise HTTPException(status_code=503, detail="Stripe payments are not configured.")


def verify_service_key(
    service_key: str | None = Header(default=None, alias="X-Payment-Service-Key"),
) -> None:
    configured_key = get_settings().payment_service_api_key
    if configured_key is None:
        raise HTTPException(status_code=503, detail="Payment service access is not configured.")
    if service_key is None or not compare_digest(service_key, configured_key.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid payment service credentials.")


@router.post("/intents", response_model=PaymentIntentRead, status_code=status.HTTP_201_CREATED)
async def create_payment_intent(
    payload: PaymentCreate,
    idempotency_key: str = Header(
        min_length=1, max_length=255, alias="Idempotency-Key"
    ),
    _: None = Depends(verify_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    _require_stripe_key()
    repository = PaymentRepository(session)
    existing = await repository.get_by_intent_key(idempotency_key)
    if existing is not None:
        if existing.booking_id != payload.booking_id:
            raise HTTPException(status_code=409, detail="The idempotency key belongs to another booking.")
        try:
            intent = await run_in_threadpool(
                stripe_gateway.retrieve_payment_intent, existing.stripe_payment_intent_id
            )
        except stripe.StripeError as exc:
            raise HTTPException(status_code=502, detail="Stripe could not retrieve the payment.") from exc
        return PaymentIntentRead(
            id=existing.id,
            booking_id=existing.booking_id,
            amount_minor=existing.amount_minor,
            currency=existing.currency,
            status=existing.status,
            client_secret=intent.client_secret,
        )

    existing = await repository.get_by_booking_id(payload.booking_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="A payment already exists for this booking.")

    settings = get_settings()
    if settings.payment_to_booking_api_key is None or not settings.booking_service_url:
        raise HTTPException(status_code=503, detail="Booking payment lookup is not configured.")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            booking_response = await client.get(
                f"{settings.booking_service_url.rstrip('/')}/bookings/internal/{payload.booking_id}/payment-details",
                headers={"X-Payment-Service-Key": settings.payment_to_booking_api_key.get_secret_value()},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Booking service is unavailable.") from exc
    if booking_response.status_code == 404:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking_response.status_code == 409:
        raise HTTPException(status_code=409, detail="Booking hold has expired or is no longer payable.")
    if booking_response.status_code >= 500:
        raise HTTPException(status_code=503, detail="Booking service is unavailable.")
    if booking_response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Booking service rejected the payment lookup.")
    booking = booking_response.json()
    if booking.get("id") != str(payload.booking_id) or booking.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Booking is not payable.")
    amount_minor = int(booking["amount_minor"])
    currency = str(booking["currency"]).lower()
    if amount_minor <= 0 or currency != "usd":
        raise HTTPException(status_code=409, detail="Booking amount or currency is not supported.")

    try:
        intent = await run_in_threadpool(
            stripe_gateway.create_payment_intent,
            amount=amount_minor,
            currency=currency,
            booking_id=str(payload.booking_id),
            idempotency_key=idempotency_key,
        )
    except stripe.StripeError as exc:
        raise HTTPException(status_code=502, detail="Stripe could not create the payment.") from exc

    try:
        payment = await repository.create(
            booking_id=payload.booking_id,
            idempotency_key=idempotency_key,
            intent_id=intent.id,
            amount_minor=amount_minor,
            currency=currency,
            status=intent.status,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        existing = await repository.get_by_intent_key(idempotency_key)
        if existing is None:
            raise HTTPException(status_code=409, detail="The idempotency key conflicts with another payment.") from exc
        payment = existing

    return PaymentIntentRead(
        id=payment.id,
        booking_id=payment.booking_id,
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        status=payment.status,
        client_secret=intent.client_secret,
    )


@router.get("/{payment_id}", response_model=PaymentRead)
async def get_payment(
    payment_id: UUID,
    _: None = Depends(verify_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    payment = await PaymentRepository(_require_database(db)).get_by_id(payment_id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Payment not found.")
    return payment


@router.post("/internal/bookings/{booking_id}/sync")
async def sync_booking_payment(
    booking_id: UUID,
    _: None = Depends(verify_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    """Reconcile a booking payment from Stripe when a browser returns before webhook delivery."""
    _require_stripe_key()
    session = _require_database(db)
    repository = PaymentRepository(session)
    payment = await repository.get_by_booking_id(booking_id)
    if payment is None:
        return {"booking_id": str(booking_id), "payment_status": "not_started"}

    try:
        intent = await run_in_threadpool(
            stripe_gateway.retrieve_payment_intent, payment.stripe_payment_intent_id
        )
    except stripe.StripeError as exc:
        raise HTTPException(status_code=502, detail="Stripe could not retrieve the payment status.") from exc

    if intent.id != payment.stripe_payment_intent_id:
        raise HTTPException(status_code=409, detail="Stripe payment does not match this booking.")
    if intent.status == "succeeded":
        if (
            int(intent.amount_received or 0) != payment.amount_minor
            or intent.currency.lower() != payment.currency.lower()
        ):
            raise HTTPException(status_code=409, detail="Stripe payment amount does not match the booking.")
        sync_event_id = f"sync:{intent.id}"
        if not await repository.event_was_processed(sync_event_id):
            await repository.enqueue_successful_delivery(
                sync_event_id, "payment_intent.succeeded", payment
            )
    else:
        await repository.sync_payment_status(payment, intent.status)
    await session.commit()
    return {"booking_id": str(booking_id), "payment_status": intent.status}


@router.get("/internal/delivery-outbox/failed")
async def list_failed_deliveries(
    limit: int = 100,
    _: None = Depends(verify_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 500.")
    entries = await PaymentRepository(_require_database(db)).list_failed_deliveries(limit)
    return [
        {
            "event_id": entry.event_id,
            "payment_id": str(entry.payment_id),
            "attempt_count": entry.attempt_count,
            "last_error": entry.last_error,
            "created_at": entry.created_at,
        }
        for entry in entries
    ]


@router.post("/internal/delivery-outbox/{event_id}/retry")
async def retry_failed_delivery(
    event_id: str,
    _: None = Depends(verify_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    entry = await PaymentRepository(_require_database(db)).retry_failed_delivery(event_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Failed delivery event not found.")
    return {"event_id": entry.event_id, "status": entry.status}


@router.post("/webhooks/stripe", include_in_schema=True)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    if not stripe_signature:
        raise HTTPException(status_code=400, detail="Missing Stripe-Signature header.")
    try:
        event = await run_in_threadpool(
            stripe_gateway.construct_webhook_event,
            await request.body(),
            stripe_signature,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Stripe webhook verification is not configured.") from exc
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature or payload.") from exc

    repository = PaymentRepository(session)
    event_id = event["id"]
    if await repository.event_was_processed(event_id):
        return {"received": True}

    event_type = event["type"]
    payment_status = {
        "payment_intent.succeeded": "succeeded",
        "payment_intent.payment_failed": "requires_payment_method",
        "payment_intent.canceled": "canceled",
        "payment_intent.processing": "processing",
        "payment_intent.requires_action": "requires_action",
    }.get(event_type)
    intent = event["data"]["object"]
    payment = await repository.get_by_stripe_id(intent["id"])
    if payment is None:
        # Return a retryable response; the webhook can arrive before intent persistence.
        raise HTTPException(status_code=503, detail="Payment intent is not available yet.")
    if event_type == "payment_intent.succeeded":
        if int(intent.get("amount_received", intent.get("amount", 0))) != payment.amount_minor or intent.get("currency", "").lower() != payment.currency.lower():
            raise HTTPException(status_code=400, detail="Stripe payment amount does not match the payment record.")
        await repository.enqueue_successful_delivery(event_id, event_type, payment)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if await repository.event_was_processed(event_id):
                return {"received": True}
            raise
        return {"received": True, "delivery_queued": True}
    try:
        await repository.update_from_event(
            event_id=event_id,
            event_type=event_type,
            intent_id=intent["id"],
            status=payment_status or intent.get("status", "unknown"),
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Stripe retries events when it does not receive a 2xx response.
        if not await repository.event_was_processed(event_id):
            raise
    return {"received": True}
