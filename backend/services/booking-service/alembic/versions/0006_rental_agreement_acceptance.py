"""Record agreement version and acceptance on each rental."""
from alembic import op
import sqlalchemy as sa

revision = "0006_rental_agreement_acceptance"
down_revision = "0005_return_alert_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("agreement_version", sa.String(40), server_default="legacy-unrecorded", nullable=False))
    op.add_column("bookings", sa.Column("agreement_accepted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_column("bookings", "agreement_accepted_at")
    op.drop_column("bookings", "agreement_version")
