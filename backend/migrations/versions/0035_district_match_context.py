"""Per-entry neighbouring-word rules for the gazetteer

`districts.match_context` scopes a context hook to ONE entry instead of to every
entry that matched the same word. The four `vocab._ALIAS_*` dicts are keyed by
the matched text, which is enough while one entry owns a word and impossible
when two share it: the rule that keeps Писарівка honest is exactly the rule that
must not silence Велика Писарівка 80 km away.

Every existing row is NULL, which is "no rules" — what they all were — so this
is behaviour-preserving until the gazetteer sets it. No backfill, so nothing
here needs a typed Core table (the trap 0.38.0 fell into).

Revision ID: 0035
Revises: 0034
Create Date: 2026-08-29T18:10:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0035'
down_revision: Union[str, Sequence[str], None] = '0034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('match_context', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.drop_column('match_context')
