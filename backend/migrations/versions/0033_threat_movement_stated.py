"""Stated-path flag on a track

`threats.movement_stated` records that a contributing message named a path
between two places («Мамекине на Смяч»), rather than merely listing districts.

Why a stored flag and not a client-side guess: the map draws a vector only when
a track has 2+ distinct event timestamps (track.ts::hasMovement), because on the
Kyiv channels a single multi-district message («Троя, Оболонь») is one drone
meandering, not a trajectory — splitting those costs 16 points of session purity
on track-eval. The northern spotter channel writes the opposite dialect: 89 of
its 141 two-district messages state «A на B», one message per leg, all at one
timestamp, so 39 real drone tracks drew as dots. The distinction is in the TEXT
(a path connective between the two places), which only the parser can see, so it
is recorded here instead of re-derived downstream.

False on every existing row; a reprocess re-derives it. Display-only — nothing
in tracking or fusion reads it.

Revision ID: 0033
Revises: 0032
Create Date: 2026-08-24T10:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0033'
down_revision: Union[str, Sequence[str], None] = '0032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('threats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('movement_stated', sa.Boolean(),
                                      nullable=False, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('threats', schema=None) as batch_op:
        batch_op.drop_column('movement_stated')
