"""raw_message_llm_response

Adds `raw_messages.llm_response` — the full structured JSON the LLM fallback
returned (district_ids plus the triage fields category/surface/summary/
target_type/status/...), stored verbatim so LLM calls are auditable on the /raw
debug view and so the Stage-3 context layer can be tuned against real responses
(see parsing/llm.py::llm_extract, pipeline/ingest.py::process_parsed). Existing
rows backfill to NULL: the response was discarded before this column existed.
Collected-only — nothing in the live pipeline routes on these fields yet.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-15T18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('llm_response', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.drop_column('llm_response')
