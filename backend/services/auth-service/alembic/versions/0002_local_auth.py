"""Move local profiles to password and role based authentication.

Revision ID: 0002_local_auth
Revises: 0001_create_users
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_local_auth"
down_revision = "0001_create_users"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "cognito_sub", new_column_name="auth_subject")
    op.add_column("users", sa.Column("password_hash", sa.String(length=256), nullable=True))
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=32), server_default="customer", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("users", "role")
    op.drop_column("users", "password_hash")
    op.alter_column("users", "auth_subject", new_column_name="cognito_sub")
