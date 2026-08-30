"""Operator-dismissed coverage-gap candidates

`toponym_dismissals` holds the words the operator marked as "not a place" while
reading Адмінка → Прогалини. The curated lists in `parsing/toponyms.py` stay
where they are — each of those is a decision with a documented failure mode (a
stop word that is a prefix of a real name silently costs the next such village)
— and this table is their operator-editable half: one exact word, matched whole,
no deploy needed.

New table only, nothing backfilled: an empty table is exactly the behaviour
before it existed.

Revision ID: 0038
Revises: 0037
Create Date: 2026-08-30T15:10:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0038'
down_revision: Union[str, Sequence[str], None] = '0037'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'toponym_dismissals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('word', sa.String(length=60), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('word'),
    )
    op.create_index(
        op.f('ix_toponym_dismissals_word'), 'toponym_dismissals', ['word'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_toponym_dismissals_word'), table_name='toponym_dismissals')
    op.drop_table('toponym_dismissals')
