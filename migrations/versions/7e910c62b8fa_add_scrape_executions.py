"""Add durable CLI/dashboard execution history."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "7e910c62b8fa"
down_revision = "4b72c4e8a1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scrape_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("results", postgresql.JSONB(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_scrape_executions_status", "scrape_executions", ["status"])
    op.create_index("ix_scrape_executions_started_at", "scrape_executions", ["started_at"])
    op.create_index("ix_jobs_scraped_at_id", "jobs", ["scraped_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_jobs_scraped_at_id", table_name="jobs")
    op.drop_table("scrape_executions")
