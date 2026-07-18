"""telegram_ids_bigint

Telegram peer/message ids are 64-bit. Channel peer ids like -1001754665396
overflow Postgres INTEGER (int32, ±2.1e9) — a live repost crashed the ingest
with `DataError: value out of int32 range` on raw_messages.forwarded_from_channel_id.
This was invisible in local dev because SQLite stores INTEGER as a 64-bit value
regardless of declared type; only Railway's Postgres enforces the width.

Widens every Telegram-id column to BIGINT: raw_messages/threat_events
(message_id, forwarded_from_id, forwarded_from_channel_id, reply_to_message_id,
source_message_id) and notices.source_message_id. Data-preserving — INTEGER ->
BIGINT is a lossless widen; existing values are untouched.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-19T01:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) pairs holding a Telegram peer/message id.
_ID_COLUMNS = [
    ('raw_messages', 'message_id'),
    ('raw_messages', 'forwarded_from_id'),
    ('raw_messages', 'forwarded_from_channel_id'),
    ('raw_messages', 'reply_to_message_id'),
    ('threat_events', 'source_message_id'),
    ('threat_events', 'reply_to_message_id'),
    ('threat_events', 'forwarded_from_id'),
    ('threat_events', 'forwarded_from_channel_id'),
    ('notices', 'source_message_id'),
]


def _alter_all(from_type: sa.types.TypeEngine, to_type: sa.types.TypeEngine) -> None:
    for table, column in _ID_COLUMNS:
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.alter_column(
                column, existing_type=from_type, type_=to_type, existing_nullable=True
            )


def upgrade() -> None:
    """Upgrade schema."""
    _alter_all(sa.Integer(), sa.BigInteger())


def downgrade() -> None:
    """Downgrade schema.

    Narrowing back to INTEGER would truncate any 64-bit id already stored, so
    this is only safe on a DB that never held an out-of-int32 value.
    """
    _alter_all(sa.BigInteger(), sa.Integer())
