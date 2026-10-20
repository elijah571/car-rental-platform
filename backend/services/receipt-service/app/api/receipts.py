from secrets import compare_digest
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_optional_db
from app.repositories import ReceiptRepository
from app.schemas.receipt import ReceiptCreate, ReceiptRead

router = APIRouter(prefix="/receipts", tags=["Receipts"])


def _receipt_matches_payload(receipt, payload: ReceiptCreate) -> bool:
    for field, value in payload.model_dump().items():
        stored_value = getattr(receipt, field)
        if isinstance(value, datetime) and isinstance(stored_value, datetime):
            stored_value = (
                stored_value.replace(tzinfo=UTC)
                if stored_value.tzinfo is None
                else stored_value.astimezone(UTC)
            )
            value = value.astimezone(UTC)
        if stored_value != value:
            return False
    return True


def verify_service_key(
    service_key: str | None = Header(default=None, alias="X-Receipt-Service-Key"),
) -> None:
    configured_key = get_settings().receipt_service_api_key
    if configured_key is None:
        raise HTTPException(status_code=503, detail="Receipt service access is not configured.")
    if service_key is None or not compare_digest(service_key, configured_key.get_secret_value()):
        raise HTTPException(status_code=401, detail="Invalid receipt service credentials.")


def require_database(db: AsyncSession | None) -> AsyncSession:
    if db is None:
        raise HTTPException(status_code=503, detail="Receipt storage is not configured.")
    return db


@router.post("", response_model=ReceiptRead, status_code=status.HTTP_201_CREATED)
async def create_receipt(
    payload: ReceiptCreate,
    idempotency_key: str = Header(min_length=1, max_length=255, alias="Idempotency-Key"),
    _: None = Depends(verify_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = require_database(db)
    repository = ReceiptRepository(session)
    existing = await repository.get_by_idempotency_key(idempotency_key)
    if existing is not None:
        if not _receipt_matches_payload(existing, payload):
            raise HTTPException(
                status_code=409,
                detail="The idempotency key belongs to a different receipt.",
            )
        return existing
    try:
        receipt = await repository.create(idempotency_key, payload)
        await session.commit()
        return receipt
    except IntegrityError as exc:
        await session.rollback()
        existing = await repository.get_by_idempotency_key(idempotency_key)
        if existing is not None:
            if not _receipt_matches_payload(existing, payload):
                raise HTTPException(
                    status_code=409,
                    detail="The idempotency key belongs to a different receipt.",
                ) from exc
            return existing
        raise HTTPException(
            status_code=409,
            detail="A receipt already exists for this booking or payment.",
        ) from exc


@router.get("/{receipt_id}", response_model=ReceiptRead)
async def get_receipt(
    receipt_id: UUID,
    _: None = Depends(verify_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    receipt = await ReceiptRepository(require_database(db)).get(receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return receipt


@router.get("/internal/by-booking/{booking_id}", response_model=ReceiptRead)
async def get_receipt_for_booking(
    booking_id: UUID,
    _: None = Depends(verify_service_key),
    db: AsyncSession | None = Depends(get_optional_db),
):
    receipt = await ReceiptRepository(require_database(db)).get_by_booking_id(booking_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found.")
    return receipt
