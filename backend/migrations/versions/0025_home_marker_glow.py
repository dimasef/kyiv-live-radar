"""Let the owner turn the marker's coloured halo off

`users.home_glow` — whether the user's own home marker carries its glow. Splits
out of 0024 rather than joining it: by the time the toggle was asked for, a live
DB was already stamped `0024`, and Alembic never re-runs a revision the DB has
passed. Editing an applied revision leaves the model declaring a column the
table doesn't have, which breaks every query against `users` — including auth.

Nullable, NULL meaning "never chosen", which the client reads as a lit marker —
how every marker looked before this was choosable. No backfill.

The contact-marker equivalent needs no column: per-contact styles live in the
`users.contact_prefs` JSON blob from 0023, which just gained a `glow` key.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-02T22:40:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0025'
down_revision: Union[str, Sequence[str], None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('home_glow', sa.Boolean(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('home_glow')
