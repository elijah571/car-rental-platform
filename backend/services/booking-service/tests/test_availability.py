import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import Booking
from app.repositories import BookingRepository
from app.schemas.booking import BookingAvailabilityQuery, BookingCreate


def test_availability_query_requires_a_valid_timezone_aware_future_window():
    with pytest.raises(ValidationError, match="timezone"):
        BookingAvailabilityQuery(
            pickup_at=datetime(2030, 1, 1),
            return_at=datetime(2030, 1, 1, 1),
        )
    with pytest.raises(ValidationError, match="later"):
        BookingAvailabilityQuery(
            pickup_at=datetime(2030, 1, 1, tzinfo=UTC),
            return_at=datetime(2030, 1, 1, tzinfo=UTC),
        )


def test_availability_hides_rented_cars_until_inspection_and_checks_reservations_by_time():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        pickup = datetime(2030, 1, 1, 10, tzinfo=UTC)
        return_at = pickup + timedelta(hours=2)
        active_vehicle, inspection_vehicle, reserved_vehicle, adjacent_vehicle, completed_vehicle = [uuid4() for _ in range(5)]
        async with sessions() as session:
            session.add_all([
                Booking(
                    customer_id=uuid4(), vehicle_id=active_vehicle,
                    pickup_at=pickup - timedelta(days=3), return_at=pickup - timedelta(days=1),
                    amount_minor=10000, currency="USD", status="active",
                ),
                Booking(
                    customer_id=uuid4(), vehicle_id=inspection_vehicle,
                    pickup_at=pickup - timedelta(days=3), return_at=pickup - timedelta(days=1),
                    amount_minor=10000, currency="USD", status="awaiting_inspection",
                ),
                Booking(
                    customer_id=uuid4(), vehicle_id=reserved_vehicle,
                    pickup_at=pickup + timedelta(minutes=30), return_at=return_at + timedelta(hours=1),
                    amount_minor=10000, currency="USD", status="confirmed",
                ),
                Booking(
                    customer_id=uuid4(), vehicle_id=adjacent_vehicle,
                    pickup_at=pickup - timedelta(hours=1), return_at=pickup,
                    amount_minor=10000, currency="USD", status="confirmed",
                ),
                Booking(
                    customer_id=uuid4(), vehicle_id=completed_vehicle,
                    pickup_at=pickup - timedelta(days=3), return_at=pickup - timedelta(days=1),
                    amount_minor=10000, currency="USD", status="completed",
                ),
            ])
            await session.commit()
            unavailable = await BookingRepository(session).unavailable_vehicle_ids(
                [active_vehicle, inspection_vehicle, reserved_vehicle, adjacent_vehicle, completed_vehicle],
                pickup_at=pickup, return_at=return_at
            )
        await engine.dispose()
        assert unavailable == {active_vehicle, inspection_vehicle, reserved_vehicle}

    asyncio.run(run())


def test_booking_creation_rejects_a_rental_after_active_booking_end():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        vehicle_id = uuid4()
        now = datetime.now(UTC)
        async with sessions() as session:
            session.add(Booking(
                customer_id=uuid4(), vehicle_id=vehicle_id,
                pickup_at=now - timedelta(days=3), return_at=now - timedelta(days=1),
                amount_minor=10000, currency="USD", status="active",
            ))
            await session.commit()
            payload = BookingCreate(
                vehicle_id=vehicle_id,
                pickup_at=now + timedelta(days=1),
                return_at=now + timedelta(days=2),
            )
            booking = await BookingRepository(session).create(
                payload,
                customer_id=uuid4(),
                amount_minor=10000,
                vehicle={
                    "make": "Test", "model": "Car", "color": "Blue",
                    "registration_number": "TEST-1",
                },
                actor="test",
            )
        await engine.dispose()
        assert booking is None

    asyncio.run(run())
