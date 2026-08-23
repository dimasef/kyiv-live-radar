"""LLM target-type verdict on raw_messages

Three nullable columns holding what app/parsing/type_llm.py said about a message
whose type neither the rules, the per-channel context window nor the incident
prior could determine: the type, its confidence, and where the model got it
('text' | 'context' | 'none').

Stored whether or not the verdict was applied — in shadow mode nothing consumes
it, and a stored verdict is also what makes an admin reprocess free (ingest
replays it instead of paying for the call again).

NULL on every existing row and on every message that never needed the call,
which is the vast majority.

Revision ID: 0032
Revises: 0031
Create Date: 2026-08-23T18:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0032'
down_revision: Union[str, Sequence[str], None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('llm_type', sa.String(length=12), nullable=True))
        batch_op.add_column(sa.Column('llm_type_confidence', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('llm_type_evidence', sa.String(length=8), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.drop_column('llm_type_evidence')
        batch_op.drop_column('llm_type_confidence')
        batch_op.drop_column('llm_type')
