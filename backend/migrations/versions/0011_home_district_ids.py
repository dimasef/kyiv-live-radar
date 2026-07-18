"""home_district_ids

A home zone on a raion boundary sits in 2-3 raions at once — the ballistic
danger trigger must match ALL of them, not just the raion containing the home
point. Replaces push_subscriptions.home_district_id (single FK) with
home_district_ids (JSON list, resolved by home_danger.raion_ids_for_zone).
Existing single ids are carried over as one-element lists; the next subscribe
resync (frontend re-POSTs home on boot) re-resolves the full set.

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-18T18:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('home_district_ids', sa.JSON(), nullable=False, server_default='[]')
        )

    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, home_district_id FROM push_subscriptions WHERE home_district_id IS NOT NULL"
    )).fetchall()
    for sub_id, district_id in rows:
        conn.execute(
            sa.text("UPDATE push_subscriptions SET home_district_ids = :ids WHERE id = :id"),
            {"ids": f"[{district_id}]", "id": sub_id},
        )

    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_column('home_district_id')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('home_district_id', sa.Integer(), nullable=True))
        batch_op.drop_column('home_district_ids')
