"""awg_h1-h4 columns: Integer → BigInteger (uint32 can exceed int32 range)

Revision ID: 005
Revises: 004
Create Date: 2026-03-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005'
down_revision: Union[str, Sequence[str], None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for col in ('awg_h1', 'awg_h2', 'awg_h3', 'awg_h4'):
        op.alter_column(
            'servers', col,
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=True,
        )


def downgrade() -> None:
    for col in ('awg_h1', 'awg_h2', 'awg_h3', 'awg_h4'):
        op.alter_column(
            'servers', col,
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=True,
        )
