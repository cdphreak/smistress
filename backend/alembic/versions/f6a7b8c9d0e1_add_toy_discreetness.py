"""add toy discreetness flags

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-11 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('toy', sa.Column('noise', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('toy', sa.Column('visibility', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('toy', sa.Column('discreet_capable', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    for col in ('discreet_capable', 'visibility', 'noise'):
        op.drop_column('toy', col)
