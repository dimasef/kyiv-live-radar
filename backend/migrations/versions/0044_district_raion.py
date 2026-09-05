"""Which raion a gazetteer point lies in: districts.raion_id

Tier 3 of track grouping (domain/tracking.py::find_nearby_track) breaks a tie
between two candidate tracks by raion: exactly one candidate whose latest place
shares the incoming place's raion wins. Pairs inside one raion reach 12.3 km
(Конча-Заспа/Деміївка), so the raion is a discriminator, not a distance.

No data backfill here: app/seed.py::_assign_raions fills the column on the next
startup from the raion boundaries (a raion row points at itself; a point outside
every boundary stays NULL, and NULL never equals NULL in the discriminator).

Revision ID: 0044
Revises: 0043
Create Date: 2026-09-05T20:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0044'
down_revision: Union[str, Sequence[str], None] = '0043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('raion_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_districts_raion_id_districts', 'districts', ['raion_id'], ['id'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.drop_constraint('fk_districts_raion_id_districts', type_='foreignkey')
        batch_op.drop_column('raion_id')
