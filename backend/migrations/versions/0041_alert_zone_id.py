"""District sirens become Alert rows: alerts.zone_id

The raion siren layer (app/feeds/alert_zones.py) was deliberately stateless — it
only painted polygons. That left the banner unable to answer the question a
reader outside Kyiv city actually asks ("is MY raion under alert?"), because the
only stored alerts came from the Kyiv channel and were oblast-grained.

`zone_id` is the raion this alert belongs to (`domain/alert_zones.Zone.id`), NULL
for the official channel's city/oblast announcements. No backfill: every existing
row IS an official announcement, so NULL already says the right thing about all
of them.

Revision ID: 0041
Revises: 0040
Create Date: 2026-09-01T10:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0041'
down_revision: Union[str, Sequence[str], None] = '0040'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('alerts', sa.Column('zone_id', sa.String(length=40), nullable=True))
    op.create_index(
        'ix_alerts_region_zone_started_at', 'alerts',
        ['region', 'zone_id', 'started_at'], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_alerts_region_zone_started_at', table_name='alerts')
    with op.batch_alter_table('alerts', schema=None) as batch_op:
        batch_op.drop_column('zone_id')
