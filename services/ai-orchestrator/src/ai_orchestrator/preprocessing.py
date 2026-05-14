# ruff: noqa: TC003
from __future__ import annotations

import math
import re
import statistics
import uuid
from collections import Counter
from datetime import datetime

from pil_contracts import MessageFeatureSet, WindowMessagePayload

_HANDLE_RE = re.compile(r"(?<!\w)@([A-Za-z0-9_]{3,32})")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\-\s()]{7,}\d")
_LINK_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_WORD_RE = re.compile(r"[A-Za-z\u0400-\u04FF0-9][A-Za-z\u0400-\u04FF0-9_-]{2,}")
_POSITIVE_HINTS = {"спасибо", "thanks", "great", "отлично", "супер", "ok", "done"}
_NEGATIVE_HINTS = {"срочно", "urgent", "проблема", "ошибка", "fail", "плохо", "не успеваю"}
_STOPWORDS = {
    "это",
    "как",
    "для",
    "with",
    "that",
    "this",
    "что",
    "если",
    "будет",
    "нужно",
    "please",
    "from",
    "have",
    "just",
    "when",
    "your",
    "about",
    "http",
    "https",
}


def build_window_id() -> str:
    return str(uuid.uuid4())


def needs_rollover(
    *,
    last_occurred_at: datetime,
    occurred_at: datetime,
    strategy: str,
    time_window_minutes: int,
) -> bool:
    if strategy not in {"by_time_window", "hybrid"}:
        return False
    gap_seconds = (occurred_at - last_occurred_at).total_seconds()
    return gap_seconds >= max(60, time_window_minutes * 60)


def compute_message_features(
    messages: list[WindowMessagePayload],
    *,
    chat_type: str,
    window_kind: str = "rolling",
) -> MessageFeatureSet:
    if not messages:
        return MessageFeatureSet(chat_type=chat_type, window_kind=window_kind)

    participant_ids = [msg.tg_sender_id for msg in messages if msg.tg_sender_id is not None]
    unique_participants = sorted(set(participant_ids))
    author_activity = Counter(str(item) for item in participant_ids)

    handles: set[str] = set()
    links: set[str] = set()
    emails: set[str] = set()
    phones: set[str] = set()
    attachment_count = 0
    forwarded_count = 0
    reply_count = 0
    keyword_counter: Counter[str] = Counter()
    positive_hits = 0
    negative_hits = 0

    latencies: list[float] = []
    for index, msg in enumerate(messages):
        text = msg.text or ""
        handles.update(match.group(1) for match in _HANDLE_RE.finditer(text))
        links.update(match.group(0) for match in _LINK_RE.finditer(text))
        emails.update(match.group(0) for match in _EMAIL_RE.finditer(text))
        phones.update(_compact_phone(match.group(0)) for match in _PHONE_RE.finditer(text))
        if msg.media_type:
            attachment_count += 1
        if msg.is_forwarded:
            forwarded_count += 1
        if msg.reply_to_message_id is not None:
            reply_count += 1

        words = [word.casefold() for word in _WORD_RE.findall(text)]
        for word in words:
            if word in _STOPWORDS or word.isdigit():
                continue
            keyword_counter[word] += 1
            if word in _POSITIVE_HINTS:
                positive_hits += 1
            if word in _NEGATIVE_HINTS:
                negative_hits += 1

        if index > 0:
            prev = messages[index - 1]
            if msg.tg_sender_id != prev.tg_sender_id:
                delta = (msg.occurred_at - prev.occurred_at).total_seconds()
                if delta >= 0:
                    latencies.append(delta)

    sentiment_hint = _sentiment_hint(positive_hits=positive_hits, negative_hits=negative_hits)
    keywords = [item for item, _ in keyword_counter.most_common(8)]
    median_latency = statistics.median(latencies) if latencies else None
    if median_latency is not None:
        median_latency = round(float(median_latency), 3)

    return MessageFeatureSet(
        chat_type=chat_type,  # type: ignore[arg-type]
        message_count=len(messages),
        participant_count=len(unique_participants),
        participant_tg_ids=unique_participants,
        author_activity=dict(author_activity),
        mention_handles=sorted(handles),
        links=sorted(links),
        emails=sorted(emails),
        phones=sorted(phones),
        keyword_candidates=keywords,
        sentiment_hint=sentiment_hint,
        attachment_count=attachment_count,
        forwarded_count=forwarded_count,
        reply_count=reply_count,
        median_response_latency_sec=median_latency,
        window_kind=window_kind,  # type: ignore[arg-type]
    )


def summarize_messages(messages: list[WindowMessagePayload], *, limit_chars: int = 360) -> str:
    parts: list[str] = []
    for msg in messages[:6]:
        speaker = msg.tg_sender_name or f"tg:{msg.tg_sender_id}" if msg.tg_sender_id else "unknown"
        parts.append(f"{speaker}: {(msg.text or '').strip()}")
    summary = " | ".join(item for item in parts if item.strip())
    if len(summary) <= limit_chars:
        return summary
    return f"{summary[: limit_chars - 3].rstrip()}..."


def topic_drift_score(messages: list[WindowMessagePayload]) -> float:
    if len(messages) < 2:
        return 0.0
    midpoint = math.ceil(len(messages) / 2)
    first = Counter(_normalized_words(messages[:midpoint]))
    second = Counter(_normalized_words(messages[midpoint:]))
    if not first or not second:
        return 0.0
    overlap = set(first).intersection(second)
    union = set(first).union(second)
    if not union:
        return 0.0
    return round(1.0 - (len(overlap) / len(union)), 3)


def _normalized_words(messages: list[WindowMessagePayload]) -> list[str]:
    words: list[str] = []
    for msg in messages:
        for word in _WORD_RE.findall(msg.text or ""):
            lowered = word.casefold()
            if lowered in _STOPWORDS or lowered.isdigit():
                continue
            words.append(lowered)
    return words


def _compact_phone(value: str) -> str:
    return re.sub(r"\D+", "", value)


def _sentiment_hint(*, positive_hits: int, negative_hits: int) -> str:
    if positive_hits and negative_hits:
        return "mixed"
    if negative_hits:
        return "negative"
    if positive_hits:
        return "positive"
    return "neutral"
