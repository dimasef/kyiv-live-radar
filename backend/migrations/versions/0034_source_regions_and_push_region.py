"""Multi-region sources, and a per-device push region

Two columns, both in service of the same shift: a region stops being something
the deployment has one of, and becomes something a SOURCE is bound to and a
DEVICE is currently in.

`sources.extra_regions` — a channel may localize into more than one region.
This is what makes "a source only ever pins targets inside its own regions"
safe to enforce: the Kyiv channels legitimately narrate the northern approach
(68 stored events over Chernihiv raions), and without a second binding that
rule would have deleted every one of them. `region` stays the PRIMARY (the
district-less fallback, and the winner of a homonym tie). Existing rows ARE
backfilled — see the reasoning at the UPDATE below.

`push_subscriptions.region` — which region's tracks this device wants waking
for. Per-subscription rather than per-account because that is what "where I am"
means: a phone carried to Kharkiv follows it there while the desktop at home
keeps watching Kyiv. NULL means the deployment's primary region, which is what
every existing row implicitly was — so that one needs no backfill.

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-28T12:00:00

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0034'
down_revision: Union[str, Sequence[str], None] = '0033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('extra_regions', sa.JSON(),
                                      nullable=False, server_default='[]'))
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('region', sa.String(length=20), nullable=True))

    # Backfill so the new rule is behaviour-PRESERVING on upgrade.
    #
    # The rule it replaces was asymmetric: a home-region channel could match any
    # region's place, every other channel only its own. Leaving `extra_regions`
    # empty would therefore narrow every Kyiv channel to Kyiv overnight and throw
    # away exactly the cross-border narration this column exists to keep (68
    # stored events over Chernihiv raions).
    #
    # Chernihiv ALONE, not every declared region, even though the old rule let a
    # Kyiv channel match anything. The two are indistinguishable today — the
    # other regions are declared with an empty gazetteer, so no name can resolve
    # into them either way — and binding to all of them would quietly arm the
    # trap the moment one gets entries: a Kyiv channel saying «Ромни» would hand
    # its track to the Sumy pool, out of the journal, the incidents and the
    # home-danger push. Widen a channel deliberately in /admin instead. This also
    # keeps a migrated DB identical to a freshly seeded one (gazetteer.SOURCES).
    #
    # Regions are listed literally rather than imported from app.regions: a
    # migration records what was true when it ran, and must not change meaning
    # the next time that tuple is edited.
    home = 'kyiv'
    others = ['chernihiv']
    op.execute(
        sa.text("UPDATE sources SET extra_regions = :val WHERE region = :home").bindparams(
            val=json.dumps(others), home=home
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_column('region')
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.drop_column('extra_regions')
