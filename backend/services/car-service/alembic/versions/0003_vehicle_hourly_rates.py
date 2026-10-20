"""Store vehicle rental prices as per-hour rates."""

from alembic import op
import sqlalchemy as sa


revision = "0003_vehicle_hourly_rates"
down_revision = "0002_add_vehicle_color"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_vehicles_daily_rate", "vehicles", type_="check")
    op.alter_column(
        "vehicles",
        "daily_rate",
        new_column_name="hourly_rate",
        existing_type=sa.Numeric(10, 2),
        existing_nullable=False,
    )
    # Preserve the existing daily price when switching its unit to hourly.
    op.execute("UPDATE vehicles SET hourly_rate = GREATEST(ROUND(hourly_rate / 24, 2), 0.01)")
    op.create_check_constraint(
        "ck_vehicles_hourly_rate", "vehicles", "hourly_rate > 0"
    )


def downgrade() -> None:
    op.drop_constraint("ck_vehicles_hourly_rate", "vehicles", type_="check")
    op.execute("UPDATE vehicles SET hourly_rate = ROUND(hourly_rate * 24, 2)")
    op.alter_column(
        "vehicles",
        "hourly_rate",
        new_column_name="daily_rate",
        existing_type=sa.Numeric(10, 2),
        existing_nullable=False,
    )
    op.create_check_constraint(
        "ck_vehicles_daily_rate", "vehicles", "daily_rate > 0"
    )
