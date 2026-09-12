"""Email verification tokens; Telegram sign-in removed

`email_tokens` holds the one-time links for address verification and password
reset (hashes only — see app/auth/verification.py).

Telegram Login is gone as a provider. Its identity rows go, and with them the
accounts that had NOTHING else — no email, no password — since no route can
ever sign them in again. Google accounts always carry a verified email, so
"no email and no password" identifies exactly the Telegram-only users. Their
dependents are handled explicitly rather than trusted to ON DELETE: SQLite
does not enforce foreign keys without a PRAGMA, and the SET NULL columns must
end up NULL on both dialects.

Revision ID: 0049
Revises: 0048
Create Date: 2026-09-12T16:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0049'
down_revision: Union[str, Sequence[str], None] = '0048'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


users = sa.table(
    'users',
    sa.column('id', sa.Integer),
    sa.column('email', sa.String),
    sa.column('password_hash', sa.String),
)
identities = sa.table(
    'oauth_identities', sa.column('user_id', sa.Integer), sa.column('provider', sa.String)
)


def _user_col(table: str, col: str) -> sa.TableClause:
    return sa.table(table, sa.column(col, sa.Integer))


def upgrade() -> None:
    op.create_table(
        'email_tokens',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('purpose', sa.String(length=10), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_email_tokens_token_hash', 'email_tokens', ['token_hash'], unique=True)
    op.create_index('ix_email_tokens_user_id', 'email_tokens', ['user_id'])

    op.execute(identities.delete().where(identities.c.provider == 'telegram'))

    orphans = (
        sa.select(users.c.id)
        .where(users.c.email.is_(None), users.c.password_hash.is_(None))
        .scalar_subquery()
    )
    for table, col in (
        ('friendships', 'requester_id'),
        ('friendships', 'addressee_id'),
        ('threat_analyses', 'user_id'),
        ('refresh_tokens', 'user_id'),
        ('oauth_identities', 'user_id'),
    ):
        t = _user_col(table, col)
        op.execute(t.delete().where(t.c[col].in_(orphans)))
    for table, col in (
        ('bug_reports', 'user_id'),
        ('parser_corrections', 'created_by_user_id'),
        ('toponym_dismissals', 'created_by_user_id'),
        ('push_subscriptions', 'user_id'),
        ('sources', 'added_by_user_id'),
    ):
        t = _user_col(table, col)
        op.execute(t.update().where(t.c[col].in_(orphans)).values({col: None}))
    op.execute(users.delete().where(users.c.email.is_(None), users.c.password_hash.is_(None)))


def downgrade() -> None:
    op.drop_index('ix_email_tokens_user_id', table_name='email_tokens')
    op.drop_index('ix_email_tokens_token_hash', table_name='email_tokens')
    op.drop_table('email_tokens')
