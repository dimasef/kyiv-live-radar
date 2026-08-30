"""Per-source LLM switch

`sources.llm_enabled` decides whether a channel's messages go through the LLM
step at all — all three consumers at once (inline localization, the target-type
classifier, the async triage pass). Until now every source went through it
unconditionally, and the only switches were global (`llm_type_mode`,
`llm_fallback_enabled`, `triage_enabled`): silencing one badly-read channel meant
silencing the classifier for every channel.

Behaviour-preserving on upgrade. The column lands NOT NULL with a server default
of true, which is exactly what every existing row already was — the default IS
the backfill, so there is no UPDATE to get right on one dialect and wrong on the
other.

`sa.true()` rather than a literal '1'/'TRUE' string: SQLite stores booleans as
integers and Postgres as a real boolean type, and the construct renders the right
one for each (the class of dialect split migration 0034 was fixed for).

Revision ID: 0037
Revises: 0036
Create Date: 2026-08-30T10:40:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0037'
down_revision: Union[str, Sequence[str], None] = '0036'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('llm_enabled', sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.drop_column('llm_enabled')
