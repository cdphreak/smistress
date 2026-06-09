"""add batch artifacts (task pool + drone line bank)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Reference the existing proof_requirement enum (labels are the Python enum
    # *names*, per the initial schema); create_type=False so we don't recreate it.
    proof = postgresql.ENUM(
        'PHOTO', 'VIDEO', 'TIMER', 'HONOR', 'NONE',
        name='proof_requirement', create_type=False,
    )
    op.create_table(
        'task_pool_item',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('description', sa.String(), nullable=False),
        sa.Column('proof_requirement', proof, nullable=False),
        sa.Column('difficulty', sa.String(), server_default='standard', nullable=False),
        sa.Column('merit_reward', sa.Integer(), server_default='0', nullable=False),
        sa.Column('merit_fail_penalty', sa.Integer(), server_default='0', nullable=False),
        sa.Column('merit_miss_penalty', sa.Integer(), server_default='0', nullable=False),
        sa.Column('consumed', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'drone_line',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('unit', sa.String(), nullable=False),
        sa.Column('event', sa.String(), nullable=False),
        sa.Column('merit_band', sa.String(), server_default='any', nullable=False),
        sa.Column('time_of_day', sa.String(), server_default='any', nullable=False),
        sa.Column('text', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('drone_line')
    op.drop_table('task_pool_item')
