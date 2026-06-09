"""add punishment pool

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-09 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pun_type = postgresql.ENUM(
        'PENANCE_TASK', 'CHASTITY_EXTENSION', 'TOKEN_CONFISCATION',
        name='punishment_type', create_type=False,
    )
    op.create_table(
        'punishment_pool_item',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('type', pun_type, nullable=False),
        sa.Column('severity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('consumed', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('punishment_pool_item')
