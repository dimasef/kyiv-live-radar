"""A region on the alert and on the incident

The two tables that carried the deployment's one region implicitly. Everything
downstream of them — the banner, the feed's attack rollups, the journal's
attack count and alert duration — therefore spoke about Kyiv while claiming to
speak generally, and each place that noticed got its own patch (three of them in
0.40.0 alone). The column is what makes those patches deletable.

Behaviour-preserving on upgrade. Both columns land NOT NULL with a server
default of 'kyiv', which is exactly what every existing row already was: the
alert channel is Kyiv's, and incidents were gated to the home region at
creation (pipeline/ingest/handlers._incident_broadcast). So the default IS the
backfill — no UPDATE to get wrong on one dialect and right on the other.

The literal 'kyiv' rather than an import from app.regions: a migration records
what was true when it ran, and must not change meaning the next time that
registry is edited.

Revision ID: 0036
Revises: 0035
Create Date: 2026-08-29T21:00:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0036'
down_revision: Union[str, Sequence[str], None] = '0035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    for table in ('alerts', 'incidents'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('region', sa.String(length=20),
                                          nullable=False, server_default='kyiv'))

    # An open alert is now found per (region, scope) rather than by scope
    # alone, so the index that served the old lookup is REPLACED rather than
    # joined by a second one — the old one can no longer serve the query's
    # leading column.
    op.drop_index('ix_alerts_scope_started_at', table_name='alerts')
    op.create_index('ix_alerts_region_scope_started_at', 'alerts',
                    ['region', 'scope', 'started_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_alerts_region_scope_started_at', table_name='alerts')
    op.create_index('ix_alerts_scope_started_at', 'alerts', ['scope', 'started_at'])
    for table in ('incidents', 'alerts'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('region')
