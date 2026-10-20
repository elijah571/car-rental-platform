from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        Index("ix_bookings_status_return_at", "status", "return_at"),
        CheckConstraint("return_at > pickup_at", name="ck_bookings_positive_window"),
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'active', 'awaiting_inspection', "
            "'inspection_failed', 'completed', 'cancelled', 'expired')",
            name="ck_bookings_status",
        ),
        CheckConstraint("amount_minor IS NULL OR amount_minor > 0", name="ck_bookings_positive_amount"),
        CheckConstraint("currency = 'USD'", name="ck_bookings_usd_only"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    vehicle_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    pickup_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    return_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD", nullable=False)
    vehicle_make: Mapped[str | None] = mapped_column(String(80), nullable=True)
    vehicle_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    vehicle_color: Mapped[str | None] = mapped_column(String(60), nullable=True)
    vehicle_license_plate: Mapped[str | None] = mapped_column(String(32), nullable=True)
    agreement_version: Mapped[str] = mapped_column(String(40), nullable=False, default="draft-1", server_default="draft-1")
    agreement_accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=True)
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
