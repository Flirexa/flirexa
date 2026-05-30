"""client_users.email: make optional

Revision ID: 039_email_optional
Revises: 038_slot_tokens
Create Date: 2026-05-26

Operators on markets where customers expect total anonymity (WeChat /
crypto buyers in Asia) reported that requiring an email at signup
costs them conversions — many users will close the form rather than
hand over a real address, and a throwaway one bounces every receipt
and verification mail we send. Making the column nullable lets the
registration form turn the field into "optional" without breaking
existing rows, and lets login take either email or username (route
layer handles the disambiguation).

Existing rows keep their values — this is just a constraint relax.
"""

from alembic import op
import sqlalchemy as sa


revision = "039_email_optional"
down_revision = "038_slot_tokens"
branch_labels = None
depends_on = None


def upgrade():
    # Postgres + SQLite both support drop-not-null via alter_column.
    # The unique index stays — NULL values are allowed in unique
    # indexes (each NULL is treated as distinct), so empty-email rows
    # don't collide.
    op.alter_column(
        "client_users",
        "email",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade():
    op.alter_column(
        "client_users",
        "email",
        existing_type=sa.String(length=255),
        nullable=False,
    )
