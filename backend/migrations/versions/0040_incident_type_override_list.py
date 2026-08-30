"""Operator's manual attack type becomes a LIST

0039 added `incidents.type_override` as a single VARCHAR, which cannot express
the case that prompted it: a raid of several weapon families at once reads as
'комбінована', and `domain/attack.classify` only says that when it is given ≥2
families. One string could name a family or say nothing — never "both".

So the column becomes JSON holding the list of types the operator says are in
the air. `classify` then derives 'combined' by itself, exactly as it does for
the automatic path, instead of 'combined' needing to be a magic value that the
TargetType enum does not contain.

Replaced rather than converted: 0039 has already been applied on dev, so its own
file must not be edited (an applied revision is never re-run, and the DB would
silently keep the old column). Nothing is migrated across — the feature has never
been released, so every existing value is NULL by construction. `batch_alter_table`
for the drop because SQLite needs the table rebuilt; Postgres ignores the batching.

Revision ID: 0040
Revises: 0039
Create Date: 2026-08-31T01:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0040'
down_revision: Union[str, Sequence[str], None] = '0039'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.drop_column('type_override')
    op.add_column('incidents', sa.Column('type_override', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.drop_column('type_override')
    op.add_column('incidents', sa.Column('type_override', sa.String(length=20), nullable=True))
