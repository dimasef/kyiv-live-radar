"""Move the settings that survive a device change onto the account

`users.home_radius_km` — the owner's danger-zone radius. Coordinates were
already on the row, but only ever written while `share_home` was on, so the
single most laborious setting in the app (place a pin on a map) did not survive
opening the app on another device. Storing it unconditionally makes the account
the source of truth and localStorage a cache. Deliberately NOT exposed to
friends: they see a marker, never how wide the zone is (see MyHomeOut vs
HomePointOut).

`users.contact_prefs` — per-contact map-marker colour/icon and the "hide this
contact's home on my map" flag, keyed by the contact's user id:
`{"7": {"color": "#c084fc", "icon": "star", "hidden": false}}`. Private
labelling, never visible to the contact. Same rationale: re-picking eight
colours on every device is exactly the kind of work an account should absorb.

Both are nullable/defaulted, so existing rows need no backfill — a user with no
stored radius simply falls back to the client default until they touch it.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-02T12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0023'
down_revision: Union[str, Sequence[str], None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('home_radius_km', sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column('contact_prefs', sa.JSON(), nullable=False, server_default='{}')
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('contact_prefs')
        batch_op.drop_column('home_radius_km')
