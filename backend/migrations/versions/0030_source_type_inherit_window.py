"""Per-source type-inheritance window

`sources.type_inherit_minutes` overrides settings.type_inherit_window_minutes
for one channel. NULL (every existing row) keeps the global default, so this is
behaviour-preserving until an operator sets a value.

Why per-source: the window is about how a channel WRITES, not about what it
watches. Measured on 2026-08-18..21, the northern spotter channel states a
target type once at the start of a wave and then writes pure vectors — 84% of
its untyped events had no stated type within the 5-minute default, 58% had one
within 30. The Kyiv channels restate the type constantly and routinely mix
ballistic and drones in one night, where a wider window would be a regression.

Revision ID: 0030
Revises: 0029
Create Date: 2026-08-21T20:10:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0030'
down_revision: Union[str, Sequence[str], None] = '0029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('type_inherit_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.drop_column('type_inherit_minutes')
