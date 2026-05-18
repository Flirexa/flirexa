"""paymentmethod ENUM: add card-provider values

Revision ID: 034_pm_card
Revises: 033_customer_email
Create Date: 2026-05-18

`client_portal_payments.payment_method` is a Postgres ENUM that was created
with only crypto + paypal + usd + eur values. The create-invoice handler
writes the raw `provider` string for hosted-checkout providers (stripe,
mollie, razorpay, payme), which Postgres rejects at commit time with
`invalid input value for enum paymentmethod: "stripe"` — every Stripe
checkout 500s the portal. Add the missing enum values so the existing
write path succeeds.

`ALTER TYPE ... ADD VALUE` cannot run inside a transaction in older Postgres
versions, so we autocommit each statement. Newer (12+) Postgres supports it
in transactions, but the `IF NOT EXISTS` guard makes the migration safe to
re-run regardless.
"""

from alembic import op


revision = "034_pm_card"
down_revision = "033_customer_email"
branch_labels = None
depends_on = None


NEW_VALUES = [
    "stripe",
    "mollie",
    "razorpay",
    "payme",
    "cryptopay",
    "nowpayments",
]


def upgrade():
    bind = op.get_bind()
    # Skip silently on non-postgres backends (SQLite has no enum types — it
    # stores the string directly, so nothing to migrate).
    if bind.dialect.name != "postgresql":
        return
    # Each ADD VALUE runs as its own statement; AUTOCOMMIT escapes the
    # surrounding alembic transaction on Postgres < 12 where ALTER TYPE
    # is non-transactional.
    conn = bind.execution_options(isolation_level="AUTOCOMMIT")
    for v in NEW_VALUES:
        conn.exec_driver_sql(
            f"ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS '{v}'"
        )


def downgrade():
    # Postgres has no `ALTER TYPE ... DROP VALUE`. Recreating the type
    # requires copying every row, which is unsafe on a live install for
    # what is effectively a metadata addition. Downgrade is a no-op.
    pass
