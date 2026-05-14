from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
from openai import AsyncOpenAI

Sentiment = Literal["positive", "negative", "neutral", "mixed"]

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)
_VALID_SENTIMENTS: set[str] = {"positive", "negative", "neutral", "mixed"}


@dataclass(slots=True, frozen=True)
class SummaryPayload:
    topics: list[str] = field(default_factory=list)
    sentiment: Sentiment = "neutral"
    summary: str = ""
    tasks: list[str] = field(default_factory=list)


@dataclass(slots=True, frozen=True)
class WormsoftConfig:
    api_base: str = "https://ai.wormsoft.ru/api/gpt"
    api_key: str = ""
    model: str = "wormsoft/agent/medium"
    max_parallel_requests: int = 1
    min_request_interval_ms: int = 250
    timeout_seconds: float = 60.0
    connect_timeout_seconds: float = 10.0
    max_connections: int = 10
    max_keepalive_connections: int = 5
    max_retries: int = 2

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.strip() and self.model.strip())


def extract_message_text(message_content: Any) -> str:
    if isinstance(message_content, str):
        return message_content
    if isinstance(message_content, list):
        parts: list[str] = []
        for item in message_content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "\n".join(part for part in parts if part)
    return str(message_content or "")


def _normalize_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for item in value:
        text = " ".join(str(item or "").split()).strip(" ,.;:-")
        if not text:
            continue
        lowered = text.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(text[:120])
        if len(normalized) >= limit:
            break
    return normalized


def _truncate(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 3].rstrip()}..."


def parse_summary_payload(
    raw_text: str,
    *,
    max_summary_chars: int = 350,
    max_topics: int = 5,
    max_tasks: int = 5,
) -> SummaryPayload:
    text = str(raw_text or "").strip()
    data: dict[str, Any] = {}

    match = _JSON_BLOCK_RE.search(text)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            data = {}

    if not data:
        return SummaryPayload(summary=_truncate(text or "No summary generated.", max_summary_chars))

    topics = _normalize_list(data.get("topics"), limit=max_topics)
    tasks = _normalize_list(data.get("tasks"), limit=max_tasks)
    sentiment = str(data.get("sentiment") or "neutral").strip().lower()
    if sentiment not in _VALID_SENTIMENTS:
        sentiment = "neutral"

    summary = _truncate(
        str(data.get("summary") or text or "No summary generated."),
        max_summary_chars,
    )
    if not summary:
        summary = "No summary generated."

    return SummaryPayload(
        topics=topics,
        sentiment=sentiment,  # type: ignore[arg-type]
        summary=summary,
        tasks=tasks,
    )


class OpenAICompatChatClient:
    """Long-lived AsyncOpenAI wrapper for OpenAI-compatible text providers."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        default_model: str,
        service_name: str,
        max_parallel_requests: int = 1,
        min_request_interval_ms: int = 250,
        timeout_seconds: float = 60.0,
        connect_timeout_seconds: float = 10.0,
        max_connections: int = 10,
        max_keepalive_connections: int = 5,
        max_retries: int = 2,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self._service_name = service_name
        self._api_key = str(api_key or "").strip()
        self._default_model = str(default_model or "").strip()
        self._request_sem = asyncio.Semaphore(max(1, int(max_parallel_requests or 1)))
        self._min_request_interval_s = max(0.0, float(min_request_interval_ms or 0) / 1000.0)
        self._request_gap_lock = asyncio.Lock()
        self._last_request_started_at = 0.0
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds, connect=connect_timeout_seconds),
            limits=httpx.Limits(
                max_connections=max(1, int(max_connections or 1)),
                max_keepalive_connections=max(1, int(max_keepalive_connections or 1)),
                keepalive_expiry=30.0,
            ),
        )
        self._client = AsyncOpenAI(
            base_url=str(base_url or "").rstrip("/"),
            api_key=self._api_key or "missing",
            http_client=self._http_client,
            default_headers=dict(default_headers or {}),
            max_retries=max(0, int(max_retries or 0)),
        )

    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def is_available(self) -> bool:
        return bool(self._api_key and self._default_model)

    async def close(self) -> None:
        await self._client.close()

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

    async def complete_summary(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model_override: str | None = None,
        max_tokens: int = 400,
        max_summary_chars: int = 350,
        max_tasks: int = 5,
    ) -> SummaryPayload:
        if not self.is_available:
            raise RuntimeError(f"{self._service_name}: llm client is not configured")

        model = str(model_override or self._default_model).strip()
        if not model:
            raise ValueError(f"{self._service_name}: model is empty")

        await self._acquire_request_slot()
        try:
            raw = await self._client.chat.completions.with_raw_response.create(
                model=model,
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
        content = ""
        if response.choices:
            content = extract_message_text(response.choices[0].message.content)
        return parse_summary_payload(
            content,
            max_summary_chars=max_summary_chars,
            max_tasks=max_tasks,
        )


def build_wormsoft_client(
    config: WormsoftConfig,
    *,
    service_name: str,
) -> OpenAICompatChatClient:
    return OpenAICompatChatClient(
        base_url=config.api_base,
        api_key=config.api_key,
        default_model=config.model,
        service_name=service_name,
        max_parallel_requests=config.max_parallel_requests,
        min_request_interval_ms=config.min_request_interval_ms,
        timeout_seconds=config.timeout_seconds,
        connect_timeout_seconds=config.connect_timeout_seconds,
        max_connections=config.max_connections,
        max_keepalive_connections=config.max_keepalive_connections,
        max_retries=config.max_retries,
    )
