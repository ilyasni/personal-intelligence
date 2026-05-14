# ruff: noqa: TC003
from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from openai import AsyncOpenAI

from ai_orchestrator.preprocessing import summarize_messages, topic_drift_score
from ai_orchestrator.settings import settings
from pil_contracts import (
    AnalyticsSignal,
    MessageFeatureSet,
    StructuredAnalysisResult,
    StructuredClaim,
    StructuredTask,
    WindowMessagePayload,
)

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)
_TASK_HINT_RE = re.compile(r"\b(todo|нужно|сделай|please|надо|дедлайн|срок)\b", re.IGNORECASE)


@dataclass(slots=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    max_parallel_requests: int = 1
    min_request_interval_ms: int = 250
    max_retries: int = 2

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip() and self.model.strip())


class OpenAICompatTextClient:
    def __init__(
        self,
        *,
        service_name: str,
        config: ProviderConfig,
        default_headers: Mapping[str, str] | None = None,
    ) -> None:
        self._service_name = service_name
        self._config = config
        self._request_sem = asyncio.Semaphore(max(1, config.max_parallel_requests))
        self._min_request_interval_s = max(0.0, config.min_request_interval_ms / 1000.0)
        self._request_gap_lock = asyncio.Lock()
        self._last_request_started_at = 0.0
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        self._client = AsyncOpenAI(
            base_url=config.base_url.rstrip("/"),
            api_key=config.api_key or "missing",
            http_client=self._http_client,
            default_headers=dict(default_headers or {}),
            max_retries=max(0, config.max_retries),
        )

    @property
    def is_available(self) -> bool:
        return self._config.is_configured

    async def close(self) -> None:
        await self._client.close()

    async def complete_text(self, *, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
        if not self.is_available:
            raise RuntimeError(f"{self._service_name}: provider is not configured")
        await self._acquire_request_slot()
        try:
            raw = await self._client.chat.completions.with_raw_response.create(
                model=self._config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
            )
        finally:
            self._release_request_slot()
        response = raw.parse()
        if not response.choices:
            return ""
        content = response.choices[0].message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                str(item.get("text") or "") for item in content if isinstance(item, dict)
            )
        return str(content or "")

    async def _acquire_request_slot(self) -> None:
        await self._request_sem.acquire()
        try:
            async with self._request_gap_lock:
                now = time.monotonic()
                wait_for = self._min_request_interval_s - (now - self._last_request_started_at)
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                self._last_request_started_at = time.monotonic()
        except Exception:
            self._request_sem.release()
            raise

    def _release_request_slot(self) -> None:
        self._request_sem.release()


class AnalysisRouter:
    def __init__(self) -> None:
        self._wormsoft = OpenAICompatTextClient(
            service_name="ai-orchestrator-wormsoft",
            config=ProviderConfig(
                name="wormsoft",
                base_url=settings.wormsoft_api_base,
                api_key=settings.wormsoft_api_key,
                model=settings.wormsoft_model_default,
                max_parallel_requests=settings.wormsoft_max_simultaneous_requests,
                min_request_interval_ms=settings.wormsoft_min_request_interval_ms,
                max_retries=settings.wormsoft_max_retries,
            ),
        )
        self._polza = OpenAICompatTextClient(
            service_name="ai-orchestrator-polza",
            config=ProviderConfig(
                name="polza",
                base_url=settings.polza_api_base,
                api_key=settings.polza_api_key,
                model=settings.polza_model_default,
                max_parallel_requests=settings.polza_max_simultaneous_requests,
                min_request_interval_ms=settings.polza_min_request_interval_ms,
                max_retries=settings.polza_max_retries,
            ),
        )

    async def close(self) -> None:
        await self._wormsoft.close()
        await self._polza.close()

    async def analyze(
        self,
        *,
        source_window_id: str,
        messages: list[WindowMessagePayload],
        features: MessageFeatureSet,
        canonical_context: dict[str, Any],
    ) -> StructuredAnalysisResult:
        for client in (self._wormsoft, self._polza):
            if not client.is_available:
                continue
            try:
                raw = await client.complete_text(
                    system_prompt=_system_prompt(),
                    user_prompt=_user_prompt(
                        source_window_id=source_window_id,
                        messages=messages,
                        features=features,
                        canonical_context=canonical_context,
                    ),
                    max_tokens=settings.analysis_max_tokens_out,
                )
                return _parse_analysis_payload(
                    raw,
                    source_window_id=source_window_id,
                    messages=messages,
                    features=features,
                )
            except Exception:
                continue
        return _heuristic_analysis(
            source_window_id=source_window_id,
            messages=messages,
            features=features,
        )


