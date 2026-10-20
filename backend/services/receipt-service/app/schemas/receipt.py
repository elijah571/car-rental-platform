from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ReceiptCreate(BaseModel):
    booking_id: UUID
    payment_id: UUID
    stripe_payment_intent_id: str = Field(min_length=1, max_length=255)
    customer_id: UUID
    rental_start: datetime
    rental_end: datetime
    amount_minor: int = Field(gt=0, le=99_999_999)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    vehicle_make: str = Field(min_length=1, max_length=100)
    vehicle_model: str = Field(min_length=1, max_length=100)
    vehicle_color: str = Field(min_length=1, max_length=60)
    vehicle_license_plate: str = Field(min_length=1, max_length=32)

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_receipt(self):
        if self.currency != "USD":
            raise ValueError("Only USD receipts are supported")
        if self.rental_start.tzinfo is None or self.rental_end.tzinfo is None:
            raise ValueError("Rental timestamps must include a timezone")
        if self.rental_end <= self.rental_start:
            raise ValueError("rental_end must be later than rental_start")
        return self


class ReceiptRead(BaseModel):
    id: UUID
    receipt_number: str
    booking_id: UUID
    payment_id: UUID
    stripe_payment_intent_id: str
    customer_id: UUID
    rental_start: datetime
    rental_end: datetime
    amount_minor: int
    currency: str
    vehicle_make: str
    vehicle_model: str
    vehicle_color: str
    vehicle_license_plate: str
    created_at: datetime

    @field_validator("rental_start", "rental_end", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    model_config = ConfigDict(from_attributes=True)
