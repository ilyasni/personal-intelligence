"""Add manual tags to person profiles

Revision ID: 202605150001
Revises: 202605130001
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "202605150001"
down_revision: str | None = "202605130001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "person",
        sa.Column("manual_tags", ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )
    op.create_index("idx_person_manual_tags_gin", "person", ["manual_tags"], postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("idx_person_manual_tags_gin", table_name="person")
    op.drop_column("person", "manual_tags")
