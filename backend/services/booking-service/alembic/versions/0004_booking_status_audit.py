"""Record booking creation and lifecycle transitions."""

from alembic import op
import sqlalchemy as sa


revision = "0004_booking_audit"
down_revision = "0003_payment_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_status_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_booking_status_events_booking_id", "booking_status_events", ["booking_id"])


def downgrade() -> None:
    op.drop_index("ix_booking_status_events_booking_id", table_name="booking_status_events")
    op.drop_table("booking_status_events")
