from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PaymentCreate(BaseModel):
    booking_id: UUID

    model_config = ConfigDict(extra="forbid")


class PaymentIntentRead(BaseModel):
    id: UUID
    booking_id: UUID
    amount_minor: int
    currency: str
    status: str
    client_secret: str


class PaymentRead(BaseModel):
    id: UUID
    booking_id: UUID
    amount_minor: int
    currency: str
    status: str
    stripe_payment_intent_id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
