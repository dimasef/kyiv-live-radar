"""corrections

Learning-from-corrections tables: parser_corrections (admin actions harvested
into a labeled regression dataset — see app/domain/corrections.py) and
gazetteer_candidates (toponyms flagged from the coverage-gap queue). Both are
additive; existing data is untouched.

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-25T12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0015'
down_revision: Union[str, Sequence[str], None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'parser_corrections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('raw_message_id', sa.Integer(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('expected', sa.JSON(), nullable=False),
        sa.Column('origin', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['raw_message_id'], ['raw_messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('raw_message_id', 'kind', name='uq_correction_raw_kind'),
    )

    op.create_table(
        'gazetteer_candidates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('raw_message_id', sa.Integer(), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('suggested_name', sa.String(length=200), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['raw_message_id'], ['raw_messages.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('gazetteer_candidates')
    op.drop_table('parser_corrections')
