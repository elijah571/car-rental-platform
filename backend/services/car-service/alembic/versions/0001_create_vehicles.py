"""Create the vehicle inventory table."""

from alembic import op
import sqlalchemy as sa


revision = "0001_create_vehicles"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vehicles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("make", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=80), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False),
        sa.Column("transmission", sa.String(length=20), nullable=False),
        sa.Column("fuel_type", sa.String(length=20), nullable=False),
        sa.Column("daily_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("registration_number", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("year >= 1900", name="ck_vehicles_year"),
        sa.CheckConstraint("seats BETWEEN 1 AND 20", name="ck_vehicles_seats"),
        sa.CheckConstraint("daily_rate > 0", name="ck_vehicles_daily_rate"),
        sa.CheckConstraint(
            "status IN ('active', 'maintenance', 'retired')",
            name="ck_vehicles_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("registration_number"),
    )
    op.create_index("ix_vehicles_make", "vehicles", ["make"])
    op.create_index("ix_vehicles_model", "vehicles", ["model"])
    op.create_index("ix_vehicles_category", "vehicles", ["category"])
    op.create_index("ix_vehicles_status_category", "vehicles", ["status", "category"])


def downgrade() -> None:
    op.drop_index("ix_vehicles_status_category", table_name="vehicles")
    op.drop_index("ix_vehicles_category", table_name="vehicles")
    op.drop_index("ix_vehicles_model", table_name="vehicles")
    op.drop_index("ix_vehicles_make", table_name="vehicles")
    op.drop_table("vehicles")
