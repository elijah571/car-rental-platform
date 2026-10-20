from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_RENTAL_DURATION = timedelta(days=7)


class BookingCreate(BaseModel):
    vehicle_id: UUID
    pickup_at: datetime
    return_at: datetime
    agreement_accepted: bool
    agreement_version: str = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def validate_booking_window(self):
        if self.pickup_at.tzinfo is None or self.pickup_at.utcoffset() is None:
            raise ValueError("pickup_at must include a timezone")
        if self.return_at.tzinfo is None or self.return_at.utcoffset() is None:
            raise ValueError("return_at must include a timezone")
        if self.return_at <= self.pickup_at:
            raise ValueError("return_at must be later than pickup_at")
        if self.return_at - self.pickup_at > MAX_RENTAL_DURATION:
            raise ValueError("Rental duration cannot exceed 7 days")
        if self.pickup_at <= datetime.now(timezone.utc):
            raise ValueError("pickup_at must be in the future")
        return self


class BookingRead(BaseModel):
    id: UUID
    customer_id: UUID
    vehicle_id: UUID
    pickup_at: datetime
    return_at: datetime
    expires_at: datetime | None
    amount_minor: int | None
    currency: str
    vehicle_make: str | None
    vehicle_model: str | None
    vehicle_color: str | None
    vehicle_license_plate: str | None
    agreement_version: str
    agreement_accepted_at: datetime
    payment_id: UUID | None
    stripe_payment_intent_id: str | None
    status: Literal[
        "pending", "confirmed", "active", "awaiting_inspection",
        "inspection_failed", "completed", "cancelled", "expired",
    ]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaymentConfirmation(BaseModel):
    booking_id: UUID
    payment_id: UUID
    stripe_payment_intent_id: str = Field(min_length=1, max_length=255)
    amount_minor: int = Field(gt=0, le=99_999_999)
    currency: str = Field(pattern=r"^[Uu][Ss][Dd]$")
    stripe_event_id: str = Field(min_length=1, max_length=255)


class BookingPaymentDetails(BaseModel):
    id: UUID
    amount_minor: int
    currency: str
    status: Literal["pending", "confirmed", "active", "awaiting_inspection", "inspection_failed", "completed", "cancelled", "expired"]
    expires_at: datetime | None


class PaymentIntentResult(BaseModel):
    id: UUID
    booking_id: UUID
    amount_minor: int
    currency: str
    status: str
    client_secret: str


class InspectionDecision(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=500)


class BookingAvailabilityQuery(BaseModel):
    pickup_at: datetime
    return_at: datetime

    @model_validator(mode="after")
    def validate_window(self):
        if self.pickup_at.tzinfo is None or self.pickup_at.utcoffset() is None:
            raise ValueError("pickup_at must include a timezone")
        if self.return_at.tzinfo is None or self.return_at.utcoffset() is None:
            raise ValueError("return_at must include a timezone")
        if self.return_at <= self.pickup_at:
            raise ValueError("return_at must be later than pickup_at")
        if self.return_at - self.pickup_at > MAX_RENTAL_DURATION:
            raise ValueError("Rental duration cannot exceed 7 days")
        if self.pickup_at <= datetime.now(timezone.utc):
            raise ValueError("pickup_at must be in the future")
        return self


class AvailableVehicle(BaseModel):
    id: UUID
    make: str
    model: str
    color: str
    year: int
    category: str
    seats: int
    transmission: str
    fuel_type: str
    hourly_rate: Decimal
    currency: str
    registration_number: str
    rental_total_minor: int
    rental_currency: str = "USD"


class ReceiptSummary(BaseModel):
    id: UUID
    receipt_number: str
    booking_id: UUID
    payment_id: UUID
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
