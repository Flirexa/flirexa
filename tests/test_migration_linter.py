from pathlib import Path

import pytest

_lint_migrations = pytest.importorskip(
    "tools.lint_migrations",
    reason="internal release linters are not part of the public open-core tree",
)
check_autocommit_with_enum_use = _lint_migrations.check_autocommit_with_enum_use


def test_autocommit_lint_ignores_historical_comment():
    content = """
def upgrade():
    # An old AUTOCOMMIT attempt broke the alembic_version update.
    op.execute("ALTER TYPE paymentmethod ADD VALUE IF NOT EXISTS 'stripe'")
"""
    assert check_autocommit_with_enum_use(Path("034.py"), content) == []


def test_autocommit_lint_detects_real_execution_override():
    content = """
def upgrade():
    bind = op.get_bind().execution_options(isolation_level="AUTOCOMMIT")
    bind.execute(sa.text("ALTER TYPE paymentmethod ADD VALUE 'stripe'"))
"""
    findings = check_autocommit_with_enum_use(Path("bad.py"), content)
    assert len(findings) == 1
    assert findings[0][0] == "ERROR"
