from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("year >= 1900", name="ck_vehicles_year"),
        CheckConstraint("seats BETWEEN 1 AND 20", name="ck_vehicles_seats"),
        CheckConstraint("hourly_rate > 0", name="ck_vehicles_hourly_rate"),
        CheckConstraint(
            "status IN ('active', 'maintenance', 'retired')",
            name="ck_vehicles_status",
        ),
        Index("ix_vehicles_status_category", "status", "category"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    make: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    color: Mapped[str] = mapped_column(String(60), nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    seats: Mapped[int] = mapped_column(nullable=False)
    transmission: Mapped[str] = mapped_column(String(20), nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    registration_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active", nullable=False
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
