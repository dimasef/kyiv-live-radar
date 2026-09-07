"""Differentiated alert levels: alerts.level / threat / level_changed_at

From 06:00 on 2026-09-06 Kyiv announces a yellow (drone) or red (missile /
massed-drone / missile-drone) level rather than one undifferentiated
«повітряна тривога». `alerts.in.ua` carries the same split per raion as
`alert_level`.

Every existing row keeps 'unknown'/'unspecified' — before this date no
announcement named a level, so backfilling one would be an invention.

Revision ID: 0046
Revises: 0045
Create Date: 2026-09-07T21:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0046'
down_revision: Union[str, Sequence[str], None] = '0045'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'alerts',
        sa.Column('level', sa.String(length=10), nullable=False, server_default='unknown'),
    )
    op.add_column(
        'alerts',
        sa.Column('threat', sa.String(length=20), nullable=False,
                  server_default='unspecified'),
    )
    op.add_column(
        'alerts',
        sa.Column('level_changed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_column('level_changed_at')
        batch_op.drop_column('threat')
        batch_op.drop_column('level')
