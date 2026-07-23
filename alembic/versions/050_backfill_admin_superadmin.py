"""backfill is_superadmin for owner accounts

Some installs carry an owner admin row whose is_superadmin flag was never set
(created before the flag mattered, or restored from an older backup). The RBAC
router-gating added in 2.2.35 requires is_superadmin (or a granted permission)
on every data endpoint, so such an owner gets 403'd off their entire panel after
updating. Backfill the owner (and legacy NULL-role rows, which on a single-admin
install ARE the owner) to is_superadmin=true so they keep full access. Delegated
admin/manager rows are left untouched — their scoping is intentional.

Belt to the code-side owner-safety in middleware/auth.py (owner role bypasses the
permission gate regardless of this flag).

Revision ID: 050_admin_superadmin_backfill
Revises: 049_cuc_slot_idx
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa

revision = '050_admin_superadmin_backfill'
down_revision = '049_cuc_slot_idx'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    try:
        conn.execute(sa.text(
            "UPDATE admin_users SET is_superadmin = true "
            "WHERE role = 'owner' OR role IS NULL"
        ))
    except Exception:
        # Legacy installs whose admin_users shape differs (e.g. no is_superadmin
        # column yet) are covered by the code-side owner fail-safe; never fail the
        # whole migration chain over this hygiene backfill.
        pass


def downgrade():
    # One-way data backfill — prior per-row values are not recoverable. No-op.
    pass
