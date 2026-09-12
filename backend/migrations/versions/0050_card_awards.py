"""Milestone card awards

`card_awards` records the cards handed out for reaching an analysis count
(domain/cards.MILESTONE_CARDS). They cannot live in `threat_analyses`: that
table's row IS one analysis of one target, and a milestone card is neither.

Deliberately NO backfill, though the awards for every already-passed threshold
could be computed from the analysis counts. An account that qualifies collects
them on its next analysis, one reveal after another — writing the rows here
would hand the cards over silently and steal exactly that moment.

Revision ID: 0050
Revises: 0049
Create Date: 2026-09-12T18:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0050'
down_revision: Union[str, Sequence[str], None] = '0049'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'card_awards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('card_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'card_id', name='uq_card_award_user_card'),
    )
    # Named explicitly, matching what `index=True` on the model generates, so
    # test_migrations_create_every_index_the_models_declare stays satisfied.
    op.create_index(op.f('ix_card_awards_user_id'), 'card_awards', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_card_awards_user_id'), table_name='card_awards')
    op.drop_table('card_awards')
