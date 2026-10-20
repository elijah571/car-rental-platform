from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Vehicle
from app.schemas.vehicle import VehicleCreate, VehicleUpdate, VehicleStatus


class VehicleRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, payload: VehicleCreate) -> Vehicle:
        vehicle = Vehicle(**payload.model_dump())
        self.session.add(vehicle)
        await self.session.flush()
        return vehicle

    async def get(self, vehicle_id: UUID) -> Vehicle | None:
        return await self.session.get(Vehicle, vehicle_id)

    async def list(
        self,
        *,
        make: str | None = None,
        model: str | None = None,
        category: str | None = None,
        status: VehicleStatus | None = "active",
        min_seats: int | None = None,
        max_hourly_rate: Decimal | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Vehicle]:
        query = select(Vehicle)
        if make:
            query = query.where(Vehicle.make.ilike(f"%{make.strip()}%"))
        if model:
            query = query.where(Vehicle.model.ilike(f"%{model.strip()}%"))
        if category:
            query = query.where(Vehicle.category.ilike(category.strip()))
        if status:
            query = query.where(Vehicle.status == status)
        if min_seats is not None:
            query = query.where(Vehicle.seats >= min_seats)
        if max_hourly_rate is not None:
            query = query.where(Vehicle.hourly_rate <= max_hourly_rate)
        result = await self.session.scalars(
            query.order_by(Vehicle.make, Vehicle.model, Vehicle.year.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.all())

    async def update(
        self,
        vehicle_id: UUID,
        payload: VehicleUpdate,
    ) -> Vehicle | None:
        vehicle = await self.get(vehicle_id)
        if vehicle is None:
            return None
        for field, value in payload.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(vehicle, field, value)
        await self.session.flush()
        return vehicle

    async def retire(self, vehicle_id: UUID) -> Vehicle | None:
        vehicle = await self.get(vehicle_id)
        if vehicle is None:
            return None
        vehicle.status = "retired"
        await self.session.flush()
        return vehicle
