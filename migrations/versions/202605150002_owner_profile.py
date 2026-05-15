"""Add canonical owner_profile table.

Revision ID: 202605150002
Revises: 202605150001
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

TZ = sa.DateTime(timezone=True)

revision: str = "202605150002"
down_revision: str | None = "202605150001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "owner_profile",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("backing_person_id", UUID(as_uuid=True), sa.ForeignKey("person.id", ondelete="SET NULL")),
        sa.Column("tg_user_id", sa.BigInteger(), unique=True),
        sa.Column("username", sa.Text()),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("preferred_language", sa.Text(), nullable=False, server_default="ru"),
        sa.Column("context_tags", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("profile_notes", sa.Text()),
        sa.Column("last_interaction_at", TZ),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("backing_person_id", name="uq_owner_profile_backing_person_id"),
        sa.CheckConstraint("preferred_language IN ('ru','en')", name="ck_owner_profile_language"),
    )
    op.create_index("idx_owner_profile_username", "owner_profile", ["username"])
    op.create_index(
        "idx_owner_profile_context_tags_gin",
        "owner_profile",
        ["context_tags"],
        postgresql_using="gin",
    )

    op.execute(
        """
        INSERT INTO owner_profile (
            backing_person_id,
            tg_user_id,
            username,
            display_name,
            preferred_language,
            context_tags,
            profile_notes,
            last_interaction_at
        )
        SELECT
            id,
            tg_user_id,
            username,
            display_name,
            'ru',
            '{}'::text[],
            notes,
            last_interaction_at
        FROM person
        WHERE is_owner = TRUE
        ORDER BY updated_at DESC
        LIMIT 1
        ON CONFLICT (backing_person_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("idx_owner_profile_context_tags_gin", "owner_profile")
    op.drop_index("idx_owner_profile_username", "owner_profile")
    op.drop_table("owner_profile")
