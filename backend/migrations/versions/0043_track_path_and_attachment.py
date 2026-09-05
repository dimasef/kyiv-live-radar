"""One source draws a track's path: threats.path_source_id, threat_events.attached_by/frame

`path_source_id` is the source whose sightings form the polyline
(app/domain/path.py): the reply-chain narrator, else the source with the most
events. Backfilled with the same rule so history does not draw the echo
zigzag; NULL stays "every event" for tracks without a source.

`attached_by` records the tracking tier that placed a sighting (NULL for
history); `frame='path'` is the write-through of the parser's stated-route
flag that `movement_stated` is now derived from; `frame_group` is reserved
for sector notation.

Revision ID: 0043
Revises: 0042
Create Date: 2026-09-05T12:00:00

"""
from collections import defaultdict
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0043'
down_revision: Union[str, Sequence[str], None] = '0042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


threats = sa.table(
    'threats',
    sa.column('id', sa.Integer),
    sa.column('path_source_id', sa.Integer),
)
events = sa.table(
    'threat_events',
    sa.column('threat_id', sa.Integer),
    sa.column('source_id', sa.Integer),
    sa.column('source_message_id', sa.BigInteger),
    sa.column('reply_to_message_id', sa.BigInteger),
    sa.column('event_time', sa.DateTime(timezone=True)),
)


def _path_source(rows: list) -> int | None:
    posted = {(r.source_id, r.source_message_id) for r in rows if r.source_message_id is not None}
    replies = [
        r for r in rows
        if r.reply_to_message_id is not None and (r.source_id, r.reply_to_message_id) in posted
    ]
    if replies:
        return max(replies, key=lambda r: r.event_time).source_id
    counts: dict[int, int] = defaultdict(int)
    first_seen: dict = {}
    for r in rows:
        if r.source_id is None:
            continue
        counts[r.source_id] += 1
        if r.source_id not in first_seen or r.event_time < first_seen[r.source_id]:
            first_seen[r.source_id] = r.event_time
    if not counts:
        return None
    return min(counts, key=lambda sid: (-counts[sid], first_seen[sid]))


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('threat_events', sa.Column('attached_by', sa.String(length=10), nullable=True))
    op.add_column('threat_events', sa.Column('frame', sa.String(length=10), nullable=True))
    op.add_column('threat_events', sa.Column('frame_group', sa.Integer(), nullable=True))
    with op.batch_alter_table('threats', schema=None) as batch_op:
        batch_op.add_column(sa.Column('path_source_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_threats_path_source_id_sources', 'sources', ['path_source_id'], ['id'],
        )

    conn = op.get_bind()
    by_threat: dict[int, list] = defaultdict(list)
    for row in conn.execute(sa.select(events)):
        by_threat[row.threat_id].append(row)
    updates = []
    for threat_id, rows in by_threat.items():
        sid = _path_source(rows)
        if sid is not None:
            updates.append({'tid': threat_id, 'sid': sid})
    if updates:
        conn.execute(
            threats.update()
            .where(threats.c.id == sa.bindparam('tid'))
            .values(path_source_id=sa.bindparam('sid')),
            updates,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('threats', schema=None) as batch_op:
        batch_op.drop_constraint('fk_threats_path_source_id_sources', type_='foreignkey')
        batch_op.drop_column('path_source_id')
    with op.batch_alter_table('threat_events', schema=None) as batch_op:
        batch_op.drop_column('frame_group')
        batch_op.drop_column('frame')
        batch_op.drop_column('attached_by')
