"""paymentmethod ENUM: add UPPERCASE values (SQLAlchemy serializes member NAME)

Revision ID: 035_pm_upper
Revises: 034_pm_card
Create Date: 2026-05-18

SQLAlchemy's `Enum(PaymentMethod)` column writes the enum MEMBER NAME
(`'STRIPE'`), not the value (`'stripe'`), unless you pass a custom
`values_callable`. The Postgres `paymentmethod` ENUM was created with
UPPERCASE member names for every original crypto value (BTC, USDT_TRC20…)
so writes lined up. Migration `034_pm_card` mistakenly added LOWERCASE
values (`'stripe'`, `'mollie'`, …) which SQLAlchemy never writes — every
Stripe create-invoice still fails with
`invalid input value for enum paymentmethod: "STRIPE"`.

This migration adds the matching UPPERCASE values so card-provider
inserts succeed. The lowercase ones from 034 stay (Postgres has no
`DROP VALUE`) but they're harmless — nothing writes them.
"""

from alembic import op


revision = "035_pm_upper"
down_revision = "034_pm_card"
branch_labels = None
depends_on = None


NEW_VALUES = [
    "STRIPE",
    "MOLLIE",
    "RAZORPAY",
    "PAYME",
    "CRYPTOPAY",
    "NOWPAYMENTS",
]


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for v in NEW_VALUES:
        op.execute(f"ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS '{v}'")


def downgrade():
    # Postgres has no `DROP VALUE`. Downgrade is a no-op — see 034.
    pass
