"""Add the vehicle color required for rental ticket snapshots."""

from alembic import op
import sqlalchemy as sa


revision = "0002_add_vehicle_color"
down_revision = "0001_create_vehicles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vehicles",
        sa.Column("color", sa.String(length=60), server_default="unspecified", nullable=False),
    )
    op.alter_column("vehicles", "color", server_default=None)


def downgrade() -> None:
    op.drop_column("vehicles", "color")
