import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_optional_db
from app.core.security import current_identity
from app.main import app
from app.models import Booking
from platform_security import CognitoIdentity


def test_operations_booking_list_requires_admin_and_filters_status(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'operations.db'}")
    asyncio.run(_create_schema(engine))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    subject = str(uuid4())

    async def override_database():
        async with sessions() as session:
            yield session

    async def add_bookings():
        async with sessions() as session:
            now = datetime.now(UTC) + timedelta(days=2)
            session.add_all([
                Booking(
                    customer_id=uuid4(), vehicle_id=uuid4(), pickup_at=now,
                    return_at=now + timedelta(hours=2), amount_minor=20000,
                    currency="USD", status="pending", vehicle_make="Toyota",
                    vehicle_model="Camry", vehicle_color="Silver",
                    vehicle_license_plate="DW-TEST-1",
                ),
                Booking(
                    customer_id=uuid4(), vehicle_id=uuid4(), pickup_at=now,
                    return_at=now + timedelta(hours=2), amount_minor=20000,
                    currency="USD", status="confirmed", vehicle_make="BMW",
                    vehicle_model="3 Series", vehicle_color="Graphite",
                    vehicle_license_plate="DW-TEST-2",
                ),
            ])
            await session.commit()

    asyncio.run(add_bookings())
    app.dependency_overrides[get_optional_db] = override_database
    app.dependency_overrides[current_identity] = lambda: CognitoIdentity(
        subject=subject, client_id="test-client", groups=frozenset(), scopes=frozenset()
    )
    try:
        with TestClient(app) as client:
            assert client.get("/bookings/operations").status_code == 403
            app.dependency_overrides[current_identity] = lambda: CognitoIdentity(
                subject=subject, client_id="test-client",
                groups=frozenset({"platform-admin"}), scopes=frozenset(),
            )
            all_bookings = client.get("/bookings/operations")
            assert all_bookings.status_code == 200
            assert {row["status"] for row in all_bookings.json()} == {"pending", "confirmed"}

            pending = client.get("/bookings/operations?status=pending")
            assert pending.status_code == 200
            assert [row["status"] for row in pending.json()] == ["pending"]
            assert client.get("/bookings/operations?status=unknown").status_code == 422
    finally:
        app.dependency_overrides.clear()
        asyncio.run(engine.dispose())


async def _create_schema(engine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
