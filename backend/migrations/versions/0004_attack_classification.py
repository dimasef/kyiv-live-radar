"""attack_classification

Adds attack-classification fields to `incidents` (see app/attack.py::classify,
which derives the actual label from these at serialization time — nothing
here is a stored classification itself). Existing incidents backfill to
attack_types=[], decoy_mentions=0, has_hypersonic=False; `ended_reason` and
`alert_id` stay NULL for historical rows (not recoverable from stored data).

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-12 17:50:24.368048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0004'
down_revision: Union[str, Sequence[str], None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.add_column(sa.Column('ended_reason', sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column('attack_types', sa.JSON(), nullable=False, server_default='[]')
        )
        batch_op.add_column(sa.Column('alert_id', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('decoy_mentions', sa.Integer(), nullable=False, server_default='0')
        )
        batch_op.add_column(
            sa.Column('has_hypersonic', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.create_foreign_key('fk_incidents_alert_id', 'alerts', ['alert_id'], ['id'])

    # Drop the server_defaults now that existing rows are backfilled — new
    # rows get their defaults from the ORM-side mapped_column, matching
    # models.py.
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.alter_column('attack_types', server_default=None)
        batch_op.alter_column('decoy_mentions', server_default=None)
        batch_op.alter_column('has_hypersonic', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('incidents', schema=None) as batch_op:
        batch_op.drop_constraint('fk_incidents_alert_id', type_='foreignkey')
        batch_op.drop_column('has_hypersonic')
        batch_op.drop_column('decoy_mentions')
        batch_op.drop_column('alert_id')
        batch_op.drop_column('attack_types')
        batch_op.drop_column('ended_reason')
