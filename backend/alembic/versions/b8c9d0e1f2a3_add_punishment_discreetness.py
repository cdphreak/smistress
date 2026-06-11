"""add punishment + pool discreetness

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-06-11 10:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema. The `discreetness` enum already exists (a7b8c9d0e1f2)."""
    discreetness = postgresql.ENUM('OVERT', 'DISCREET', 'SILENT', name='discreetness',
                                   create_type=False)
    for table in ('punishment', 'punishment_pool_item'):
        op.add_column(
            table,
            sa.Column('discreetness', discreetness, server_default='OVERT', nullable=False),
        )
        op.add_column(
            table,
            sa.Column('required_toy_ids', postgresql.JSONB(astext_type=sa.Text()),
                      server_default='[]', nullable=False),
        )


def downgrade() -> None:
    """Downgrade schema. Leave the `discreetness` type — task/pool still use it."""
    for table in ('punishment_pool_item', 'punishment'):
        op.drop_column(table, 'required_toy_ids')
        op.drop_column(table, 'discreetness')
