# ruff: noqa: TC003
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from pil_contracts.base import BaseEvent

STREAM_TELEGRAM_MESSAGE = "events.telegram.message"
STREAM_TELEGRAM_MESSAGE_EDITED = "events.telegram.message_edited"
STREAM_TELEGRAM_MESSAGE_DELETED = "events.telegram.message_deleted"
STREAM_TELEGRAM_CHAT_MEMBER = "events.telegram.chat_member"
STREAM_TELEGRAM_BUSINESS_CONNECTION = "events.telegram.business_connection"
STREAM_TELEGRAM_PREPROCESSED = "events.telegram.preprocessed"

STREAM_ENTITY_FOUND = "events.processing.entity_found"
STREAM_DLQ_ENTITY = "events.dlq.entity_found"
STREAM_PERSON_UPDATED = "events.processing.person_updated"
STREAM_TASK_CREATED = "events.processing.task_created"
STREAM_TASK_RESOLVED = "events.processing.task_resolved"
STREAM_INTERACTION_UPDATED = "events.processing.interaction_updated"
STREAM_DLQ_TASK = "events.dlq.task_extractor"
STREAM_DLQ_SUMMARIZER = "events.dlq.chat_summarizer"

STREAM_AI_ANALYSIS_COMPLETED = "events.ai.analysis_completed"
STREAM_AI_ANALYTICS_SIGNAL = "events.ai.analytics_signal"


class TelegramMessageEvent(BaseEvent):
    stream: Literal["events.telegram.message"] = "events.telegram.message"

    tg_chat_id: int
    tg_message_id: int
    tg_sender_id: int | None = None
    tg_sender_username: str | None = None
    tg_sender_name: str | None = None
    chat_title: str | None = None
    chat_type: Literal["private", "group", "supergroup", "channel"] = "private"
    text: str | None = None
    media_type: str | None = None
    media_mime: str | None = None
    reply_to_message_id: int | None = None
    via_business_bot: bool = False
    is_forwarded: bool = False
    tg_date: datetime | None = None
    raw_s3_key: str | None = None


class TelegramMessageEditedEvent(BaseEvent):
    stream: Literal["events.telegram.message_edited"] = "events.telegram.message_edited"

    tg_chat_id: int
    tg_message_id: int
    edit_date: datetime | None = None
    new_text: str | None = None
    raw_s3_key: str | None = None


class TelegramMessageDeletedEvent(BaseEvent):
    stream: Literal["events.telegram.message_deleted"] = "events.telegram.message_deleted"

    tg_chat_id: int
    tg_message_ids: list[int] = Field(default_factory=list)


class TelegramChatMemberEvent(BaseEvent):
    stream: Literal["events.telegram.chat_member"] = "events.telegram.chat_member"

    tg_chat_id: int
    tg_user_id: int
    action: Literal["join", "leave", "kick"]


class TelegramBusinessConnectionEvent(BaseEvent):
    stream: Literal["events.telegram.business_connection"] = "events.telegram.business_connection"

    connection_id: str
    tg_user_id: int
    is_enabled: bool


class WindowMessagePayload(BaseModel):
    tg_message_id: int
    tg_sender_id: int | None = None
    tg_sender_name: str | None = None
    tg_sender_username: str | None = None
    text: str = ""
    reply_to_message_id: int | None = None
    media_type: str | None = None
    is_forwarded: bool = False
    occurred_at: datetime

    model_config = {"frozen": True}


class MessageFeatureSet(BaseModel):
    chat_type: Literal["private", "group", "supergroup", "channel"] = "private"
    message_count: int = 0
    participant_count: int = 0
    participant_tg_ids: list[int] = Field(default_factory=list)
    author_activity: dict[str, int] = Field(default_factory=dict)
    mention_handles: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    phones: list[str] = Field(default_factory=list)
    keyword_candidates: list[str] = Field(default_factory=list)
    sentiment_hint: Literal["positive", "negative", "neutral", "mixed"] = "neutral"
    attachment_count: int = 0
    forwarded_count: int = 0
    reply_count: int = 0
    median_response_latency_sec: float | None = None
    window_kind: Literal["single", "rolling", "time_window"] = "rolling"

    model_config = {"frozen": True}


