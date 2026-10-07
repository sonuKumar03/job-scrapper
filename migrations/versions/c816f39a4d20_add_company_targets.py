"""Separate company identities and runtime ATS targets."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'c816f39a4d20'
down_revision = '91c42e7a6b30'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'companies',
        sa.Column('company_key', sa.String(256), primary_key=True),
        sa.Column('company_name', sa.Text(), nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('directory_status', sa.String(32), nullable=False),
    )
    op.create_table(
        'company_targets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_key', sa.String(256), sa.ForeignKey('companies.company_key', ondelete='CASCADE'), nullable=False),
        sa.Column('provider', sa.String(32), nullable=False),
        sa.Column('account_key', sa.String(256), nullable=False),
        sa.Column('board_url', sa.Text(), nullable=False),
        sa.Column('verification_status', sa.String(32), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('provenance', sa.Text(), nullable=False),
        sa.Column('checked_at', sa.DateTime(timezone=True)),
        sa.Column('succeeded_at', sa.DateTime(timezone=True)),
        sa.Column('last_error', sa.Text()),
        sa.UniqueConstraint('provider', 'account_key', name='uq_company_targets_provider_account'),
        sa.CheckConstraint("provider IN ('greenhouse', 'lever', 'ashby', 'workday', 'workable')", name='ck_company_targets_provider'),
        sa.CheckConstraint("verification_status IN ('supported', 'needs_review', 'unsupported', 'unavailable', 'blocked', 'unverified')", name='ck_company_targets_status'),
    )
    op.create_index('ix_company_targets_provider_enabled', 'company_targets', ['provider', 'enabled'])


def downgrade() -> None:
    op.drop_table('company_targets')
    op.drop_table('companies')
