"""add queued proof memory columns

Revision ID: g7b8c9d0e1f2
Revises: b8c9d0e1f2a3
Create Date: 2026-10-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'g7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('proof', sa.Column('media_uri', sa.String(), nullable=True))
    op.add_column('task', sa.Column('punitive', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.execute(
        "UPDATE task SET punitive = true WHERE id IN "
        "(SELECT penance_task_id FROM punishment WHERE penance_task_id IS NOT NULL)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('task', 'punitive')
    op.drop_column('proof', 'media_uri')
