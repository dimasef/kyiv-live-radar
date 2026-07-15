"""notice_source_message_id

Adds `notices.source_message_id` — the originating channel message id, mirroring
ThreatEvent.source_message_id. Lets /raw_messages trace a raw message to the
notice it became (all-clear / summary), not just to a ThreatEvent. Existing
notices backfill to NULL (not recoverable from stored data).

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-15T14:34:38

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('notices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_message_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('notices', schema=None) as batch_op:
        batch_op.drop_column('source_message_id')
