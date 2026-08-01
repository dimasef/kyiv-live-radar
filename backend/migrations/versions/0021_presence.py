"""contact presence

`users.last_seen_at` (stamped on authenticated requests) plus
`users.share_presence`, which gates the last-seen TIMESTAMP only — the live
online dot is visible to accepted friends regardless.

`share_presence` defaults to TRUE, and that default is applied to existing rows
too: the server_default backfills them on ADD COLUMN. This is a deliberate
operator decision — it means accounts created before this migration start
disclosing their last-active time to accepted friends without acting. The
per-user opt-out is PUT /me/presence.

Revision ID: 0021
Revises: 0020
Create Date: 2026-08-01T19:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0021'
down_revision: Union[str, Sequence[str], None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(
            sa.Column('share_presence', sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('share_presence')
        batch_op.drop_column('last_seen_at')
