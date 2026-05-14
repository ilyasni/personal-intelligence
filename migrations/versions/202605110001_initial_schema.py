"""Initial schema: connection, chat, person, chat_membership, api_key, setting

Revision ID: 202605110001
Revises: -
Create Date: 2026-05-11

NOTE: id columns use gen_random_uuid() (PostgreSQL built-in).
      UUIDv7 via pg_uuidv7 extension — planned upgrade, tracked in Q-PG-1.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

# DateTime(timezone=True) → TIMESTAMPTZ в PostgreSQL
TZ = sa.DateTime(timezone=True)

revision: str = "202605110001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── connection ────────────────────────────────────────────────────────────
    op.create_table(
        "connection",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("tg_user_id", sa.BigInteger()),
        sa.Column("display_name", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("metadata", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("kind IN ('telethon_userbot','business_bot')", name="ck_connection_kind"),
        sa.CheckConstraint("status IN ('connected','disconnected','error')", name="ck_connection_status"),
    )

    # ── chat ──────────────────────────────────────────────────────────────────
    op.create_table(
        "chat",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("title", sa.Text()),
        sa.Column("is_allowed", sa.Boolean(), nullable=False, server_default="FALSE"),
        sa.Column("member_count", sa.Integer()),
        sa.Column("metadata", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("tg_chat_id", name="uq_chat_tg_chat_id"),
        sa.CheckConstraint(
            "kind IN ('private','group','supergroup','channel')", name="ck_chat_kind"
        ),
    )
    op.create_index(
        "idx_chat_is_allowed",
        "chat",
        ["is_allowed"],
        postgresql_where=sa.text("is_allowed = TRUE"),
    )

    # ── person ────────────────────────────────────────────────────────────────
    op.create_table(
        "person",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tg_user_id", sa.BigInteger(), unique=True),
        sa.Column("username", sa.Text()),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("is_owner", sa.Boolean(), nullable=False, server_default="FALSE"),
        sa.Column("bio", sa.Text()),
        sa.Column("role", sa.Text()),
        sa.Column("organizations", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("topics", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("communication_style", sa.Text()),
        sa.Column("trust_score", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("last_interaction_at", TZ),
        sa.Column("notes", sa.Text()),
        sa.Column("blocked", sa.Boolean(), nullable=False, server_default="FALSE"),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("trust_score BETWEEN 0 AND 1", name="ck_person_trust_score"),
    )
    op.create_index("idx_person_username", "person", ["username"])
    op.create_index("idx_person_last_interaction", "person", ["last_interaction_at"])
    op.create_index("idx_person_topics_gin", "person", ["topics"], postgresql_using="gin")
    op.create_index("idx_person_organizations_gin", "person", ["organizations"], postgresql_using="gin")

    # ── chat_membership ───────────────────────────────────────────────────────
    op.create_table(
        "chat_membership",
        sa.Column("chat_id", UUID(as_uuid=True), sa.ForeignKey("chat.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("person_id", UUID(as_uuid=True), sa.ForeignKey("person.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("joined_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("left_at", TZ),
        sa.Column("role", sa.Text()),
    )

    # ── api_key ───────────────────────────────────────────────────────────────
    op.create_table(
        "api_key",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("scopes", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="TRUE"),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("last_used_at", TZ),
        sa.UniqueConstraint("key_hash", name="uq_api_key_hash"),
    )

    # ── setting ───────────────────────────────────────────────────────────────
    op.create_table(
        "setting",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.text("now()")),
    )

    # Seed default settings
    op.execute(
        """
        INSERT INTO setting (key, value) VALUES
          ('retention.raw_message_days', '90'),
          ('ingestion.backfill_count',   '200'),
          ('llm.mode.entity',            '"local"'),
          ('llm.mode.summarizer',        '"local"')
        """
    )


def downgrade() -> None:
    op.drop_table("setting")
    op.drop_table("api_key")
    op.drop_table("chat_membership")
    op.drop_index("idx_person_organizations_gin", "person")
    op.drop_index("idx_person_topics_gin", "person")
    op.drop_index("idx_person_last_interaction", "person")
    op.drop_index("idx_person_username", "person")
    op.drop_table("person")
    op.drop_index("idx_chat_is_allowed", "chat")
    op.drop_table("chat")
    op.drop_table("connection")
