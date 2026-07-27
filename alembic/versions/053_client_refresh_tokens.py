"""add rotating client-portal refresh tokens

Revision ID: 053_client_refresh_tokens
Revises: 052_portal_rate_limits
"""
from alembic import op
import sqlalchemy as sa


revision = "053_client_refresh_tokens"
down_revision = "052_portal_rate_limits"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_refresh_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_hash", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["client_users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_client_refresh_tokens_user_id",
        "client_refresh_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_client_refresh_tokens_token_hash",
        "client_refresh_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_client_refresh_tokens_family_id",
        "client_refresh_tokens",
        ["family_id"],
        unique=False,
    )
    op.create_index(
        "ix_client_refresh_tokens_expires_at",
        "client_refresh_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_client_refresh_tokens_user_family",
        "client_refresh_tokens",
        ["user_id", "family_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_client_refresh_tokens_user_family",
        table_name="client_refresh_tokens",
    )
    op.drop_index(
        "ix_client_refresh_tokens_expires_at",
        table_name="client_refresh_tokens",
    )
    op.drop_index(
        "ix_client_refresh_tokens_family_id",
        table_name="client_refresh_tokens",
    )
    op.drop_index(
        "ix_client_refresh_tokens_token_hash",
        table_name="client_refresh_tokens",
    )
    op.drop_index(
        "ix_client_refresh_tokens_user_id",
        table_name="client_refresh_tokens",
    )
    op.drop_table("client_refresh_tokens")
