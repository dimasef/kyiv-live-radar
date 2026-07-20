"""users_auth

User accounts + linked SSO identities + a nullable owner FK on push
subscriptions. See app/auth/ and app/models.py (User / OAuthIdentity).

Backward-compatible: existing push_subscriptions rows get user_id = NULL
(anonymous device subs), unchanged in behavior.

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-20T12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0014'
down_revision: Union[str, Sequence[str], None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=True),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=10), nullable=False, server_default='user'),
        sa.Column('display_name', sa.String(length=120), nullable=True),
        sa.Column('avatar_url', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    # Partial-null unique: many null-email (Telegram-only) rows may coexist,
    # while a present email is unique. Both SQLite & Postgres treat NULLs distinct.
    op.create_index('uq_users_email', 'users', ['email'], unique=True)

    op.create_table(
        'oauth_identities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False),
        sa.Column('provider_user_id', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=True),
        sa.Column('raw_profile', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'provider_user_id', name='uq_identity_provider_user'),
    )

    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        # Named so the batch (SQLite table-rebuild) can drop it on downgrade.
        batch_op.create_foreign_key(
            'fk_push_subscriptions_user_id', 'users', ['user_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('push_subscriptions', schema=None) as batch_op:
        batch_op.drop_constraint('fk_push_subscriptions_user_id', type_='foreignkey')
        batch_op.drop_column('user_id')
    op.drop_table('oauth_identities')
    op.drop_index('uq_users_email', table_name='users')
    op.drop_table('users')
