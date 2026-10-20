"""Index active rentals for scheduled return alerts."""

from alembic import op


revision = "0005_return_alert_index"
down_revision = "0004_booking_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_bookings_status_return_at", "bookings", ["status", "return_at"])


def downgrade() -> None:
    op.drop_index("ix_bookings_status_return_at", table_name="bookings")
