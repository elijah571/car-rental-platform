"""Persist Stripe success delivery work for retry independent of Stripe."""

from alembic import op
import sqlalchemy as sa


revision = "0003_payment_delivery_outbox"
down_revision = "0002_payment_per_booking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_delivery_outbox",
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'reconciliation_required', 'failed')",
            name="ck_payment_delivery_outbox_status",
        ),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_payment_delivery_outbox_payment_id", "payment_delivery_outbox", ["payment_id"])
    op.create_index("ix_payment_delivery_outbox_next_attempt_at", "payment_delivery_outbox", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_payment_delivery_outbox_next_attempt_at", table_name="payment_delivery_outbox")
    op.drop_index("ix_payment_delivery_outbox_payment_id", table_name="payment_delivery_outbox")
    op.drop_table("payment_delivery_outbox")
