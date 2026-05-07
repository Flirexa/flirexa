"""client_share_tokens — time-limited public download links

Revision ID: 030_share_tokens
Revises: 029_subs_traffic_zero
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa

revision = "030_share_tokens"
down_revision = "029_subs_traffic_zero"
branch_labels = None
depends_on = None


def upgrade():
    # Idempotent — skip create if the table already exists. Defends against
    # the case where a previous attempt of this same migration partially
    # ran but didn't update alembic_version (e.g. crash between
    # CREATE TABLE and the alembic_version UPDATE). Without this, the
    # second run blasts straight into a "relation already exists" error
    # and the whole migration aborts inside the lifespan handler — the
    # smoke check then sees current=029 head=030 and triggers a rollback.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "client_share_tokens" not in existing_tables:
        op.create_table(
            "client_share_tokens",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("token", sa.String(64), nullable=False, unique=True),
            sa.Column("client_id", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("download_ip", sa.String(64), nullable=True),
        )

    existing_indexes = {
        ix["name"] for ix in inspector.get_indexes("client_share_tokens")
    } if "client_share_tokens" in inspector.get_table_names() else set()

    if "ix_client_share_tokens_token" not in existing_indexes:
        op.create_index(
            "ix_client_share_tokens_token",
            "client_share_tokens",
            ["token"],
            unique=True,
        )
    if "ix_client_share_tokens_client_id" not in existing_indexes:
        op.create_index(
            "ix_client_share_tokens_client_id",
            "client_share_tokens",
            ["client_id"],
        )


def downgrade():
    op.drop_index("ix_client_share_tokens_client_id", table_name="client_share_tokens")
    op.drop_index("ix_client_share_tokens_token", table_name="client_share_tokens")
    op.drop_table("client_share_tokens")
