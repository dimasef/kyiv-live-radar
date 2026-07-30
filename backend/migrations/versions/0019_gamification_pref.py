"""gamification account preference

Promote the opt-in gamification toggle from client-only localStorage to an
account-bound setting (`users.gamification`), so enabling it on one device
carries to the user's other devices. Additive, defaults to False (opt-in
preserved).

Revision ID: 0019
Revises: 0018
Create Date: 2026-07-30T12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0019'
down_revision: Union[str, Sequence[str], None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('gamification', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('gamification')
