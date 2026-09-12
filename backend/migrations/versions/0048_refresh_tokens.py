"""Refresh tokens become server-side state

Until now a refresh JWT was valid for its whole 30-day life: logout was a
client-side discard, and nothing but blocking the account could end a leaked
one. Each issued refresh token now has a row here keyed by its `jti`; using it
rotates it (the old row is revoked, a new one issued), logout revokes it, and
presenting an already-revoked one revokes the user's whole family — the
standard reuse-detection signal that a token was stolen.

Tokens minted before this migration have no row and are refused once, which
logs everyone out one time.

Revision ID: 0048
Revises: 0047
Create Date: 2026-09-12T12:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0048'
down_revision: Union[str, Sequence[str], None] = '0047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'refresh_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('jti', sa.String(length=32), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_refresh_tokens_jti', 'refresh_tokens', ['jti'], unique=True)
    op.create_index('ix_refresh_tokens_user_id', 'refresh_tokens', ['user_id'])


def downgrade() -> None:
    op.drop_index('ix_refresh_tokens_user_id', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_jti', table_name='refresh_tokens')
    op.drop_table('refresh_tokens')
