"""Pin each monitored channel to its Telegram id, not its username

`sources.tg_channel_id` — learned on the first successful resolve and then used
as the row's true identity.

A username is mutable. On 2026-08-03 @KievRadar renamed itself to @kyiv_allerts
and the row, which resolved by handle, quietly stopped matching the channel it
was meant to watch. The worse half of that failure is that a freed Telegram
handle can be claimed by anyone: `_resolve_channel` would resolve the new owner,
JOIN it, and feed a stranger's posts into the threat stream carrying the trust
weight of the spotter it replaced.

NULL means "not learned yet" — the next successful resolve fills it in, so
existing rows adopt their id on the first connect after deploy with no backfill.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-03T17:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0026'
down_revision: Union[str, Sequence[str], None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tg_channel_id', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.drop_column('tg_channel_id')
