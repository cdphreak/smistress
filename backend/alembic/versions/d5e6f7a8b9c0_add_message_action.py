"""add message.action

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'message', sa.Column('action', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('message', 'action')
