from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from secrets import compare_digest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_optional_db
from app.core.security import current_identity, require_platform_admin
from app.repositories import BookingRepository
from app.schemas.booking import (
    BookingCreate,
    BookingAvailabilityQuery,
    AvailableVehicle,
    BookingPaymentDetails,
    BookingRead,
    InspectionDecision,
    PaymentConfirmation,
    PaymentIntentResult,
    ReceiptSummary,
)
from app.services.pricing import calculate_rental_price
from app.services.lifecycle import next_booking_status
from platform_security import CognitoIdentity

router = APIRouter(prefix="/bookings", tags=["Bookings"])


def verify_payment_service_key(
    service_key: str | None = Header(default=None, alias="X-Payment-Service-Key"),
) -> None:
    configured = get_settings().payment_to_booking_api_key
    if configured is None:
        raise HTTPException(status_code=503, detail="Payment callback access is not configured.")
    if service_key is None or not compare_digest(service_key, configured.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid payment service credentials.")


@router.post("/internal/payment-confirmations", response_model=BookingRead)
async def confirm_booking_payment(
    payload: PaymentConfirmation,
    _: None = Depends(verify_payment_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    repository = BookingRepository(session)
    booking = await repository.get_for_update(payload.booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    prior = await repository.get_processed_payment_event(payload.stripe_event_id)
    if prior:
        if (
            prior.booking_id != booking.id
            or booking.payment_id != payload.payment_id
            or booking.stripe_payment_intent_id != payload.stripe_payment_intent_id
        ):
            raise HTTPException(status_code=409, detail="Payment event was already used.")
        return booking
    if booking.amount_minor != payload.amount_minor or booking.currency.lower() != payload.currency.lower():
        raise HTTPException(status_code=409, detail="Payment amount does not match the booking.")
    if (
        booking.status in {"confirmed", "active", "awaiting_inspection", "inspection_failed", "completed"}
        and booking.payment_id == payload.payment_id
        and booking.stripe_payment_intent_id == payload.stripe_payment_intent_id
    ):
        await repository.record_payment_event(payload.stripe_event_id, booking.id)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(status_code=409, detail="Payment event was already applied.") from exc
        return booking
    hold_active = (
        booking.status == "pending"
        and booking.expires_at is not None
        and booking.expires_at > datetime.now(UTC)
    )
    if not hold_active:
        may_restore_expired = (
            booking.status in {"pending", "expired"}
            and await repository.can_confirm_expired_paid_booking(booking)
        )
        if not may_restore_expired:
            raise HTTPException(status_code=409, detail="Booking hold expired and the vehicle is no longer available.")
    previous_status = booking.status
    booking.status = "confirmed"
    booking.payment_id = payload.payment_id
    booking.stripe_payment_intent_id = payload.stripe_payment_intent_id
    await repository.record_status_event(
        booking, previous_status, "confirmed", f"stripe:{payload.stripe_event_id}"
    )
    await repository.record_payment_event(payload.stripe_event_id, booking.id)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Payment was already applied to another booking.") from exc
    return booking


@router.get("/internal/{booking_id}/payment-details", response_model=BookingPaymentDetails)
async def get_internal_payment_details(
    booking_id: UUID,
    _: None = Depends(verify_payment_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    booking = await BookingRepository(_require_database(db)).get(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.status != "pending" or booking.expires_at is None or booking.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=409, detail="Booking hold has expired or is no longer payable.")
    if booking.amount_minor is None:
        raise HTTPException(status_code=409, detail="Booking has no calculated payment amount.")
    return booking


def _require_database(db: AsyncSession | None) -> AsyncSession:
    if db is None:
        raise HTTPException(status_code=503, detail="Booking storage is not configured.")
    return db


def _customer_id(identity: CognitoIdentity) -> UUID:
    try:
        return UUID(identity.subject)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="The Cognito subject is not a UUID.") from exc


async def _load_active_vehicle(vehicle_id: UUID) -> dict[str, str]:
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{settings.car_service_url.rstrip('/')}/vehicles/{vehicle_id}")
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Vehicle inventory is unavailable.") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Active vehicle not found.")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Vehicle inventory is unavailable.")
    vehicle = response.json()
    if vehicle.get("status") != "active":
        raise HTTPException(status_code=409, detail="The vehicle is not available for booking.")
    return vehicle


async def _require_rental_eligibility(identity: CognitoIdentity) -> None:
    """Fail closed unless auth-service confirms a verified, KYC-approved renter."""
    settings = get_settings()
    if settings.auth_service_api_key is None:
        raise HTTPException(status_code=503, detail="Driver verification is not available. Contact support before renting.")
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(
                f"{settings.auth_service_url.rstrip('/')}/auth/internal/users/{identity.subject}/rental-eligibility",
                headers={"X-Auth-Service-Key": settings.auth_service_api_key.get_secret_value()},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Driver verification is temporarily unavailable.") from exc
    if response.status_code == 403:
        raise HTTPException(status_code=403, detail="Verify your email and submit your driver licence and identity document before renting.")
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Driver verification is temporarily unavailable.")
    result = response.json()
    if result.get("eligible") is not True:
        state = result.get("status")
        detail = {
            "not_submitted": "Submit your driver licence and identity document before renting.",
            "pending": "Your driver licence and identity documents are awaiting administrator approval.",
            "rejected": "A verification document was rejected. Upload a replacement before renting.",
        }.get(state, "Complete driver and identity verification before renting.")
        raise HTTPException(status_code=403, detail=detail)


@router.post("", response_model=BookingRead, status_code=status.HTTP_201_CREATED)
async def create_booking(
    payload: BookingCreate,
    identity: CognitoIdentity = Depends(current_identity),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    if not payload.agreement_accepted:
        raise HTTPException(status_code=422, detail="Accept the rental agreement before reserving a vehicle.")
    settings = get_settings()
    if payload.agreement_version != settings.rental_agreement_version:
        raise HTTPException(status_code=409, detail="The rental agreement has changed. Review and accept the current version.")
    await _require_rental_eligibility(identity)
    vehicle = await _load_active_vehicle(payload.vehicle_id)
    try:
        amount_minor = calculate_rental_price(
            payload.pickup_at, payload.return_at, vehicle["hourly_rate"]
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    repository = BookingRepository(session)
    try:
        booking = await repository.create(
            payload,
            customer_id=_customer_id(identity),
            amount_minor=amount_minor,
            vehicle=vehicle,
            actor=identity.subject,
        )
        if booking is None:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail="The vehicle is already held or booked for part of this time window.",
            )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail="The vehicle is already held or booked for part of this time window.",
        ) from exc
    return booking


@router.get("/availability", response_model=list[AvailableVehicle])
async def list_available_vehicles(
    pickup_at: datetime,
    return_at: datetime,
    make: str | None = Query(default=None, min_length=1, max_length=80),
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession | None = Depends(get_optional_db),
):
    try:
        window = BookingAvailabilityQuery(pickup_at=pickup_at, return_at=return_at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(
                f"{settings.car_service_url.rstrip('/')}/vehicles",
                params={
                    "status": "active", "limit": limit, "offset": offset,
                    **({"make": make.strip()} if make else {}),
                },
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Vehicle inventory is unavailable.") from exc
    if response.status_code != 200:
        raise HTTPException(status_code=503, detail="Vehicle inventory is unavailable.")
    vehicles = response.json()
    session = _require_database(db)
    repository = BookingRepository(session)
    expired = await repository.expire_pending_holds()
    if expired:
        await session.commit()
    unavailable = await repository.unavailable_vehicle_ids(
        [UUID(vehicle["id"]) for vehicle in vehicles],
        pickup_at=window.pickup_at,
        return_at=window.return_at,
    )
    return [
        AvailableVehicle.model_validate({
            **vehicle,
            "rental_total_minor": calculate_rental_price(
                window.pickup_at, window.return_at, vehicle["hourly_rate"]
            ),
            "rental_currency": "USD",
        })
        for vehicle in vehicles
        if UUID(vehicle["id"]) not in unavailable
    ]


@router.post("/{booking_id}/payment-intent", response_model=PaymentIntentResult)
async def create_booking_payment_intent(
    booking_id: UUID,
    idempotency_key: str = Header(min_length=1, max_length=255, alias="Idempotency-Key"),
    identity: CognitoIdentity = Depends(current_identity),
    db: AsyncSession | None = Depends(get_optional_db),
):
    booking = await BookingRepository(_require_database(db)).get(booking_id)
    if booking is None or booking.customer_id != _customer_id(identity):
        raise HTTPException(status_code=404, detail="Booking not found.")
    await _require_rental_eligibility(identity)
    if booking.status != "pending" or booking.expires_at is None or booking.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=409, detail="Booking hold has expired or is no longer payable.")
    settings = get_settings()
    if settings.payment_service_api_key is None:
        raise HTTPException(status_code=503, detail="Payment service access is not configured.")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{settings.payment_service_url.rstrip('/')}/payments/intents",
                headers={
                    "X-Payment-Service-Key": settings.payment_service_api_key.get_secret_value(),
                    "Idempotency-Key": idempotency_key,
                },
                json={"booking_id": str(booking.id)},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Payment service is unavailable.") from exc
    if response.status_code == 409:
        raise HTTPException(status_code=409, detail="The booking cannot be paid in its current state.")
    if response.status_code >= 500:
        raise HTTPException(status_code=503, detail="Payment service is unavailable.")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Payment service rejected the request.")
    return response.json()


@router.post("/{booking_id}/payment-status")
async def sync_booking_payment_status(
    booking_id: UUID,
    identity: CognitoIdentity = Depends(current_identity),
    db: AsyncSession | None = Depends(get_optional_db),
):
    booking = await BookingRepository(_require_database(db)).get(booking_id)
    if booking is None or booking.customer_id != _customer_id(identity):
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.status not in {"pending", "expired"}:
        successful_states = {
            "confirmed", "active", "awaiting_inspection", "inspection_failed", "completed"
        }
        return {
            "booking_id": str(booking.id),
            "booking_status": booking.status,
            "payment_status": "succeeded" if booking.status in successful_states else booking.status,
        }

    settings = get_settings()
    if settings.payment_service_api_key is None:
        raise HTTPException(status_code=503, detail="Payment service access is not configured.")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{settings.payment_service_url.rstrip('/')}/payments/internal/bookings/{booking.id}/sync",
                headers={"X-Payment-Service-Key": settings.payment_service_api_key.get_secret_value()},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Payment service is unavailable.") from exc
    if response.status_code >= 500:
        raise HTTPException(status_code=503, detail="Payment service is unavailable.")
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Payment service rejected the status check.")
    payment = response.json()
    return {
        "booking_id": str(booking.id),
        "booking_status": booking.status,
        "payment_status": payment.get("payment_status", "unknown"),
    }


@router.get("", response_model=list[BookingRead])
async def list_bookings(
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    identity: CognitoIdentity = Depends(current_identity),
    db: AsyncSession | None = Depends(get_optional_db),
):
    repository = BookingRepository(_require_database(db))
    return await repository.list_for_customer(
        _customer_id(identity), limit=limit, offset=offset
    )


@router.get("/operations", response_model=list[BookingRead])
async def list_bookings_for_operations(
    status_filter: Literal[
        "pending", "confirmed", "active", "awaiting_inspection",
        "inspection_failed", "completed", "cancelled", "expired",
    ] | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    _: CognitoIdentity = Depends(require_platform_admin),
    db: AsyncSession | None = Depends(get_optional_db),
):
    """List bookings across customers for the admin operations workspace."""
    return await BookingRepository(_require_database(db)).list_for_operations(
        status=status_filter, limit=limit, offset=offset
    )


@router.get("/{booking_id}", response_model=BookingRead)
async def get_booking(
    booking_id: UUID,
    identity: CognitoIdentity = Depends(current_identity),
    db: AsyncSession | None = Depends(get_optional_db),
):
    booking = await BookingRepository(_require_database(db)).get(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.customer_id != _customer_id(identity) and "platform-admin" not in identity.groups:
        raise HTTPException(status_code=404, detail="Booking not found.")
    return booking


@router.get("/{booking_id}/receipt", response_model=ReceiptSummary)
async def get_booking_receipt(
    booking_id: UUID,
    identity: CognitoIdentity = Depends(current_identity),
    db: AsyncSession | None = Depends(get_optional_db),
):
    booking = await BookingRepository(_require_database(db)).get(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.customer_id != _customer_id(identity) and "platform-admin" not in identity.groups:
        raise HTTPException(status_code=404, detail="Booking not found.")
    settings = get_settings()
    if settings.receipt_service_api_key is None:
        raise HTTPException(status_code=503, detail="Receipt service access is not configured.")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{settings.receipt_service_url.rstrip('/')}/receipts/internal/by-booking/{booking_id}",
                headers={"X-Receipt-Service-Key": settings.receipt_service_api_key.get_secret_value()},
            )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Receipt service is unavailable.") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    if response.status_code >= 400:
        raise HTTPException(status_code=503, detail="Receipt service is unavailable.")
    return response.json()


@router.post("/{booking_id}/cancel", response_model=BookingRead)
async def cancel_booking(
    booking_id: UUID,
    identity: CognitoIdentity = Depends(require_platform_admin),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    repository = BookingRepository(session)
    booking = await repository.get_for_update(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    if booking.status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only unpaid pending bookings can be cancelled until refund policy is defined.",
        )
    previous_status = booking.status
    booking.status = next_booking_status(
        previous_status,
        "cancel",
        now=datetime.now(UTC),
        pickup_at=booking.pickup_at,
        return_at=booking.return_at,
    )
    await repository.record_status_event(
        booking, previous_status, booking.status, identity.subject, "Administrator cancelled unpaid hold"
    )
    await session.commit()
    return booking


@router.post("/{booking_id}/start", response_model=BookingRead)
async def start_booking(
    booking_id: UUID,
    identity: CognitoIdentity = Depends(require_platform_admin),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    repository = BookingRepository(session)
    booking = await repository.get_for_update(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    now = datetime.now(UTC)
    previous_status = booking.status
    try:
        booking.status = next_booking_status(
            previous_status, "start", now=now,
            pickup_at=booking.pickup_at, return_at=booking.return_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await repository.record_status_event(booking, previous_status, booking.status, identity.subject)
    await session.commit()
    return booking


@router.post("/{booking_id}/return", response_model=BookingRead)
async def return_booking(
    booking_id: UUID,
    identity: CognitoIdentity = Depends(require_platform_admin),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    repository = BookingRepository(session)
    booking = await repository.get_for_update(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    previous_status = booking.status
    try:
        booking.status = next_booking_status(
            previous_status, "return", now=datetime.now(UTC),
            pickup_at=booking.pickup_at, return_at=booking.return_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await repository.record_status_event(booking, previous_status, booking.status, identity.subject)
    await session.commit()
    return booking


@router.post("/{booking_id}/return-request", response_model=BookingRead)
async def request_booking_return(
    booking_id: UUID,
    identity: CognitoIdentity = Depends(current_identity),
    db: AsyncSession | None = Depends(get_optional_db),
):
    """Customer reports the vehicle returned once the booked rental window ends."""
    session = _require_database(db)
    repository = BookingRepository(session)
    booking = await repository.get_for_update(booking_id)
    if booking is None or booking.customer_id != _customer_id(identity):
        raise HTTPException(status_code=404, detail="Booking not found.")
    now = datetime.now(UTC)
    if booking.status != "active":
        raise HTTPException(status_code=409, detail="Only an active rental can be returned.")
    if booking.return_at > now:
        raise HTTPException(status_code=409, detail="You can report the return after the scheduled rental period ends.")
    previous_status = booking.status
    booking.status = next_booking_status(
        previous_status, "return", now=now,
        pickup_at=booking.pickup_at, return_at=booking.return_at,
    )
    await repository.record_status_event(
        booking, previous_status, booking.status, identity.subject,
        "Customer reported the vehicle returned; awaiting administrator inspection",
    )
    await session.commit()
    return booking


@router.post("/{booking_id}/inspection", response_model=BookingRead)
async def inspect_return(
    booking_id: UUID,
    payload: InspectionDecision,
    identity: CognitoIdentity = Depends(require_platform_admin),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    repository = BookingRepository(session)
    booking = await repository.get_for_update(booking_id)
    if booking is None:
        raise HTTPException(status_code=404, detail="Booking not found.")
    previous_status = booking.status
    try:
        action = "approve_inspection" if payload.approved else "reject_inspection"
        booking.status = next_booking_status(
            previous_status, action,
            now=datetime.now(UTC), pickup_at=booking.pickup_at, return_at=booking.return_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await repository.record_status_event(
        booking, previous_status, booking.status, identity.subject, payload.note
    )
    await session.commit()
    return booking
