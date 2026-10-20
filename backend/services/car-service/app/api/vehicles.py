from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_optional_db
from app.core.security import optional_identity, require_platform_admin
from app.repositories import VehicleRepository
from app.schemas.vehicle import VehicleCreate, VehicleRead, VehicleStatus, VehicleUpdate

router = APIRouter(prefix="/vehicles", tags=["Vehicles"])


def _require_database(db: AsyncSession | None) -> AsyncSession:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Vehicle storage is not configured.",
        )
    return db


def _registration_conflict() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="A vehicle with that registration number already exists.",
    )


@router.post("", response_model=VehicleRead, status_code=status.HTTP_201_CREATED)
async def create_vehicle(
    payload: VehicleCreate,
    _: None = Depends(require_platform_admin),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    try:
        vehicle = await VehicleRepository(session).create(payload)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _registration_conflict() from exc
    return vehicle


@router.get("", response_model=list[VehicleRead])
async def list_vehicles(
    make: str | None = Query(default=None, min_length=1, max_length=80),
    model: str | None = Query(default=None, min_length=1, max_length=80),
    category: str | None = Query(default=None, min_length=1, max_length=40),
    vehicle_status: VehicleStatus | None = Query(default="active", alias="status"),
    min_seats: int | None = Query(default=None, ge=1, le=20),
    max_hourly_rate: Decimal | None = Query(default=None, gt=0),
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    identity=Depends(optional_identity),
    db: AsyncSession | None = Depends(get_optional_db),
):
    if vehicle_status != "active" and (
        identity is None or "platform-admin" not in identity.groups
    ):
        raise HTTPException(status_code=403, detail="Administrator access is required to list inactive vehicles.")
    return await VehicleRepository(_require_database(db)).list(
        make=make,
        model=model,
        category=category,
        status=vehicle_status,
        min_seats=min_seats,
        max_hourly_rate=max_hourly_rate,
        limit=limit,
        offset=offset,
    )


@router.get("/{vehicle_id}", response_model=VehicleRead)
async def get_vehicle(
    vehicle_id: UUID,
    db: AsyncSession | None = Depends(get_optional_db),
):
    vehicle = await VehicleRepository(_require_database(db)).get(vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    if vehicle.status != "active":
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    return vehicle


@router.patch("/{vehicle_id}", response_model=VehicleRead)
async def update_vehicle(
    vehicle_id: UUID,
    payload: VehicleUpdate,
    _: None = Depends(require_platform_admin),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    try:
        vehicle = await VehicleRepository(session).update(vehicle_id, payload)
        if vehicle is None:
            raise HTTPException(status_code=404, detail="Vehicle not found.")
        await session.commit()
        await session.refresh(vehicle)
    except IntegrityError as exc:
        await session.rollback()
        raise _registration_conflict() from exc
    return vehicle


@router.delete("/{vehicle_id}", response_model=VehicleRead)
async def retire_vehicle(
    vehicle_id: UUID,
    _: None = Depends(require_platform_admin),
    db: AsyncSession | None = Depends(get_optional_db),
):
    session = _require_database(db)
    vehicle = await VehicleRepository(session).retire(vehicle_id)
    if vehicle is None:
        raise HTTPException(status_code=404, detail="Vehicle not found.")
    await session.commit()
    await session.refresh(vehicle)
    return vehicle
