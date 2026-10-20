import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models import Booking
from app.repositories import BookingRepository
from app.schemas.booking import BookingAvailabilityQuery


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


def test_availability_excludes_only_overlapping_blocking_bookings():
    async def run():
        engine = create_async_engine("sqlite+aiosqlite://")
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        pickup = datetime(2030, 1, 1, 10, tzinfo=UTC)
        return_at = pickup + timedelta(hours=2)
        unavailable_vehicle, adjacent_vehicle = uuid4(), uuid4()
        async with sessions() as session:
            session.add_all([
                Booking(
                    customer_id=uuid4(), vehicle_id=unavailable_vehicle,
                    pickup_at=pickup + timedelta(minutes=30),
                    return_at=return_at + timedelta(hours=1),
                    amount_minor=10000, currency="USD", status="active",
                ),
                Booking(
                    customer_id=uuid4(), vehicle_id=adjacent_vehicle,
                    pickup_at=pickup - timedelta(hours=1), return_at=pickup,
                    amount_minor=10000, currency="USD", status="confirmed",
                ),
            ])
            await session.commit()
            unavailable = await BookingRepository(session).unavailable_vehicle_ids(
                [unavailable_vehicle, adjacent_vehicle], pickup_at=pickup, return_at=return_at
            )
        await engine.dispose()
        assert unavailable == {unavailable_vehicle}

    asyncio.run(run())
