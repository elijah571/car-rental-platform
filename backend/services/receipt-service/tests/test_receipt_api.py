import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import receipts as receipt_api
from app.core.database import Base, get_optional_db
from app.main import app


@pytest.fixture
def receipt_api_client(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'receipts.db'}")
    asyncio.run(_create_schema(engine))
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def override_database():
        async with sessions() as session:
            yield session

    monkeypatch.setattr(
        receipt_api,
        "get_settings",
        lambda: type("Settings", (), {"receipt_service_api_key": SecretStr("receipt-test-key")})(),
    )
    app.dependency_overrides[get_optional_db] = override_database
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


async def _create_schema(engine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _payload():
    pickup = datetime.now(UTC) + timedelta(days=1)
    return {
        "booking_id": str(uuid4()),
        "payment_id": str(uuid4()),
        "stripe_payment_intent_id": f"pi_{uuid4().hex}",
        "customer_id": str(uuid4()),
        "rental_start": pickup.isoformat(),
        "rental_end": (pickup + timedelta(days=1)).isoformat(),
        "amount_minor": 22500,
        "currency": "usd",
        "vehicle_make": "Toyota",
        "vehicle_model": "Corolla",
        "vehicle_color": "Blue",
        "vehicle_license_plate": "TEST-123",
    }


def test_receipt_creation_requires_service_key_and_is_payload_bound_idempotent(receipt_api_client):
    client = receipt_api_client
    payload = _payload()
    unauthenticated = client.post(
        "/receipts", headers={"Idempotency-Key": "receipt-event-1"}, json=payload
    )
    assert unauthenticated.status_code == 401

    headers = {
        "X-Receipt-Service-Key": "receipt-test-key",
        "Idempotency-Key": "receipt-event-1",
    }
    created = client.post("/receipts", headers=headers, json=payload)
    assert created.status_code == 201
    receipt = created.json()
    assert receipt["currency"] == "USD"
    assert receipt["amount_minor"] == 22500

    duplicate = client.post("/receipts", headers=headers, json=payload)
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == receipt["id"]

    conflicting = client.post(
        "/receipts",
        headers=headers,
        json={**payload, "amount_minor": 23000},
    )
    assert conflicting.status_code == 409

    fetched = client.get(
        f"/receipts/{receipt['id']}",
        headers={"X-Receipt-Service-Key": "receipt-test-key"},
    )
    assert fetched.status_code == 200
    assert fetched.json() == receipt


def test_receipt_validation_and_internal_booking_lookup(receipt_api_client):
    client = receipt_api_client
    headers = {
        "X-Receipt-Service-Key": "receipt-test-key",
        "Idempotency-Key": "receipt-event-2",
    }
    invalid = client.post(
        "/receipts",
        headers=headers,
        json={**_payload(), "rental_end": "not-a-time"},
    )
    assert invalid.status_code == 422

    missing_booking = client.get(
        f"/receipts/internal/by-booking/{uuid4()}",
        headers={"X-Receipt-Service-Key": "receipt-test-key"},
    )
    assert missing_booking.status_code == 404
