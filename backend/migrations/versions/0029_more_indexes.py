"""two indexes 0020's own rule should have caught

0020 set the rule: "one index per column that appears in a WHERE or ORDER BY at
least twice". Two columns met it and were missed.

  * notices.source_message_id — api/raw_query.py filters on it three times (a
    correlated EXISTS evaluated per raw_messages row on the /raw list) and
    api/coverage.py once. Its sibling notices.source_id was indexed in 0020;
    this one wasn't.
  * threats.status — domain/tracking.py::find_recent_impact selects on it for
    every incoming impact message, once per named district. 0020 indexed the
    composite (closed_at, closed_reason) for /threats/active, which does not
    serve a status lookup.

Purely additive: no table or column changes, safe to run on a live DB.

Revision ID: 0029
Revises: 0028
Create Date: 2026-08-21T12:00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0029'
down_revision: Union[str, Sequence[str], None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, table, [columns]) — mirrored by index=True on the matching
# mapped_column in app/models.py; keep the two in step.
_INDEXES: list[tuple[str, str, list[str]]] = [
    ('ix_notices_source_message_id', 'notices', ['source_message_id']),
    ('ix_threats_status', 'threats', ['status']),
]


def upgrade() -> None:
    """Upgrade schema."""
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    """Downgrade schema."""
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
