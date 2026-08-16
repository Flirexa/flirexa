"""add per-device DNS protection profiles and policies

Revision ID: 055_dns_protection
Revises: 054_client_account_balance
"""

from alembic import op
import sqlalchemy as sa


revision = "055_dns_protection"
down_revision = "054_client_account_balance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dns_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=48), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("resolver_addresses", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("customer_selectable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(name) > 0", name="ck_dns_profiles_name_nonempty"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mode", name="uq_dns_profiles_mode"),
    )
    op.create_table(
        "dns_policy_assignments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=24), nullable=False),
        sa.Column("scope_value", sa.String(length=100), nullable=False),
        sa.Column("enforced", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scope_type IN ('plan','segment','client','device')",
            name="ck_dns_policy_scope_type",
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["dns_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scope_type", "scope_value", name="uq_dns_policy_scope"),
    )
    op.create_index("ix_dns_policy_assignments_profile_id", "dns_policy_assignments", ["profile_id"])
    op.create_index("ix_dns_policy_assignments_scope_type", "dns_policy_assignments", ["scope_type"])
    op.create_index("ix_dns_policy_assignments_scope_value", "dns_policy_assignments", ["scope_value"])
    op.add_column("device_slots", sa.Column("dns_profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_device_slots_dns_profile", "device_slots", "dns_profiles",
        ["dns_profile_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_device_slots_dns_profile_id", "device_slots", ["dns_profile_id"])
    op.add_column("clients", sa.Column("dns_profile_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_clients_dns_profile", "clients", "dns_profiles",
        ["dns_profile_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_clients_dns_profile_id", "clients", ["dns_profile_id"])


def downgrade():
    op.drop_index("ix_clients_dns_profile_id", table_name="clients")
    op.drop_constraint("fk_clients_dns_profile", "clients", type_="foreignkey")
    op.drop_column("clients", "dns_profile_id")
    op.drop_index("ix_device_slots_dns_profile_id", table_name="device_slots")
    op.drop_constraint("fk_device_slots_dns_profile", "device_slots", type_="foreignkey")
    op.drop_column("device_slots", "dns_profile_id")
    op.drop_index("ix_dns_policy_assignments_scope_value", table_name="dns_policy_assignments")
    op.drop_index("ix_dns_policy_assignments_scope_type", table_name="dns_policy_assignments")
    op.drop_index("ix_dns_policy_assignments_profile_id", table_name="dns_policy_assignments")
    op.drop_table("dns_policy_assignments")
    op.drop_table("dns_profiles")
