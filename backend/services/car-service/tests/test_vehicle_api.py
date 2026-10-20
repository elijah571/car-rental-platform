import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base, get_optional_db
from app.core.security import current_identity, optional_identity
from app.main import app
from platform_security import CognitoIdentity


@pytest.fixture
def vehicle_api(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'vehicles.db'}")
    asyncio.run(_create_schema(engine))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    identity = {"value": None}

    async def override_database():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_optional_db] = override_database
    app.dependency_overrides[current_identity] = lambda: identity["value"]
    app.dependency_overrides[optional_identity] = lambda: identity["value"]
    with TestClient(app) as client:
        yield client, identity
    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())


async def _create_schema(engine):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _identity(*groups: str) -> CognitoIdentity:
    return CognitoIdentity(
        subject=str(uuid4()),
        client_id="test-client",
        groups=frozenset(groups),
        scopes=frozenset(),
    )


def _vehicle_payload(registration_number="TEST-100"):
    return {
        "make": " Toyota ",
        "model": " Corolla ",
        "color": " Blue ",
        "year": 2024,
        "category": "Sedan",
        "seats": 5,
        "transmission": "automatic",
        "fuel_type": "hybrid",
        "hourly_rate": "85.50",
        "currency": "USD",
        "registration_number": registration_number,
    }


def test_vehicle_writes_require_admin_and_public_reads_hide_retired(vehicle_api):
    client, identity = vehicle_api
    identity["value"] = _identity()
    denied = client.post("/vehicles", json=_vehicle_payload())
    assert denied.status_code == 403

    identity["value"] = _identity("platform-admin")
    created = client.post("/vehicles", json=_vehicle_payload(" ab-123 "))
    assert created.status_code == 201
    vehicle = created.json()
    assert vehicle["make"] == "Toyota"
    assert vehicle["registration_number"] == "AB-123"

    listed = client.get("/vehicles")
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [vehicle["id"]]

    updated = client.patch(
        f"/vehicles/{vehicle['id']}",
        json={"hourly_rate": "90.00", "color": "Silver"},
    )
    assert updated.status_code == 200
    assert updated.json()["hourly_rate"] == "90.00"
    assert updated.json()["color"] == "Silver"

    retired = client.delete(f"/vehicles/{vehicle['id']}")
    assert retired.status_code == 200
    assert retired.json()["status"] == "retired"
    assert client.get(f"/vehicles/{vehicle['id']}").status_code == 404
    assert client.get("/vehicles").json() == []

    admin_inventory = client.get("/vehicles?status=retired")
    assert admin_inventory.status_code == 200
    assert [item["id"] for item in admin_inventory.json()] == [vehicle["id"]]


def test_vehicle_registration_is_unique_and_filters_validate(vehicle_api):
    client, identity = vehicle_api
    identity["value"] = _identity("platform-admin")
    first = client.post("/vehicles", json=_vehicle_payload("DUP-001"))
    assert first.status_code == 201
    duplicate = client.post("/vehicles", json=_vehicle_payload(" dup-001 "))
    assert duplicate.status_code == 409

    assert client.get("/vehicles?min_seats=0").status_code == 422
    assert client.post("/vehicles", json={**_vehicle_payload(), "hourly_rate": 0}).status_code == 422