def _system_prompt() -> str:
    return (
        "You analyze Telegram conversation windows for a personal intelligence service. "
        "Return strict JSON only. Never assign personality traits, diagnoses, clinical labels, "
        "or speculative psychology. Focus on factual claims, tasks, cautious communication "
        "signals, and evidence-backed summaries. Every claim, task, and analytics signal must "
        "reference real message ids from the window. If evidence is weak, add caveats instead of "
        "guessing."
    )


def _user_prompt(
    *,
    source_window_id: str,
    messages: list[WindowMessagePayload],
    features: MessageFeatureSet,
    canonical_context: dict[str, Any],
) -> str:
    serialized_messages = [
        {
            "tg_message_id": msg.tg_message_id,
            "tg_sender_id": msg.tg_sender_id,
            "tg_sender_name": msg.tg_sender_name,
            "text": msg.text,
            "reply_to_message_id": msg.reply_to_message_id,
            "occurred_at": msg.occurred_at.isoformat(),
        }
        for msg in messages
    ]
    schema = {
        "source_window_id": source_window_id,
        "summary": "short grounded summary",
        "topics": ["topic"],
        "participants": [123],
        "claims": [
            {
                "kind": "fact|relationship|contact|topic",
                "subject": "optional",
                "predicate": "required",
                "object": "optional",
                "claim": "required",
                "confidence": 0.0,
                "evidence_message_ids": [1],
                "caveats": ["optional"],
            }
        ],
        "tasks": [
            {
                "title": "required",
                "description": "optional",
                "priority": 3,
                "due_at": None,
                "confidence": 0.0,
                "evidence_message_ids": [1],
                "caveats": ["optional"],
            }
        ],
        "analytics_signals": [
            {
                "kind": "responsiveness|initiative_balance|topic_drift|conversation_health|friction|activity",
                "score": 0.0,
                "summary": "required",
                "evidence_message_ids": [1],
                "payload": {},
            }
        ],
        "confidence": 0.0,
        "caveats": ["optional"],
    }
    return json.dumps(
        {
            "instruction": (
                "Produce evidence-backed JSON. Do not infer mental health, personality types, "
                "clinical conditions, or hidden intentions. Use only evidence from messages and "
                "the explicit preprocessing features."
            ),
            "output_schema": schema,
            "canonical_context": canonical_context,
            "features": features.model_dump(mode="json"),
            "messages": serialized_messages,
        },
        ensure_ascii=False,
        default=str,
    )


def _parse_analysis_payload(
    raw_text: str,
    *,
    source_window_id: str,
    messages: list[WindowMessagePayload],
    features: MessageFeatureSet,
) -> StructuredAnalysisResult:
    match = _JSON_RE.search(raw_text or "")
    if not match:
        return _heuristic_analysis(
            source_window_id=source_window_id,
            messages=messages,
            features=features,
        )
    data = json.loads(match.group(0))
    data["source_window_id"] = source_window_id
    result = StructuredAnalysisResult.model_validate(data)
    return _sanitize_result(result, messages=messages, features=features)


def _sanitize_result(
    result: StructuredAnalysisResult,
    *,
    messages: list[WindowMessagePayload],
    features: MessageFeatureSet,
) -> StructuredAnalysisResult:
    valid_ids = {msg.tg_message_id for msg in messages}
    safe_claims: list[StructuredClaim] = []
    for claim in result.claims:
        evidence_ids = [item for item in claim.evidence_message_ids if item in valid_ids]
        if not evidence_ids:
            continue
        safe_claims.append(
            claim.model_copy(
                update={
                    "confidence": min(max(float(claim.confidence), 0.0), 1.0),
                    "evidence_message_ids": evidence_ids,
                }
            )
        )

    safe_tasks: list[StructuredTask] = []
    for task in result.tasks:
        evidence_ids = [item for item in task.evidence_message_ids if item in valid_ids]
        if not evidence_ids:
            continue
        safe_tasks.append(
            task.model_copy(
                update={
                    "priority": min(max(int(task.priority), 1), 5),
                    "confidence": min(max(float(task.confidence), 0.0), 1.0),
                    "evidence_message_ids": evidence_ids,
                }
            )
        )

    safe_signals: list[AnalyticsSignal] = []
    for signal in result.analytics_signals:
        evidence_ids = [item for item in signal.evidence_message_ids if item in valid_ids]
        safe_signals.append(
            signal.model_copy(
                update={
                    "score": min(max(float(signal.score), 0.0), 1.0),
                    "evidence_message_ids": evidence_ids,
                }
            )
        )

    if not safe_signals:
        safe_signals = _heuristic_signals(messages=messages, features=features)

    return result.model_copy(
        update={
            "claims": safe_claims,
            "tasks": safe_tasks,
            "analytics_signals": safe_signals,
            "confidence": min(max(float(result.confidence), 0.0), 1.0),
        }
    )


