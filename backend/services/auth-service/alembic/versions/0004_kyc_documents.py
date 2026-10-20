"""Add encrypted identity evidence storage for manual verification."""
from alembic import op
import sqlalchemy as sa

revision = "0004_kyc_documents"
down_revision = "0003_support_tickets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kyc_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("encrypted_content", sa.LargeBinary(), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("original_filename", sa.String(180), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("review_note", sa.String(500), nullable=True),
        sa.Column("reviewed_by", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("document_type IN ('driver_license', 'identity_document')", name="ck_kyc_document_type"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_kyc_document_status"),
    )
    op.create_index("ix_kyc_documents_user_id", "kyc_documents", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_kyc_documents_user_id", table_name="kyc_documents")
    op.drop_table("kyc_documents")
