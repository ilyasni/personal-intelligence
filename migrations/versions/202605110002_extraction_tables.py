"""B-02: topic, mention, interaction, task, processed_event, audit_log

Revision ID: 202605110002
Revises: 202605110001
Create Date: 2026-05-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

TZ = sa.DateTime(timezone=True)

revision: str = "202605110002"
down_revision: Union[str, None] = "202605110001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── topic ─────────────────────────────────────────────────────────────────
    op.create_table(
        "topic",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("slug", name="uq_topic_slug"),
    )

    # ── mention ───────────────────────────────────────────────────────────────
    op.create_table(
        "mention",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chat_id", UUID(as_uuid=True), sa.ForeignKey("chat.id", ondelete="CASCADE"), nullable=False),
        sa.Column("speaker_person_id", UUID(as_uuid=True), sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mentioned_person_id", UUID(as_uuid=True), sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_ref", JSONB(), nullable=False),
        sa.Column("context", sa.Text()),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_mention_speaker", "mention", ["speaker_person_id"])
    op.create_index("idx_mention_mentioned", "mention", ["mentioned_person_id"])

    # ── interaction (partitioned by created_at monthly) ───────────────────────
    # Alembic does not natively emit PARTITION BY — use raw DDL.
    op.execute(
        """
        CREATE TABLE interaction (
          id              UUID NOT NULL DEFAULT gen_random_uuid(),
          chat_id         UUID NOT NULL REFERENCES chat(id) ON DELETE CASCADE,
          window_start    TIMESTAMPTZ NOT NULL,
          window_end      TIMESTAMPTZ NOT NULL,
          participants    UUID[] NOT NULL,
          topics          TEXT[] NOT NULL DEFAULT '{}',
          sentiment       TEXT CHECK (sentiment IN ('positive','negative','neutral','mixed')),
          summary         TEXT NOT NULL,
          tasks           UUID[] NOT NULL DEFAULT '{}',
          source_object_ref TEXT,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
        """
    )
    op.execute(
        """
        CREATE TABLE interaction_2026_05 PARTITION OF interaction
          FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')
        """
    )
    op.execute(
        """
        CREATE TABLE interaction_2026_06 PARTITION OF interaction
          FOR VALUES FROM ('2026-06-01') TO ('2026-07-01')
        """
    )
    op.execute("CREATE INDEX idx_interaction_chat_window ON interaction(chat_id, window_end DESC)")
    op.execute("CREATE INDEX idx_interaction_participants_gin ON interaction USING GIN(participants)")

    # ── task ──────────────────────────────────────────────────────────────────
    op.create_table(
        "task",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("owner_person_id", UUID(as_uuid=True), sa.ForeignKey("person.id", ondelete="SET NULL")),
        sa.Column("counterpart_person_id", UUID(as_uuid=True), sa.ForeignKey("person.id", ondelete="SET NULL")),
        sa.Column("chat_id", UUID(as_uuid=True), sa.ForeignKey("chat.id", ondelete="SET NULL")),
        sa.Column("source_message_ref", JSONB(), nullable=False),
        sa.Column("due_at", TZ),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default="2"),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("evidence", sa.Text()),
        sa.Column("resolved_at", TZ),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('open','done','dropped')", name="ck_task_status"),
        sa.CheckConstraint("priority BETWEEN 1 AND 5", name="ck_task_priority"),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_task_confidence"),
    )
    op.execute("CREATE INDEX idx_task_owner ON task(owner_person_id) WHERE status='open'")
    op.execute("CREATE INDEX idx_task_due ON task(due_at) WHERE status='open'")

    # ── processed_event (partitioned by processed_at monthly) ─────────────────
    op.execute(
        """
        CREATE TABLE processed_event (
          consumer_name   TEXT NOT NULL,
          event_id        TEXT NOT NULL,
          processed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (consumer_name, event_id, processed_at)
        ) PARTITION BY RANGE (processed_at)
        """
    )
    op.execute(
        """
        CREATE TABLE processed_event_2026_05 PARTITION OF processed_event
          FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')
        """
    )
    op.execute(
        """
        CREATE TABLE processed_event_2026_06 PARTITION OF processed_event
          FOR VALUES FROM ('2026-06-01') TO ('2026-07-01')
        """
    )

    # ── audit_log (partitioned by ts monthly) ─────────────────────────────────
    op.execute(
        """
        CREATE TABLE audit_log (
          id              UUID NOT NULL DEFAULT gen_random_uuid(),
          ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
          actor           TEXT NOT NULL,
          action          TEXT NOT NULL,
          target          TEXT,
          request_id      TEXT,
          duration_ms     INT,
          payload         JSONB,
          PRIMARY KEY (id, ts)
        ) PARTITION BY RANGE (ts)
        """
    )
    op.execute(
        """
        CREATE TABLE audit_log_2026_05 PARTITION OF audit_log
          FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')
        """
    )
    op.execute(
        """
        CREATE TABLE audit_log_2026_06 PARTITION OF audit_log
          FOR VALUES FROM ('2026-06-01') TO ('2026-07-01')
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_log CASCADE")
    op.execute("DROP TABLE IF EXISTS processed_event CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_task_due")
    op.execute("DROP INDEX IF EXISTS idx_task_owner")
    op.drop_table("task")
    op.execute("DROP TABLE IF EXISTS interaction CASCADE")
    op.drop_index("idx_mention_mentioned", "mention")
    op.drop_index("idx_mention_speaker", "mention")
    op.drop_table("mention")
    op.drop_table("topic")
