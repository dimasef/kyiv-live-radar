"""User-filed bug reports

`bug_reports` — a description, an optional inline screenshot, and the technical
context the app collected for the reporter (version, browser, OS, viewport,
page scale).

The context columns are the reason this table exists. The 2026-08-12 Android
report arrived as one screenshot with no version, browser or viewport, and the
diagnosis had to begin by measuring pixels in a JPEG.

`user_id` is ON DELETE SET NULL: a deleted account must not take the bug it
reported with it.

Revision ID: 0027
Revises: 0026
Create Date: 2026-08-12T22:10:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0027'
down_revision: Union[str, Sequence[str], None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'bug_reports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('screenshot', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='new'),
        sa.Column('app_version', sa.String(length=20), nullable=True),
        sa.Column('browser', sa.String(length=60), nullable=True),
        sa.Column('os', sa.String(length=60), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('context', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_bug_reports_user_id', 'bug_reports', ['user_id'])
    # The admin list is "newest first, optionally filtered by status".
    op.create_index('ix_bug_reports_status_created', 'bug_reports', ['status', 'created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_bug_reports_status_created', table_name='bug_reports')
    op.drop_index('ix_bug_reports_user_id', table_name='bug_reports')
    op.drop_table('bug_reports')
