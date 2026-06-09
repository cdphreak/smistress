"""chastity timer + economy debt + punishment ledger

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-09 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. denial_timer (plural, per-event) -> chastity_timer (single per profile).
    op.drop_table('denial_timer')
    op.create_table(
        'chastity_timer',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('note', sa.String(), server_default='', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('profile_id', name='uq_chastity_profile'),
    )

    # 2. economy debt balance.
    op.add_column(
        'economy_state',
        sa.Column('debt', sa.Integer(), server_default='0', nullable=False),
    )

    # 3. punishment ledger (+ its enums, created here).
    pun_type = postgresql.ENUM(
        'PENANCE_TASK', 'CHASTITY_EXTENSION', 'TOKEN_CONFISCATION', name='punishment_type'
    )
    pun_status = postgresql.ENUM(
        'ISSUED', 'SERVED', 'BOUGHT_DOWN', 'EXPIRED', name='punishment_status'
    )
    op.create_table(
        'punishment',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('type', pun_type, nullable=False),
        sa.Column('severity', sa.Integer(), server_default='1', nullable=False),
        sa.Column('reason', sa.String(), server_default='', nullable=False),
        sa.Column('debt_amount', sa.Integer(), server_default='0', nullable=False),
        sa.Column('status', pun_status, server_default='ISSUED', nullable=False),
        sa.Column('penance_task_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('punishment')
    op.execute('DROP TYPE punishment_status')
    op.execute('DROP TYPE punishment_type')
    op.drop_column('economy_state', 'debt')
    op.drop_table('chastity_timer')
    op.create_table(
        'denial_timer',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('reason', sa.String(), server_default='', nullable=False),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['profile_id'], ['sub_profile.id']),
        sa.PrimaryKeyConstraint('id'),
    )
