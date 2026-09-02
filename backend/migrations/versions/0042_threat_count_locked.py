"""An operator's target count outranks the parser: threats.target_count_locked

`Threat.target_count` is a running max over the group sizes spotters state
within a reply chain (pipeline/ingest/context._apply_update). That is right
while nobody has looked, and wrong the moment someone has: an operator who
corrects an inflated "5" down to "2" was overruled by the next message that
restated a bigger number, because the max has no way to know one of its inputs
had already been judged wrong.

The flag says "a human decided this one". No backfill: every existing row was
derived by the pipeline, so False is already true of all of them.

Revision ID: 0042
Revises: 0041
Create Date: 2026-09-02T12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0042'
down_revision: Union[str, Sequence[str], None] = '0041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'threats',
        sa.Column(
            'target_count_locked', sa.Boolean(), nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('threats', schema=None) as batch_op:
        batch_op.drop_column('target_count_locked')
