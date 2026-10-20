"""Add booking price/vehicle snapshots, 15-minute holds, and overlap exclusion."""

from alembic import op
import sqlalchemy as sa


revision = "0002_booking_price_hold_snapshot"
down_revision = "0001_create_bookings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.drop_constraint("ck_bookings_status", "bookings", type_="check")
    op.create_check_constraint(
        "ck_bookings_status",
        "bookings",
        "status IN ('pending', 'confirmed', 'active', 'awaiting_inspection', "
        "'inspection_failed', 'completed', 'cancelled', 'expired')",
    )
    op.add_column("bookings", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("bookings", sa.Column("amount_minor", sa.Integer(), nullable=True))
    op.add_column(
        "bookings",
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
    )
    op.add_column("bookings", sa.Column("vehicle_make", sa.String(length=80), nullable=True))
    op.add_column("bookings", sa.Column("vehicle_model", sa.String(length=80), nullable=True))
    op.add_column("bookings", sa.Column("vehicle_color", sa.String(length=60), nullable=True))
    op.add_column("bookings", sa.Column("vehicle_license_plate", sa.String(length=32), nullable=True))
    op.execute(
        "UPDATE bookings SET expires_at = created_at + INTERVAL '15 minutes' "
        "WHERE status = 'pending' AND expires_at IS NULL"
    )
    op.create_check_constraint(
        "ck_bookings_positive_amount",
        "bookings",
        "amount_minor IS NULL OR amount_minor > 0",
    )
    op.create_check_constraint("ck_bookings_usd_only", "bookings", "currency = 'USD'")
    op.create_index("ix_bookings_expires_at", "bookings", ["expires_at"])
    op.execute(
        "ALTER TABLE bookings ADD CONSTRAINT ex_bookings_vehicle_time_overlap "
        "EXCLUDE USING gist (vehicle_id WITH =, "
        "tstzrange(pickup_at, return_at, '[)') WITH &&) "
        "WHERE (status IN ('pending', 'confirmed', 'active', 'awaiting_inspection', 'inspection_failed'))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE bookings DROP CONSTRAINT ex_bookings_vehicle_time_overlap")
    op.drop_index("ix_bookings_expires_at", table_name="bookings")
    op.drop_constraint("ck_bookings_usd_only", "bookings", type_="check")
    op.drop_constraint("ck_bookings_positive_amount", "bookings", type_="check")
    op.drop_column("bookings", "vehicle_license_plate")
    op.drop_column("bookings", "vehicle_color")
    op.drop_column("bookings", "vehicle_model")
    op.drop_column("bookings", "vehicle_make")
    op.drop_column("bookings", "currency")
    op.drop_column("bookings", "amount_minor")
    op.drop_column("bookings", "expires_at")
    op.drop_constraint("ck_bookings_status", "bookings", type_="check")
    op.create_check_constraint(
        "ck_bookings_status", "bookings", "status IN ('pending', 'cancelled')"
    )
