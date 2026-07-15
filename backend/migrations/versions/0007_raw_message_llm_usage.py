"""raw_message_llm_usage

Adds `raw_messages.llm_input_tokens` / `llm_output_tokens` / `llm_cost_usd` —
token usage and computed cost for the LLM fallback call, set alongside
`llm_attempted` whenever the call actually completed (see
pipeline/ingest.py::_resolve, parsing/llm.py::llm_extract). Existing rows
backfill to NULL: no usage was recorded before this column existed.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-15T15:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('llm_input_tokens', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('llm_output_tokens', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('llm_cost_usd', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.drop_column('llm_cost_usd')
        batch_op.drop_column('llm_output_tokens')
        batch_op.drop_column('llm_input_tokens')
