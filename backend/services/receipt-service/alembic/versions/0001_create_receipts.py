"""Create immutable rental receipt snapshots."""

from alembic import op
import sqlalchemy as sa


revision = "0001_create_receipts"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("receipt_number", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("rental_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rental_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("vehicle_make", sa.String(length=100), nullable=False),
        sa.Column("vehicle_model", sa.String(length=100), nullable=False),
        sa.Column("vehicle_color", sa.String(length=60), nullable=False),
        sa.Column("vehicle_license_plate", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount_minor > 0", name="ck_receipts_positive_amount"),
        sa.CheckConstraint("rental_end > rental_start", name="ck_receipts_positive_rental_window"),
        sa.CheckConstraint("currency = 'USD'", name="ck_receipts_usd_only"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("receipt_number"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("booking_id"),
        sa.UniqueConstraint("payment_id"),
        sa.UniqueConstraint("stripe_payment_intent_id"),
    )
    op.create_index("ix_receipts_customer_id", "receipts", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_receipts_customer_id", table_name="receipts")
    op.drop_table("receipts")
