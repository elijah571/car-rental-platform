from uuid import UUID

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentDeliveryOutbox, ProcessedStripeEvent


class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_intent_key(self, key: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.idempotency_key == key)
        )
        return result.scalar_one_or_none()

    async def get_by_booking_id(self, booking_id: UUID) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.booking_id == booking_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        return await self.session.get(Payment, payment_id)

    async def get_by_stripe_id(self, intent_id: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.stripe_payment_intent_id == intent_id)
        )
        return result.scalar_one_or_none()

    async def event_was_processed(self, event_id: str) -> bool:
        return await self.session.get(ProcessedStripeEvent, event_id) is not None

    async def create(
        self,
        *,
        booking_id: UUID,
        idempotency_key: str,
        intent_id: str,
        amount_minor: int,
        currency: str,
        status: str,
    ) -> Payment:
        payment = Payment(
            booking_id=booking_id,
            idempotency_key=idempotency_key,
            stripe_payment_intent_id=intent_id,
            amount_minor=amount_minor,
            currency=currency,
            status=status,
        )
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def update_from_event(self, event_id: str, event_type: str, intent_id: str, status: str):
        payment = await self.get_by_stripe_id(intent_id)
        self.session.add(ProcessedStripeEvent(event_id=event_id, event_type=event_type))
        if payment is not None and payment.status not in {
            "succeeded_pending_delivery",
            "succeeded",
            "succeeded_unapplied",
            "succeeded_delivery_failed",
        }:
            payment.status = status
        await self.session.flush()
        return payment

    async def enqueue_successful_delivery(self, event_id: str, event_type: str, payment: Payment) -> None:
        if payment.status in {
            "succeeded_pending_delivery",
            "succeeded",
            "succeeded_unapplied",
            "succeeded_delivery_failed",
        }:
            self.session.add(ProcessedStripeEvent(event_id=event_id, event_type=event_type))
            await self.session.flush()
            return
        self.session.add(
            PaymentDeliveryOutbox(
                event_id=event_id,
                event_type=event_type,
                payment_id=payment.id,
                status="pending",
            )
        )
        payment.status = "succeeded_pending_delivery"
        self.session.add(ProcessedStripeEvent(event_id=event_id, event_type=event_type))
        await self.session.flush()

    async def sync_payment_status(self, payment: Payment, status: str) -> None:
        if payment.status not in {
            "succeeded_pending_delivery",
            "succeeded",
            "succeeded_unapplied",
            "succeeded_delivery_failed",
        }:
            payment.status = status
            await self.session.flush()

    async def claim_next_delivery(self, *, lease_seconds: int = 60) -> PaymentDeliveryOutbox | None:
        now = datetime.now(UTC)
        eligible = or_(
            PaymentDeliveryOutbox.status == "pending",
            and_(
                PaymentDeliveryOutbox.status == "processing",
                PaymentDeliveryOutbox.locked_until <= now,
            ),
        )
        result = await self.session.execute(
            select(PaymentDeliveryOutbox)
            .where(
                eligible,
                PaymentDeliveryOutbox.next_attempt_at <= now,
            )
            .order_by(PaymentDeliveryOutbox.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return None
        entry.status = "processing"
        entry.locked_until = now + timedelta(seconds=lease_seconds)
        await self.session.commit()
        return entry

    async def mark_delivery_complete(self, entry: PaymentDeliveryOutbox) -> None:
        payment = await self.session.get(Payment, entry.payment_id)
        if payment is not None:
            payment.status = "succeeded"
        entry.status = "delivered"
        entry.locked_until = None
        entry.last_error = None
        await self.session.commit()

    async def mark_reconciliation_required(self, entry: PaymentDeliveryOutbox) -> None:
        payment = await self.session.get(Payment, entry.payment_id)
        if payment is not None:
            payment.status = "succeeded_unapplied"
        entry.status = "reconciliation_required"
        entry.locked_until = None
        await self.session.commit()

    async def mark_delivery_failed(
        self,
        entry: PaymentDeliveryOutbox,
        error: str,
        *,
        max_attempts: int = 20,
    ) -> None:
        entry.attempt_count += 1
        entry.last_error = error[:1000]
        entry.locked_until = None
        if entry.attempt_count >= max_attempts:
            entry.status = "failed"
            payment = await self.session.get(Payment, entry.payment_id)
            if payment is not None:
                payment.status = "succeeded_delivery_failed"
        else:
            entry.status = "pending"
            delay_seconds = min(30 * (2 ** (entry.attempt_count - 1)), 3600)
            entry.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        await self.session.commit()

    async def retry_failed_delivery(self, event_id: str) -> PaymentDeliveryOutbox | None:
        entry = await self.session.get(PaymentDeliveryOutbox, event_id)
        if entry is None or entry.status != "failed":
            return None
        entry.status = "pending"
        entry.attempt_count = 0
        entry.next_attempt_at = datetime.now(UTC)
        entry.locked_until = None
        entry.last_error = None
        payment = await self.session.get(Payment, entry.payment_id)
        if payment is not None:
            payment.status = "succeeded_pending_delivery"
        await self.session.commit()
        return entry

    async def list_failed_deliveries(self, limit: int = 100) -> list[PaymentDeliveryOutbox]:
        result = await self.session.execute(
            select(PaymentDeliveryOutbox)
            .where(PaymentDeliveryOutbox.status == "failed")
            .order_by(PaymentDeliveryOutbox.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())
