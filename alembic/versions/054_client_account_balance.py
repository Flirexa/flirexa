"""add client account balances and immutable transaction ledger

Revision ID: 054_client_account_balance
Revises: 053_client_refresh_tokens
"""

from alembic import op
import sqlalchemy as sa


revision = "054_client_account_balance"
down_revision = "053_client_refresh_tokens"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "client_portal_payments",
        sa.Column("purpose", sa.String(length=32), nullable=False, server_default="subscription"),
    )
    op.add_column(
        "client_portal_payments",
        sa.Column("balance_credit_minor", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_client_portal_payments_purpose",
        "client_portal_payments",
        ["purpose"],
        unique=False,
    )

    op.create_table(
        "client_account_balances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("available_minor", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["client_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_client_account_balances_user_id"),
        sa.CheckConstraint("available_minor >= 0", name="ck_client_account_balance_nonnegative"),
    )
    op.create_table(
        "client_balance_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("balance_after_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
        sa.Column("transaction_type", sa.String(length=32), nullable=False),
        sa.Column("reference", sa.String(length=255), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=False, server_default="system"),
        sa.Column("actor_id", sa.String(length=100), nullable=True),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["client_users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="uq_client_balance_tx_idempotency_key"),
    )
    op.create_index(
        "ix_client_balance_transactions_user_id",
        "client_balance_transactions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_client_balance_transactions_transaction_type",
        "client_balance_transactions",
        ["transaction_type"],
        unique=False,
    )
    op.create_index(
        "ix_client_balance_transactions_reference",
        "client_balance_transactions",
        ["reference"],
        unique=False,
    )
    op.create_index(
        "ix_client_balance_transactions_created_at",
        "client_balance_transactions",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_client_balance_user_created",
        "client_balance_transactions",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_client_balance_user_created", table_name="client_balance_transactions")
    op.drop_index("ix_client_balance_transactions_created_at", table_name="client_balance_transactions")
    op.drop_index("ix_client_balance_transactions_reference", table_name="client_balance_transactions")
    op.drop_index("ix_client_balance_transactions_transaction_type", table_name="client_balance_transactions")
    op.drop_index("ix_client_balance_transactions_user_id", table_name="client_balance_transactions")
    op.drop_table("client_balance_transactions")
    op.drop_table("client_account_balances")
    op.drop_index("ix_client_portal_payments_purpose", table_name="client_portal_payments")
    op.drop_column("client_portal_payments", "balance_credit_minor")
    op.drop_column("client_portal_payments", "purpose")
