"""allow repeated content hashes across source identities

Revision ID: 4b72c4e8a1d3
Revises: 834f81899107
Create Date: 2026-10-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4b72c4e8a1d3"
down_revision: Union[str, Sequence[str], None] = "834f81899107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_jobs_content_hash", table_name="jobs")
    op.create_index("ix_jobs_content_hash", "jobs", ["content_hash"], unique=False)


def downgrade() -> None:
    duplicates = op.get_bind().execute(
        sa.text("SELECT 1 FROM jobs GROUP BY content_hash HAVING count(*) > 1 LIMIT 1")
    ).first()
    if duplicates:
        raise RuntimeError("Cannot restore unique content hashes while duplicate jobs exist")
    op.drop_index("ix_jobs_content_hash", table_name="jobs")
    op.create_index("ix_jobs_content_hash", "jobs", ["content_hash"], unique=True)
