from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Receipt
from app.schemas.receipt import ReceiptCreate


class ReceiptRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_idempotency_key(self, key: str) -> Receipt | None:
        result = await self.session.execute(
            select(Receipt).where(Receipt.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def get(self, receipt_id: UUID) -> Receipt | None:
        return await self.session.get(Receipt, receipt_id)

    async def get_by_booking_id(self, booking_id: UUID) -> Receipt | None:
        result = await self.session.execute(
            select(Receipt).where(Receipt.booking_id == booking_id)
        )
        return result.scalar_one_or_none()

    async def create(self, key: str, payload: ReceiptCreate) -> Receipt:
        receipt_id = uuid4()
        receipt = Receipt(
            id=receipt_id,
            receipt_number=f"CR-{receipt_id.hex[:28].upper()}",
            idempotency_key=key,
            **payload.model_dump(),
        )
        self.session.add(receipt)
        await self.session.flush()
        return receipt
