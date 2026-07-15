"""raw_message_llm_attempted

Adds `raw_messages.llm_attempted` — whether the LLM fallback was actually
called for this message (see pipeline/ingest.py::_resolve), for the /raw
debug view. Existing rows backfill to NULL: genuinely unknown, since nothing
recorded this historically and re-deriving it from today's parser would
reflect current logic, not what actually ran at ingest time.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-15T15:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('llm_attempted', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.drop_column('llm_attempted')
