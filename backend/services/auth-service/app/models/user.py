from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, LargeBinary, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    """Local account, password credentials, and authorization role."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    auth_subject: Mapped[str] = mapped_column(String(128), unique=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    full_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str | None] = mapped_column(String(256), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="customer", server_default="customer")
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class KycDocument(Base):
    """Privately stored, encrypted customer identity evidence."""

    __tablename__ = "kyc_documents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    encrypted_content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)
    review_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
