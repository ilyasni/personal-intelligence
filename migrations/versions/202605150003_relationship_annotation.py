"""Add canonical relationship_annotation table.

Revision ID: 202605150003
Revises: 202605150002
Create Date: 2026-05-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

TZ = sa.DateTime(timezone=True)

revision: str = "202605150003"
down_revision: str | None = "202605150002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "relationship_annotation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "owner_profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("owner_profile.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("person_id", UUID(as_uuid=True), sa.ForeignKey("person.id", ondelete="CASCADE")),
        sa.Column("chat_id", UUID(as_uuid=True), sa.ForeignKey("chat.id", ondelete="CASCADE")),
        sa.Column("labels", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "(CASE WHEN person_id IS NOT NULL THEN 1 ELSE 0 END) + "
            "(CASE WHEN chat_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_relationship_annotation_exactly_one_target",
        ),
        sa.UniqueConstraint("owner_profile_id", "person_id", name="uq_relationship_annotation_owner_person"),
        sa.UniqueConstraint("owner_profile_id", "chat_id", name="uq_relationship_annotation_owner_chat"),
    )
    op.create_index("idx_relationship_annotation_person_id", "relationship_annotation", ["person_id"])
    op.create_index("idx_relationship_annotation_chat_id", "relationship_annotation", ["chat_id"])
    op.create_index(
        "idx_relationship_annotation_labels_gin",
        "relationship_annotation",
        ["labels"],
        postgresql_using="gin",
    )

    op.execute(
        """
        INSERT INTO relationship_annotation (owner_profile_id, person_id, labels, note)
        SELECT
            owner.id,
            person.id,
            person.manual_tags,
            person.notes
        FROM (
            SELECT id
            FROM owner_profile
            ORDER BY updated_at DESC
            LIMIT 1
        ) AS owner
        JOIN person ON person.is_owner = FALSE
        WHERE cardinality(person.manual_tags) > 0 OR person.notes IS NOT NULL
        ON CONFLICT (owner_profile_id, person_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("idx_relationship_annotation_labels_gin", "relationship_annotation")
    op.drop_index("idx_relationship_annotation_chat_id", "relationship_annotation")
    op.drop_index("idx_relationship_annotation_person_id", "relationship_annotation")
    op.drop_table("relationship_annotation")
