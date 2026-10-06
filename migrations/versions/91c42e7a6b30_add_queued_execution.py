"""Add queued lifecycle and transactional task dispatch."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '91c42e7a6b30'
down_revision = '7e910c62b8fa'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('scrape_executions', sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True))
    op.execute('UPDATE scrape_executions SET queued_at = started_at')
    op.alter_column('scrape_executions', 'queued_at', nullable=False)
    op.alter_column('scrape_executions', 'started_at', nullable=True)
    op.add_column('scrape_executions', sa.Column('executor_mode', sa.String(16), nullable=False, server_default='memory'))
    op.add_column('scrape_executions', sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('scrape_executions', sa.Column('attempt_token', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('ix_scrape_executions_queued_at', 'scrape_executions', ['queued_at'])
    op.create_table(
        'scrape_dispatches',
        sa.Column('run_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('scrape_executions.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('generation', sa.Integer(), nullable=False),
        sa.Column('dispatched_generation', sa.Integer(), nullable=False),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
    )
    op.create_index('ix_scrape_dispatches_available_at', 'scrape_dispatches', ['available_at'])


def downgrade() -> None:
    op.drop_table('scrape_dispatches')
    op.execute('UPDATE scrape_executions SET started_at = queued_at WHERE started_at IS NULL')
    op.alter_column('scrape_executions', 'started_at', nullable=False)
    op.drop_index('ix_scrape_executions_queued_at', table_name='scrape_executions')
    for name in ('attempt_token', 'attempts', 'executor_mode', 'queued_at'):
        op.drop_column('scrape_executions', name)
