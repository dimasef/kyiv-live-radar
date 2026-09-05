"""A channel's sector notation: sources.sector_notation

Місто Кия writes «Обухів/Вишеньки/Бориспіль» for ONE target's sector; the
ballistic enumeration split cut such a message into three tracks (11 of 22
ballistic tracks in the live DB). With 'slash' the slash-joined run is one
target. Backfilled for that channel; every other channel keeps 'none'.

Revision ID: 0045
Revises: 0044
Create Date: 2026-09-05T22:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0045'
down_revision: Union[str, Sequence[str], None] = '0044'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

sources = sa.table(
    'sources',
    sa.column('channel_key', sa.String),
    sa.column('sector_notation', sa.String),
)


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'sources',
        sa.Column('sector_notation', sa.String(length=10), nullable=False,
                  server_default='none'),
    )
    op.execute(
        sources.update()
        .where(sources.c.channel_key == 'Kyiaradar')
        .values(sector_notation='slash')
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.drop_column('sector_notation')
