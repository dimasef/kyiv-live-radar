"""Aftermath reports — what a strike did to a raion

A new table, not a new `threats.kind`. Every public surface's impact filter is
keyed on the literal 'impact' (api/public/threats.py, serialize.py's
_incident_district_ids, domain/journal.py, the five exits pinned by
tests/test_impact_privacy.py); a new kind would need each rewritten from an
equality to a set membership, and one missed filter publishes where a strike
landed. Nothing but its own route queries this table.

Pure create_table with no data pass: the reports this holds were never stored in
any form — `rules._aftermath` suppressed the message and `clears_districts`
wiped its raions — so there is nothing to backfill and no dialect-specific
UPDATE to get wrong.

Revision ID: 0047
Revises: 0046
Create Date: 2026-09-08T12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0047'
down_revision: Union[str, Sequence[str], None] = '0046'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'aftermath_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('district_id', sa.Integer(), nullable=False),
        sa.Column('region', sa.String(length=20), nullable=False, server_default='kyiv'),
        sa.Column('reported_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('categories', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('text', sa.Text(), nullable=False, server_default=''),
        sa.Column('source_id', sa.Integer(), nullable=True),
        sa.Column('source_message_id', sa.BigInteger(), nullable=True),
        sa.Column('raw_id', sa.Integer(), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id']),
        sa.ForeignKeyConstraint(['source_id'], ['sources.id']),
        sa.ForeignKeyConstraint(['raw_id'], ['raw_messages.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Named explicitly, matching what `index=True` on the model generates, so
    # test_migrations_create_every_index_the_models_declare stays satisfied.
    op.create_index(op.f('ix_aftermath_reports_district_id'), 'aftermath_reports',
                    ['district_id'], unique=False)
    op.create_index(op.f('ix_aftermath_reports_reported_at'), 'aftermath_reports',
                    ['reported_at'], unique=False)
    op.create_index(op.f('ix_aftermath_reports_source_id'), 'aftermath_reports',
                    ['source_id'], unique=False)
    op.create_index(op.f('ix_aftermath_reports_source_message_id'), 'aftermath_reports',
                    ['source_message_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_aftermath_reports_source_message_id'),
                  table_name='aftermath_reports')
    op.drop_index(op.f('ix_aftermath_reports_source_id'), table_name='aftermath_reports')
    op.drop_index(op.f('ix_aftermath_reports_reported_at'), table_name='aftermath_reports')
    op.drop_index(op.f('ix_aftermath_reports_district_id'), table_name='aftermath_reports')
    op.drop_table('aftermath_reports')
