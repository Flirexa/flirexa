"""client segments — operator grouping with a shared rule template

Revision ID: 048_client_segments
Revises: 047_promo_redempt
Create Date: 2026-06-25

Additive: new client_segments table + nullable clients.segment_id (ON DELETE SET NULL).
Existing rows unaffected (segment_id defaults NULL = ungrouped).
"""
from alembic import op
import sqlalchemy as sa


revision = "048_client_segments"
down_revision = "047_promo_redempt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_segments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("color", sa.String(length=16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("bandwidth_limit", sa.Integer(), nullable=True),
        sa.Column("traffic_limit_mb", sa.Integer(), nullable=True),
        sa.Column("expiry_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auto_bandwidth_rule_id", sa.Integer(),
                  sa.ForeignKey("traffic_rules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("name", name="uq_client_segments_name"),
    )
    op.add_column("clients", sa.Column("segment_id", sa.Integer(),
                  sa.ForeignKey("client_segments.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_clients_segment_id", "clients", ["segment_id"])


def downgrade() -> None:
    op.drop_index("ix_clients_segment_id", table_name="clients")
    op.drop_column("clients", "segment_id")
    op.drop_table("client_segments")
