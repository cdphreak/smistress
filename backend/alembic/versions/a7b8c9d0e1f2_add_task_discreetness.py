"""add task + pool discreetness profile

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-11 10:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DISCREETNESS = postgresql.ENUM('OVERT', 'DISCREET', 'SILENT', name='discreetness')


def upgrade() -> None:
    """Upgrade schema."""
    _DISCREETNESS.create(op.get_bind(), checkfirst=True)
    for table in ('task', 'task_pool_item'):
        op.add_column(
            table, sa.Column('intensity', sa.Integer(), server_default='0', nullable=False)
        )
        op.add_column(
            table,
            sa.Column(
                'discreetness',
                postgresql.ENUM('OVERT', 'DISCREET', 'SILENT', name='discreetness',
                                create_type=False),
                server_default='OVERT', nullable=False,
            ),
        )
        op.add_column(
            table,
            sa.Column('required_toy_ids', postgresql.JSONB(astext_type=sa.Text()),
                      server_default='[]', nullable=False),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('task_pool_item', 'task'):
        op.drop_column(table, 'required_toy_ids')
        op.drop_column(table, 'discreetness')
        op.drop_column(table, 'intensity')
    op.execute('DROP TYPE IF EXISTS discreetness')
