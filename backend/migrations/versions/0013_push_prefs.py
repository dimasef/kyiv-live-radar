"""push_prefs

Per-subscription notification preferences (phase 1 of flexible notifications):
    {"min_level": "warning"|"danger",     # escalation floor for home pushes
     "types": ["ballistic", ...],          # allowed target types (unknown always passes)
     "citywide": bool}                     # push on a city-wide alert track too
Absent/empty prefs mean the pre-0.10 behavior (warning+danger, all types) plus
citywide on — the single-user MVP asked for the citywide push, so it defaults
enabled rather than silently off for the existing subscription.

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-19T12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('prefs', sa.JSON(), nullable=False, server_default='{}'))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_column('prefs')
