"""track_lifecycle_and_repost_channel

Adds the explicit track-lifecycle columns (kind/closed_reason — see
app/lifecycle.py) and the repost origin-channel id used by
fusion.py::_origin_keys to disambiguate reposts from different channels that
share a numeric message id.

Data backfill for existing rows: `kind` defaults to 'track', flipped to
'impact' for rows that already have status='impact'. `closed_reason` backfills
from `status` for already-closed rows — 'destroyed' maps directly, and the
historical 'lost' (which conflated відбій / дорозвідка stand-down / silence
timeout into one value) maps to 'stale' since the original distinction isn't
recoverable from stored data. Open tracks and impact markers get NULL.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-12 09:58:16.490527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('forwarded_from_channel_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('threat_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('forwarded_from_channel_id', sa.Integer(), nullable=True))

    with op.batch_alter_table('threats', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('kind', sa.String(length=10), nullable=False, server_default='track')
        )
        batch_op.add_column(sa.Column('closed_reason', sa.String(length=20), nullable=True))

    threats = sa.table(
        'threats',
        sa.column('status', sa.String),
        sa.column('kind', sa.String),
        sa.column('closed_reason', sa.String),
    )
    op.execute(threats.update().where(threats.c.status == 'impact').values(kind='impact'))
    op.execute(
        threats.update().where(threats.c.status == 'destroyed').values(closed_reason='destroyed')
    )
    op.execute(threats.update().where(threats.c.status == 'lost').values(closed_reason='stale'))

    # Drop the server_default now that existing rows are backfilled — new rows
    # get 'track' from the ORM-side mapped_column default, matching models.py.
    with op.batch_alter_table('threats', schema=None) as batch_op:
        batch_op.alter_column('kind', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('threats', schema=None) as batch_op:
        batch_op.drop_column('closed_reason')
        batch_op.drop_column('kind')

    with op.batch_alter_table('threat_events', schema=None) as batch_op:
        batch_op.drop_column('forwarded_from_channel_id')

    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.drop_column('forwarded_from_channel_id')
