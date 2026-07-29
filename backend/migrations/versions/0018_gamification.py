"""gamification

Collectible-card analysis of targets (opt-in coping mechanic). Adds one table,
`threat_analyses`, which doubles as the per-user card collection and the
scarcity ledger: `UniqueConstraint(threat_id, kind)` makes each of a target's
two analyses ('track' / 'remains') a global first-writer-wins claim.

No changes to existing tables — purely additive, safe to run on a live DB.

Revision ID: 0018
Revises: 0017
Create Date: 2026-07-29T12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0018'
down_revision: Union[str, Sequence[str], None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'threat_analyses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('threat_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('card_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['threat_id'], ['threats.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('threat_id', 'kind', name='uq_analysis_threat_kind'),
    )
    op.create_index(
        op.f('ix_threat_analyses_threat_id'), 'threat_analyses', ['threat_id']
    )
    op.create_index(
        op.f('ix_threat_analyses_user_id'), 'threat_analyses', ['user_id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_threat_analyses_user_id'), table_name='threat_analyses')
    op.drop_index(op.f('ix_threat_analyses_threat_id'), table_name='threat_analyses')
    op.drop_table('threat_analyses')
