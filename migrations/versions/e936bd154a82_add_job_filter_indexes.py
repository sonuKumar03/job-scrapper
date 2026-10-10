"""Index substring search and selected job attributes without rewriting data."""

from alembic import op

revision = 'e936bd154a82'
down_revision = 'c816f39a4d20'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')
    op.execute('CREATE INDEX ix_jobs_title_trgm ON jobs USING gin (title gin_trgm_ops)')
    op.execute('CREATE INDEX ix_jobs_company_trgm ON jobs USING gin (company_name gin_trgm_ops)')
    for field in ('work_arrangement', 'employment_type'):
        op.execute(f"CREATE INDEX ix_jobs_{field} ON jobs ((coalesce(nullif(attributes ->> '{field}', ''), 'unknown')))")
    for bound in ('min', 'max'):
        field = f'experience_years_{bound}'
        op.execute(f"CREATE INDEX ix_jobs_experience_{bound} ON jobs ((CASE WHEN jsonb_typeof(attributes -> '{field}') = 'number' THEN (attributes ->> '{field}')::numeric END))")


def downgrade():
    for name in ('title_trgm', 'company_trgm', 'work_arrangement', 'employment_type', 'experience_min', 'experience_max'):
        op.drop_index(f'ix_jobs_{name}', table_name='jobs')
