"""paymentmethod ENUM: add 'paylio'

Revision ID: 044_pm_paylio
Revises: 043_device_slot_bind_timestamps
Create Date: 2026-06-01

`client_portal_payments.payment_method` is a Postgres ENUM. Adding the
PayLio provider without ALTER TYPE makes every paylio checkout 500 the
portal with `invalid input value for enum paymentmethod: "paylio"`.

Mirrors 034_pm_card. `IF NOT EXISTS` keeps re-runs safe.
"""

from alembic import op


revision = "044_pm_paylio"
down_revision = "043_device_slot_bind_timestamps"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # SQLAlchemy's SQLEnum serialises by member NAME, so the enum value
    # in Postgres must be the uppercase Python name ('PAYLIO'), not the
    # lowercase ``str`` value ('paylio'). Matches the pattern set by
    # 035_paymentmethod_uppercase. The lowercase variant is added too
    # for backward compatibility with any code path that writes the
    # raw `provider` string verbatim.
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'PAYLIO'")
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'paylio'")


def downgrade():
    pass
