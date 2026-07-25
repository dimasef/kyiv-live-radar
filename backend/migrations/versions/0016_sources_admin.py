"""sources admin

Make the sources table admin-manageable: the live listener now subscribes to
the active rows in this table (not the env channel lists), and the /admin
console edits them. All additive; existing rows keep working (subscribe_ref
NULL falls back to channel_key, is_active already defaulted True).

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-25T13:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0016'
down_revision: Union[str, Sequence[str], None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    `added_by_user_id` is added as a plain nullable column WITHOUT a DB-level
    foreign key: adding a FK to `sources` (which raw_messages/threat_events/
    notices already reference) inside a SQLite batch rebuild raises Alembic's
    CircularDependencyError. It's provenance-only, SQLite doesn't enforce FKs,
    and the ORM model still declares the ForeignKey for create_all — so nothing
    depends on the constraint existing on an upgraded DB."""
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.add_column(sa.Column('subscribe_ref', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('last_listener_error', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('added_by_user_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('sources', schema=None) as batch_op:
        batch_op.drop_column('added_by_user_id')
        batch_op.drop_column('created_at')
        batch_op.drop_column('last_listener_error')
        batch_op.drop_column('subscribe_ref')
