"""push_subscriptions

Web Push for danger-near-home: one row per browser push endpoint, carrying the
home zone it guards (lat/lon/radius + the containing raion resolved at
subscribe time) and per-track danger bookkeeping so pushes fire on level
escalation only (see app/pipeline/home_push.py).

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-18T12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'push_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('endpoint', sa.Text(), nullable=False),
        sa.Column('p256dh', sa.String(length=200), nullable=False),
        sa.Column('auth', sa.String(length=100), nullable=False),
        sa.Column('home_lat', sa.Float(), nullable=True),
        sa.Column('home_lon', sa.Float(), nullable=True),
        sa.Column('home_radius_km', sa.Float(), nullable=False, server_default='3.0'),
        sa.Column('home_district_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('danger_state', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('last_push_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['home_district_id'], ['districts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('endpoint'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('push_subscriptions')