def _heuristic_analysis(
    *,
    source_window_id: str,
    messages: list[WindowMessagePayload],
    features: MessageFeatureSet,
) -> StructuredAnalysisResult:
    claims: list[StructuredClaim] = []
    first_message_id = messages[0].tg_message_id if messages else 0
    for email in features.emails:
        claims.append(
            StructuredClaim(
                kind="contact",
                predicate="shared_email",
                object=email,
                claim=f"An email address was shared: {email}.",
                confidence=0.72,
                evidence_message_ids=[first_message_id],
                caveats=["Extracted with deterministic preprocessing."],
            )
        )
    for phone in features.phones:
        claims.append(
            StructuredClaim(
                kind="contact",
                predicate="shared_phone",
                object=phone,
                claim=f"A phone number was shared: {phone}.",
                confidence=0.7,
                evidence_message_ids=[first_message_id],
                caveats=["Extracted with deterministic preprocessing."],
            )
        )
    for link in features.links[:3]:
        claims.append(
            StructuredClaim(
                kind="fact",
                predicate="shared_link",
                object=link,
                claim=f"A link was shared: {link}.",
                confidence=0.68,
                evidence_message_ids=[first_message_id],
                caveats=["Link shared in the current window."],
            )
        )

    tasks: list[StructuredTask] = []
    for msg in messages:
        if _TASK_HINT_RE.search(msg.text or ""):
            tasks.append(
                StructuredTask(
                    title=(msg.text or "").strip()[:120] or "Follow up",
                    priority=3,
                    confidence=0.55,
                    evidence_message_ids=[msg.tg_message_id],
                    caveats=["Heuristic task extraction."],
                )
            )
            if len(tasks) >= 3:
                break

    return StructuredAnalysisResult(
        source_window_id=source_window_id,
        summary=summarize_messages(messages),
        topics=features.keyword_candidates[:5],
        participants=features.participant_tg_ids,
        claims=claims,
        tasks=tasks,
        analytics_signals=_heuristic_signals(messages=messages, features=features),
        confidence=0.58,
        caveats=["Generated without remote LLM output."],
    )


def _heuristic_signals(
    *,
    messages: list[WindowMessagePayload],
    features: MessageFeatureSet,
) -> list[AnalyticsSignal]:
    evidence = [msg.tg_message_id for msg in messages[:3]]
    latency = features.median_response_latency_sec or 0.0
    responsiveness = 1.0 if latency <= 0 else max(0.0, min(1.0, 1.0 - min(latency, 7200.0) / 7200.0))
    activity = max(0.0, min(1.0, features.message_count / 20.0))
    if features.author_activity:
        counts = list(features.author_activity.values())
        dominant = max(counts)
        initiative_balance = 1.0 - min(1.0, (dominant / max(sum(counts), 1)) - 0.5)
    else:
        initiative_balance = 0.0

    drift = topic_drift_score(messages)
    friction = 0.7 if features.sentiment_hint == "negative" else 0.5 if features.sentiment_hint == "mixed" else 0.2
    health = max(0.0, min(1.0, (responsiveness + initiative_balance + (1.0 - friction)) / 3.0))

    return [
        AnalyticsSignal(
            kind="responsiveness",
            score=round(responsiveness, 3),
            summary="Estimated from message-to-message response gaps.",
            evidence_message_ids=evidence,
            payload={"median_response_latency_sec": latency},
        ),
        AnalyticsSignal(
            kind="initiative_balance",
            score=round(max(initiative_balance, 0.0), 3),
            summary="Estimated from sender activity distribution in the window.",
            evidence_message_ids=evidence,
            payload={"author_activity": features.author_activity},
        ),
        AnalyticsSignal(
            kind="topic_drift",
            score=round(drift, 3),
            summary="Estimated from keyword overlap between the first and second half of the window.",
            evidence_message_ids=evidence,
            payload={"keyword_candidates": features.keyword_candidates},
        ),
        AnalyticsSignal(
            kind="friction",
            score=round(min(max(friction, 0.0), 1.0), 3),
            summary="Estimated from tone and negative urgency hints.",
            evidence_message_ids=evidence,
            payload={"sentiment_hint": features.sentiment_hint},
        ),
        AnalyticsSignal(
            kind="conversation_health",
            score=round(health, 3),
            summary="Composite signal from responsiveness, initiative balance, and friction.",
            evidence_message_ids=evidence,
            payload={},
        ),
        AnalyticsSignal(
            kind="activity",
            score=round(activity, 3),
            summary="Estimated from message count within the window.",
            evidence_message_ids=evidence,
            payload={"message_count": features.message_count},
        ),
    ]
