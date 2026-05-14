"""AI runtime reset tables: analysis_window, extracted_fact, analytics_signal

Revision ID: 202605130001
Revises: 202605110002
Create Date: 2026-05-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

TZ = sa.DateTime(timezone=True)

revision: str = "202605130001"
down_revision: Union[str, None] = "202605110002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analysis_window",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("chat_id", UUID(as_uuid=True), sa.ForeignKey("chat.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("source_message_ids", ARRAY(sa.BigInteger()), nullable=False, server_default="{}"),
        sa.Column("participant_tg_ids", ARRAY(sa.BigInteger()), nullable=False, server_default="{}"),
        sa.Column("chat_type", sa.Text(), nullable=False, server_default="private"),
        sa.Column("window_start", TZ, nullable=False),
        sa.Column("window_end", TZ, nullable=False),
        sa.Column("messages", JSONB(), nullable=False, server_default="[]"),
        sa.Column("features", JSONB(), nullable=False, server_default="{}"),
        sa.Column("analysis_payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_analysis_window_confidence"),
        sa.CheckConstraint(
            "chat_type IN ('private','group','supergroup','channel')",
            name="ck_analysis_window_chat_type",
        ),
    )
    op.create_index("idx_analysis_window_chat_end", "analysis_window", ["chat_id", "window_end"])
    op.create_index("idx_analysis_window_tg_chat_end", "analysis_window", ["tg_chat_id", "window_end"])

    op.create_table(
        "extracted_fact",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "window_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analysis_window.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fact_type", sa.Text(), nullable=False),
        sa.Column("subject_text", sa.Text()),
        sa.Column("predicate", sa.Text(), nullable=False),
        sa.Column("object_text", sa.Text()),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=False, server_default="0.5"),
        sa.Column("evidence_message_ids", ARRAY(sa.BigInteger()), nullable=False, server_default="{}"),
        sa.Column("caveats", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("metadata", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name="ck_extracted_fact_confidence"),
    )
    op.create_index("idx_extracted_fact_window", "extracted_fact", ["window_id"])
    op.create_index("idx_extracted_fact_type", "extracted_fact", ["fact_type"])

    op.create_table(
        "analytics_signal",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "window_id",
            UUID(as_uuid=True),
            sa.ForeignKey("analysis_window.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tg_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("signal_kind", sa.Text(), nullable=False),
        sa.Column("score", sa.Numeric(5, 3), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence_message_ids", ARRAY(sa.BigInteger()), nullable=False, server_default="{}"),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="ck_analytics_signal_score"),
    )
    op.create_index("idx_analytics_signal_window", "analytics_signal", ["window_id"])
    op.create_index("idx_analytics_signal_chat", "analytics_signal", ["tg_chat_id", "created_at"])
    op.create_index("idx_analytics_signal_kind", "analytics_signal", ["signal_kind"])


def downgrade() -> None:
    op.drop_index("idx_analytics_signal_kind", table_name="analytics_signal")
    op.drop_index("idx_analytics_signal_chat", table_name="analytics_signal")
    op.drop_index("idx_analytics_signal_window", table_name="analytics_signal")
    op.drop_table("analytics_signal")

    op.drop_index("idx_extracted_fact_type", table_name="extracted_fact")
    op.drop_index("idx_extracted_fact_window", table_name="extracted_fact")
    op.drop_table("extracted_fact")

    op.drop_index("idx_analysis_window_tg_chat_end", table_name="analysis_window")
    op.drop_index("idx_analysis_window_chat_end", table_name="analysis_window")
    op.drop_table("analysis_window")
