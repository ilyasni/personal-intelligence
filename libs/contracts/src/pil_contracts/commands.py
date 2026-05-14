# ruff: noqa: TC001
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from pil_contracts.base import BaseCommand
from pil_contracts.events import MessageFeatureSet, StructuredAnalysisResult, WindowMessagePayload

STREAM_SYSTEM_COMMAND = "system.command"
STREAM_AI_PROJECTION_COMMAND = "events.ai.projection_command"
STREAM_AI_EMBEDDING_REQUESTED = "events.ai.embedding_requested"
STREAM_AI_REPROCESS_WINDOW = "events.ai.reprocess_window"


class BackfillChatCommand(BaseCommand):
    kind: Literal["backfill_chat"] = "backfill_chat"
    chat_id: int
    count: int = 200


class ProjectionCommand(BaseCommand):
    kind: Literal["project_analysis"] = "project_analysis"
    source_window_id: str
    source_event_id: str
    tg_chat_id: int
    messages: list[WindowMessagePayload] = Field(default_factory=list)
    features: MessageFeatureSet
    result: StructuredAnalysisResult
    trace_id: str | None = None


class EmbeddingProfile(BaseModel):
    provider: Literal["wormsoft", "polza"] = "wormsoft"
    model: str
    alias_name: str = "pil_memory_active"
    collection_name: str | None = None
    dimension: int | None = None

    model_config = {"frozen": True}


class EmbeddingJob(BaseCommand):
    kind: Literal["embed_window"] = "embed_window"
    source_window_id: str
    tg_chat_id: int
    analysis_window_id: str
    person_ids: list[str] = Field(default_factory=list)
    topic_tags: list[str] = Field(default_factory=list)
    narrative_text: str
    profile_provider: Literal["wormsoft", "polza"] = "wormsoft"
    profile_model: str
    profile_alias: str = "pil_memory_active"
    trace_id: str | None = None


class ReprocessWindowCommand(BaseCommand):
    kind: Literal["reprocess_window"] = "reprocess_window"
    window_id: str
    trace_id: str | None = None
