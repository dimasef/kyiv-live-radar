"""Region-exclusive gazetteer entries

`districts.region_only` marks a place matchable ONLY by a channel reporting from
its own region. Every existing row is False, which is exactly what they were
implicitly, so this is behaviour-preserving until the gazetteer sets it.

Why it is needed: `region` alone cannot separate a name both oblasts use for
their OWN landmark. «ТЕЦ» is 42 Kyiv mentions (ТЕЦ-5/ТЕЦ-6, Видубичі) and 5
Chernihiv ones in the stored corpus, and `prefer_region` only breaks TIES — a
lone Chernihiv entry faces no tie and would have claimed all 47. Same for
«вокзал», «летовище», «очисні».

Revision ID: 0031
Revises: 0030
Create Date: 2026-08-21T20:45:00

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0031'
down_revision: Union[str, Sequence[str], None] = '0030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('region_only', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('districts', schema=None) as batch_op:
        batch_op.drop_column('region_only')
