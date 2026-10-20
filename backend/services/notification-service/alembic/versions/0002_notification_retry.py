"""Add notification retry leases and exponential backoff state."""

from alembic import op
import sqlalchemy as sa


revision = "0002_notification_retry"
down_revision = "0001_create_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_notifications_status", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_status",
        "notifications",
        "status IN ('pending', 'sending', 'sent', 'failed')",
    )
    op.add_column(
        "notifications",
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("notifications", sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("notifications", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.execute("UPDATE notifications SET status='failed' WHERE status='sending'")
    op.drop_column("notifications", "locked_until")
    op.drop_column("notifications", "next_attempt_at")
    op.drop_column("notifications", "attempt_count")
    op.drop_constraint("ck_notifications_status", "notifications", type_="check")
    op.create_check_constraint(
        "ck_notifications_status", "notifications", "status IN ('pending', 'sent', 'failed')"
    )
