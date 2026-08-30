"""Operator's manual attack type

`incidents.type_override` holds what the operator says an attack IS, overriding
the type derived from its member tracks. NULL — the default and the value every
existing row gets — means "derive it", i.e. exactly the behaviour before this
column existed, so nothing is backfilled.

It has to be a stored column rather than a write to `incidents.target_type`:
that field and `attack_types` are rebuilt from the members by
`domain/incidents.recompute_incident_types` on every attach, so during a live
raid a plain write would be erased within seconds.

Nullable add, no server_default and no data pass — safe on both dialects.

Revision ID: 0039
Revises: 0038
Create Date: 2026-08-31T00:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0039'
down_revision: Union[str, Sequence[str], None] = '0038'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('incidents', sa.Column('type_override', sa.String(length=20), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('incidents', 'type_override')