class AnalysisEvidence(BaseModel):
    tg_message_id: int
    quote: str | None = None

    model_config = {"frozen": True}


class StructuredClaim(BaseModel):
    kind: Literal["fact", "relationship", "contact", "topic"] = "fact"
    subject: str | None = None
    predicate: str
    object: str | None = None
    claim: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_message_ids: list[int] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class StructuredTask(BaseModel):
    title: str
    description: str | None = None
    priority: int = Field(default=3, ge=1, le=5)
    due_at: datetime | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence_message_ids: list[int] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class AnalyticsSignal(BaseModel):
    kind: Literal[
        "responsiveness",
        "initiative_balance",
        "topic_drift",
        "conversation_health",
        "friction",
        "activity",
    ]
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    summary: str
    evidence_message_ids: list[int] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": True}


class StructuredAnalysisResult(BaseModel):
    source_window_id: str
    summary: str
    topics: list[str] = Field(default_factory=list)
    participants: list[int] = Field(default_factory=list)
    claims: list[StructuredClaim] = Field(default_factory=list)
    tasks: list[StructuredTask] = Field(default_factory=list)
    analytics_signals: list[AnalyticsSignal] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    caveats: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class TelegramPreprocessedEvent(BaseEvent):
    stream: Literal["events.telegram.preprocessed"] = "events.telegram.preprocessed"

    source_event_id: str
    tg_chat_id: int
    source_window_id: str
    messages: list[WindowMessagePayload] = Field(default_factory=list)
    features: MessageFeatureSet


class AIAnalysisCompletedEvent(BaseEvent):
    stream: Literal["events.ai.analysis_completed"] = "events.ai.analysis_completed"

    source_event_id: str
    tg_chat_id: int
    source_window_id: str
    result: StructuredAnalysisResult


class AnalyticsSignalEvent(BaseEvent):
    stream: Literal["events.ai.analytics_signal"] = "events.ai.analytics_signal"

    source_window_id: str
    tg_chat_id: int
    signal: AnalyticsSignal


class EntityCandidate(BaseModel):
    kind: Literal["person", "organization", "topic"]
    surface: str
    normalized: str
    confidence: float
    person_id: str | None = None

    model_config = {"frozen": True}


class EntityFoundEvent(BaseEvent):
    stream: Literal["events.processing.entity_found"] = "events.processing.entity_found"

    source_event_id: str
    tg_chat_id: int
    tg_message_id: int
    tg_sender_id: int | None = None
    language: str = "en"
    entities: list[EntityCandidate] = Field(default_factory=list)


class PersonUpdatedEvent(BaseEvent):
    stream: Literal["events.processing.person_updated"] = "events.processing.person_updated"

    person_id: str
    tg_user_id: int | None = None
    display_name: str
    organizations: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    trust_score: float = 0.5


class TaskCreatedEvent(BaseEvent):
    stream: Literal["events.processing.task_created"] = "events.processing.task_created"

    task_id: str
    title: str
    owner_person_id: str | None = None
    counterpart_person_id: str | None = None
    due_at: datetime | None = None
    source_message_ref: dict[str, int] = Field(default_factory=dict)
    confidence: float = 0.5
    evidence: str | None = None


class TaskResolvedEvent(BaseEvent):
    stream: Literal["events.processing.task_resolved"] = "events.processing.task_resolved"

    task_id: str
    resolution: Literal["done", "dropped"]
    evidence: str | None = None


class InteractionUpdatedEvent(BaseEvent):
    stream: Literal["events.processing.interaction_updated"] = "events.processing.interaction_updated"

    interaction_id: str
    chat_id: str
    window_start: datetime
    window_end: datetime
    participants: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    sentiment: Literal["positive", "negative", "neutral", "mixed"] = "neutral"
    summary: str
    task_ids: list[str] = Field(default_factory=list)
