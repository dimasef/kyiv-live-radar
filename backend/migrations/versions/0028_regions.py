"""Watched regions: districts/sources/threats carry a region

The radar was single-region by assumption, not by configuration: the track pool,
the all-clear and the stale sweep were all global, so any second region's
sightings would have merged into Kyiv's tracks. `region` makes the pool
explicit — 'kyiv' (м. Київ + Київська обл.) and 'chernihiv' (the northern
early-warning approach).

Every existing row is 'kyiv', which is exactly what it was implicitly, so this
is behaviour-preserving on its own: nothing produces 'chernihiv' yet.

`districts.city` is dropped in the same revision. It defaulted to "Kyiv", was
never written by the gazetteer seed and never read anywhere — a dead
almost-region column that would only confuse the real one.

Revision ID: 0028
Revises: 0027
Create Date: 2026-08-19T18:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0028'
down_revision: Union[str, Sequence[str], None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# server_default backfills existing rows in one statement; the model carries a
# Python-side default, so the DB-side one is only needed for the ALTER itself.
_REGION = sa.String(length=20)


def upgrade() -> None:
    """Upgrade schema."""
    for table in ('districts', 'sources', 'threats'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column('region', _REGION, nullable=False, server_default='kyiv')
            )
    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.drop_column('city')
    op.create_index('ix_threats_region_closed_at', 'threats', ['region', 'closed_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_threats_region_closed_at', table_name='threats')
    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('city', sa.String(length=80), nullable=False, server_default='Kyiv')
        )
    for table in ('districts', 'sources', 'threats'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('region')
