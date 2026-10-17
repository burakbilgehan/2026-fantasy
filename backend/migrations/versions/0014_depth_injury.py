"""depth chart injury status (ESPN depth source)

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('depth_charts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('injury', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('depth_charts', schema=None) as batch_op:
        batch_op.drop_column('injury')
