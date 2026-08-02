"""Let the owner choose how their own home marker looks

`users.home_icon` / `users.home_color` — the shape and colour of the marker the
user sees over their own home. Private to the owner, exactly like
`contact_prefs` from 0023: friends keep labelling that home however they like on
their own map, so these two columns are absent from FriendOut and only ever
reach the account they belong to.

On the account rather than in localStorage because that is what makes the
setting an account feature at all — an anonymous visitor keeps the default cyan
house. Both nullable, NULL meaning "default", so no backfill.

(The halo toggle that belongs to the same feature ships as its own revision,
0025 — this one had already been applied to a live DB by the time it was asked
for, and Alembic never re-runs a revision the DB is already stamped with.)

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-02T20:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0024'
down_revision: Union[str, Sequence[str], None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('home_icon', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('home_color', sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('home_color')
        batch_op.drop_column('home_icon')
