"""Persist per-source stop requests independently of worker progress."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'ab67d2190f43'
down_revision = 'e936bd154a82'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('scrape_executions', sa.Column('stopped_sources', postgresql.JSONB(),
                                               nullable=False, server_default='[]'))


def downgrade() -> None:
    op.drop_column('scrape_executions', 'stopped_sources')
