"""threat_context_layer

Additive schema for the LLM threat-context layer (async triage + directional
axes). One migration for the whole feature so it ships and rolls back as a unit:

- raw_messages.triage_state / triage_action — async-triage bookkeeping.
- notices.origin / generated_by — directional origin + rule-vs-LLM provenance
  (new notice kinds directional/forecast/status need no DDL — kind is a string).
- threat_events.llm_summary — operator-facing gist for the feed headline.
- threat_axes — the directional-axis entity (its own lifecycle: fusion window,
  corroboration, TTL), mirroring the Alert/Incident pattern.

All columns nullable or server-defaulted; existing rows backfill cleanly.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-16T12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.add_column(sa.Column('triage_state', sa.String(length=12), nullable=True))
        batch_op.add_column(sa.Column('triage_action', sa.String(length=20), nullable=True))

    with op.batch_alter_table('notices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('origin', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column(
            'generated_by', sa.String(length=10), nullable=False, server_default='rule'
        ))

    with op.batch_alter_table('threat_events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('llm_summary', sa.Text(), nullable=True))

    op.create_table(
        'threat_axes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('target_type', sa.String(length=20), nullable=False, server_default='unknown'),
        sa.Column('origin_key', sa.String(length=20), nullable=True),
        sa.Column('sector', sa.String(length=4), nullable=False, server_default='N'),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='unverified'),
        sa.Column('corroboration_count', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('origin_keys_seen', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('raw_ids', sa.JSON(), nullable=False, server_default='[]'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('threat_axes')
    with op.batch_alter_table('threat_events', schema=None) as batch_op:
        batch_op.drop_column('llm_summary')
    with op.batch_alter_table('notices', schema=None) as batch_op:
        batch_op.drop_column('generated_by')
        batch_op.drop_column('origin')
    with op.batch_alter_table('raw_messages', schema=None) as batch_op:
        batch_op.drop_column('triage_action')
        batch_op.drop_column('triage_state')
