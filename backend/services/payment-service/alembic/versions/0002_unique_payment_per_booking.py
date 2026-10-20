"""Allow one payment intent per booking."""

from alembic import op


revision = "0002_payment_per_booking"
down_revision = "0001_create_payments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_payments_booking_id", table_name="payments")
    op.create_unique_constraint("uq_payments_booking_id", "payments", ["booking_id"])


def downgrade() -> None:
    op.drop_constraint("uq_payments_booking_id", "payments", type_="unique")
    op.create_index("ix_payments_booking_id", "payments", ["booking_id"])
