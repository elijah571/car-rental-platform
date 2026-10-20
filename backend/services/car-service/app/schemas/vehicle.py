from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

VehicleStatus = Literal["active", "maintenance", "retired"]
Transmission = Literal["automatic", "manual"]
FuelType = Literal["petrol", "diesel", "hybrid", "electric"]


class VehicleCreate(BaseModel):
    make: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=80)
    color: str = Field(min_length=1, max_length=60)
    year: int = Field(ge=1900, le=2100)
    category: str = Field(min_length=1, max_length=40)
    seats: int = Field(ge=1, le=20)
    transmission: Transmission
    fuel_type: FuelType
    hourly_rate: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    registration_number: str = Field(min_length=1, max_length=32)
    status: VehicleStatus = "active"

    @field_validator("make", "model", "color", "category", "registration_number")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("registration_number")
    @classmethod
    def normalize_registration(cls, value: str) -> str:
        return value.strip().upper()


class VehicleUpdate(BaseModel):
    make: str | None = Field(default=None, min_length=1, max_length=80)
    model: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, min_length=1, max_length=60)
    year: int | None = Field(default=None, ge=1900, le=2100)
    category: str | None = Field(default=None, min_length=1, max_length=40)
    seats: int | None = Field(default=None, ge=1, le=20)
    transmission: Transmission | None = None
    fuel_type: FuelType | None = None
    hourly_rate: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    registration_number: str | None = Field(default=None, min_length=1, max_length=32)
    status: VehicleStatus | None = None

    @model_validator(mode="after")
    def require_update_fields(self):
        if not any(getattr(self, field) is not None for field in self.model_fields_set):
            raise ValueError("At least one field must be provided")
        return self

    @field_validator("make", "model", "color", "category")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned

    @field_validator("registration_number")
    @classmethod
    def normalize_optional_registration(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None


class VehicleRead(BaseModel):
    id: UUID
    make: str
    model: str
    color: str
    year: int
    category: str
    seats: int
    transmission: Transmission
    fuel_type: FuelType
    hourly_rate: Decimal
    currency: str
    registration_number: str
    status: VehicleStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
