"""hot-path indexes

Until now the schema carried exactly four indexes, three of them incidental
(the users-email unique, two on threat_analyses). Every other lookup — the
threat_id JOIN behind every serializer, the event_time/created_at ordering
behind the feed, the closed_at filter behind /threats/active — was a sequential
scan. Harmless at MVP row counts, but prod is Postgres and raw_messages already
passed 4k rows with a single user, so this closes the gap before it bites.

Chosen from the real query patterns in app/ (`grep order_by/where`), not
speculatively:
  * one index per column that appears in a WHERE or ORDER BY at least twice;
  * composites where the pair is always queried together (threats' active
    filter, alerts' scope+time), which also serve prefix lookups on their
    first column — so no separate single-column index for those;
  * nothing on columns already covered by an existing unique constraint's
    implicit index (raw_messages.source_id sits under
    uq_raw_message_source_msgid; friendships.requester_id under
    uq_friendship_pair — only addressee_id, the uncovered second column,
    gets its own).

Purely additive: no table or column changes, safe to run on a live DB.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-01T12:00:00

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '0020'
down_revision: Union[str, Sequence[str], None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, table, [columns]) — mirrored by index=True on the matching
# mapped_column in app/models.py; keep the two in step.
_INDEXES: list[tuple[str, str, list[str]]] = [
    # Every threat serializer joins events to their track and orders by time.
    ('ix_threat_events_threat_id', 'threat_events', ['threat_id']),
    ('ix_threat_events_event_time', 'threat_events', ['event_time']),
    # Several events from ONE channel message are grouped into one feed card.
    ('ix_threat_events_source_message_id', 'threat_events', ['source_message_id']),
    ('ix_threat_events_source_id', 'threat_events', ['source_id']),
    # /threats/active — the hottest query: open tracks, admin-dismissed excluded.
    ('ix_threats_closed_at_reason', 'threats', ['closed_at', 'closed_reason']),
    ('ix_threats_created_at', 'threats', ['created_at']),
    ('ix_threats_incident_id', 'threats', ['incident_id']),
    ('ix_incidents_started_at', 'incidents', ['started_at']),
    ('ix_incidents_ended_at', 'incidents', ['ended_at']),
    ('ix_incidents_alert_id', 'incidents', ['alert_id']),
    # Alerts are always filtered by scope first, then ordered by time.
    ('ix_alerts_scope_started_at', 'alerts', ['scope', 'started_at']),
    ('ix_alerts_ended_at', 'alerts', ['ended_at']),
    ('ix_raw_messages_event_time', 'raw_messages', ['event_time']),
    # Rare-True flag (~5% of messages) — the /raw LLM filter selects on it.
    ('ix_raw_messages_llm_attempted', 'raw_messages', ['llm_attempted']),
    ('ix_threat_axes_expires_at', 'threat_axes', ['expires_at']),
    ('ix_notices_event_time', 'notices', ['event_time']),
    ('ix_notices_source_id', 'notices', ['source_id']),
    # uq_friendship_pair already covers requester_id; the reverse side doesn't.
    ('ix_friendships_addressee_id', 'friendships', ['addressee_id']),
    ('ix_push_subscriptions_user_id', 'push_subscriptions', ['user_id']),
    ('ix_oauth_identities_user_id', 'oauth_identities', ['user_id']),
]


def upgrade() -> None:
    """Upgrade schema."""
    for name, table, columns in _INDEXES:
        op.create_index(name, table, columns)


def downgrade() -> None:
    """Downgrade schema."""
    for name, table, _columns in reversed(_INDEXES):
        op.drop_index(name, table_name=table)
