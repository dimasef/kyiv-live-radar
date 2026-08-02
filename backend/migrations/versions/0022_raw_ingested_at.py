"""raw_messages.ingested_at — when WE stored a message, vs. when it was posted

`event_time` is the Telegram timestamp; until now nothing recorded when the row
actually reached us. The two diverge whenever a reconnect backfill replays
history: on 2026-08-02 a 00:14 sighting was stored AFTER the 00:28 відбій, so
its reply-child started a track before the parent existed and the parent then
opened a THIRD track (plus a fresh incident) minutes after the all-clear.
Reconstructing that needed row-id archaeology; `ingested_at - event_time` makes
it a single readable number in /raw.

Nullable on purpose: rows stored before this migration have a genuinely unknown
ingestion time, and 0 or the event time would both be lies. New rows get it from
the column default, so no ingest call site has to remember.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-02T08:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0022'
down_revision: Union[str, Sequence[str], None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ingested_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.drop_column('ingested_at')
