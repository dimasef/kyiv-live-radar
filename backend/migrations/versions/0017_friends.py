"""friends

Friend graph + shareable home. Adds a `friendships` edge table (request/accept
consent model) and promotes home location to first-class, shareable columns on
`users` (home_lat/home_lon/share_home) so a friend's home can be shown on the
map independently of any per-device push subscription.

Backward-compatible: existing users get NULL home + share_home=False (opt-in),
so nothing is shared until the owner turns it on.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-28T12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0017'
down_revision: Union[str, Sequence[str], None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    `friendships` FKs to `users` are declared in create_table (not a batch
    rebuild), so the SQLite circular-dependency footgun from 0016 does not apply
    — mirrors how 0014 created `oauth_identities` with a FK to users.

    The `users` additions are plain columns with NO foreign keys, so the batch
    rebuild is safe.
    """
    op.create_table(
        'friendships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('requester_id', sa.Integer(), nullable=False),
        sa.Column('addressee_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('responded_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['requester_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['addressee_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('requester_id', 'addressee_id', name='uq_friendship_pair'),
    )

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('home_lat', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('home_lon', sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column('share_home', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('share_home')
        batch_op.drop_column('home_lon')
        batch_op.drop_column('home_lat')
    op.drop_table('friendships')
