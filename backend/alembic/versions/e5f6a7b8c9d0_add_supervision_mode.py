"""add supervision mode + notes

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-10 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    mode = postgresql.ENUM(
        'FULL', 'DISCREET', 'TASK', 'HOMEOFFICE', 'VACATION', name='supervision_mode'
    )
    mode.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'sub_profile',
        sa.Column('supervision_mode', mode, server_default='FULL', nullable=False),
    )
    op.add_column(
        'sub_profile',
        sa.Column(
            'supervision_notes', postgresql.JSONB(astext_type=sa.Text()),
            server_default='{}', nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('sub_profile', 'supervision_notes')
    op.drop_column('sub_profile', 'supervision_mode')
    op.execute('DROP TYPE supervision_mode')
