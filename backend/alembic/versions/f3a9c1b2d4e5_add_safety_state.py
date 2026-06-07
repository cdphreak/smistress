"""add safety_state

Revision ID: f3a9c1b2d4e5
Revises: 2c12f7878811
Create Date: 2026-06-07 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f3a9c1b2d4e5'
down_revision: Union[str, Sequence[str], None] = '2c12f7878811'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'safety_state',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('is_halted', sa.Boolean(), nullable=False),
        sa.Column('on_hiatus', sa.Boolean(), nullable=False),
        sa.Column('last_safeword_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_consent_check_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('safety_state')
