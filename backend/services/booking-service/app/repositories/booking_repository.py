from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Booking, BookingStatusEvent, ProcessedPaymentEvent
from app.schemas.booking import BookingCreate


def _blocks_vehicle_for_window(pickup_at: datetime, return_at: datetime):
    return or_(
        Booking.status.in_(("active", "awaiting_inspection", "inspection_failed")),
        and_(
            Booking.status.in_(("pending", "confirmed")),
            Booking.pickup_at < return_at,
            Booking.return_at > pickup_at,
        ),
    )


class BookingRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        payload: BookingCreate,
        *,
        customer_id: UUID,
        amount_minor: int,
        vehicle: dict[str, str],
        actor: str,
    ) -> Booking | None:
        await self.expire_pending_holds()
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            await self.session.execute(
                select(
                    func.pg_advisory_xact_lock(
                        func.hashtextextended(str(payload.vehicle_id), 0)
                    )
                )
            )
        overlap = await self.session.scalar(
            select(Booking.id)
            .where(
                Booking.vehicle_id == payload.vehicle_id,
                _blocks_vehicle_for_window(payload.pickup_at, payload.return_at),
            )
            .limit(1)
        )
        if overlap is not None:
            return None

        hold_minutes = get_settings().booking_hold_minutes
        expires_at = datetime.now(UTC) + timedelta(minutes=hold_minutes)
        booking = Booking(
            **payload.model_dump(exclude={"agreement_accepted"}),
            customer_id=customer_id,
            expires_at=expires_at,
            amount_minor=amount_minor,
            currency="USD",
            vehicle_make=vehicle["make"],
            vehicle_model=vehicle["model"],
            vehicle_color=vehicle["color"],
            vehicle_license_plate=vehicle["registration_number"],
            status="pending",
        )
        self.session.add(booking)
        await self.session.flush()
        await self.record_status_event(booking, None, "pending", actor)
        return booking

    async def expire_pending_holds(self) -> list[UUID]:
        result = await self.session.scalars(
            update(Booking)
            .where(
                Booking.status == "pending",
                Booking.expires_at <= func.now(),
            )
            .values(status="expired", updated_at=func.now())
            .returning(Booking.id)
        )
        booking_ids = list(result.all())
        for booking_id in booking_ids:
            self.session.add(
                BookingStatusEvent(
                    booking_id=booking_id,
                    from_status="pending",
                    to_status="expired",
                    actor="system:hold-expiry",
                    note="Unpaid hold expired",
                )
            )
        return booking_ids

    async def get(self, booking_id: UUID) -> Booking | None:
        return await self.session.get(Booking, booking_id)

    async def get_for_update(self, booking_id: UUID) -> Booking | None:
        result = await self.session.execute(
            select(Booking).where(Booking.id == booking_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def can_confirm_expired_paid_booking(self, booking: Booking) -> bool:
        """Allow a completed charge to keep its reservation only if the car is still free."""
        bind = self.session.get_bind()
        if bind.dialect.name == "postgresql":
            await self.session.execute(
                select(func.pg_advisory_xact_lock(func.hashtextextended(str(booking.vehicle_id), 0)))
            )
        conflict = await self.session.scalar(
            select(Booking.id)
            .where(
                Booking.id != booking.id,
                Booking.vehicle_id == booking.vehicle_id,
                _blocks_vehicle_for_window(booking.pickup_at, booking.return_at),
            )
            .limit(1)
        )
        return conflict is None

    async def record_status_event(
        self,
        booking: Booking,
        from_status: str | None,
        to_status: str,
        actor: str,
        note: str | None = None,
    ) -> None:
        self.session.add(
            BookingStatusEvent(
                booking_id=booking.id,
                from_status=from_status,
                to_status=to_status,
                actor=actor,
                note=note,
            )
        )
        await self.session.flush()

    async def get_processed_payment_event(self, event_id: str) -> ProcessedPaymentEvent | None:
        return await self.session.get(ProcessedPaymentEvent, event_id)

    async def record_payment_event(self, event_id: str, booking_id: UUID) -> None:
        self.session.add(ProcessedPaymentEvent(event_id=event_id, booking_id=booking_id))
        await self.session.flush()

    async def list_for_customer(
        self,
        customer_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Booking]:
        result = await self.session.scalars(
            select(Booking)
            .where(Booking.customer_id == customer_id)
            .order_by(Booking.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.all())

    async def list_for_operations(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Booking]:
        statement = select(Booking).order_by(Booking.created_at.desc())
        if status is not None:
            statement = statement.where(Booking.status == status)
        result = await self.session.scalars(statement.limit(limit).offset(offset))
        return list(result.all())

    async def list_active_returns_due_before(
        self,
        cutoff: datetime,
        *,
        after: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Booking]:
        statement = select(Booking).where(
            Booking.status == "active",
            Booking.return_at <= cutoff,
        )
        if after is not None:
            statement = statement.where(Booking.return_at > after)
        result = await self.session.scalars(
            statement.order_by(Booking.return_at.asc(), Booking.id.asc()).limit(limit).offset(offset)
        )
        return list(result.all())

    async def unavailable_vehicle_ids(
        self,
        vehicle_ids: list[UUID],
        *,
        pickup_at: datetime,
        return_at: datetime,
    ) -> set[UUID]:
        if not vehicle_ids:
            return set()
        # A vehicle stays out of the customer catalog for the full time it is
        # rented and while its return is awaiting inspection. Pending and
        # confirmed reservations only block their actual time window.
        result = await self.session.scalars(
            select(Booking.vehicle_id).where(
                Booking.vehicle_id.in_(vehicle_ids),
                _blocks_vehicle_for_window(pickup_at, return_at),
            )
        )
        return set(result.all())

    async def cancel_pending(self, booking_id: UUID) -> Booking | None:
        booking = await self.get(booking_id)
        if booking is None or booking.status != "pending":
            return None
        booking.status = "cancelled"
        await self.session.flush()
        return booking
