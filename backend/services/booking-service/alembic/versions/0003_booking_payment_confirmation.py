"""Store payment linkage and idempotent Stripe confirmation events."""

from alembic import op
import sqlalchemy as sa


revision = "0003_payment_link"
down_revision = "0002_booking_price_hold_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("payment_id", sa.Uuid(), nullable=True))
    op.add_column("bookings", sa.Column("stripe_payment_intent_id", sa.String(255), nullable=True))
    op.create_unique_constraint("uq_bookings_payment_id", "bookings", ["payment_id"])
    op.create_unique_constraint(
        "uq_bookings_stripe_payment_intent_id", "bookings", ["stripe_payment_intent_id"]
    )
    op.create_table(
        "processed_payment_events",
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("booking_id", sa.Uuid(), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("processed_payment_events")
    op.drop_constraint("uq_bookings_stripe_payment_intent_id", "bookings", type_="unique")
    op.drop_constraint("uq_bookings_payment_id", "bookings", type_="unique")
    op.drop_column("bookings", "stripe_payment_intent_id")
    op.drop_column("bookings", "payment_id")
