from __future__ import annotations

from dataclasses import dataclass
import structlog

from pil_llm import SummaryPayload, WormsoftConfig, build_wormsoft_client

from chat_summarizer.heuristics import SummaryResult, summarize_window
from chat_summarizer.settings import settings

_SYSTEM_PROMPT = """
You summarize Telegram chat windows for a private memory system.
Return strict JSON only with this shape:
{
  "topics": ["topic 1", "topic 2"],
  "sentiment": "positive|negative|neutral|mixed",
  "summary": "One compact summary no longer than 350 characters.",
  "tasks": ["optional task hint"]
}
Rules:
- Keep topics short and concrete.
- Keep summary factual and compact.
- Do not include markdown.
- If the dialogue is unclear, use "neutral".
""".strip()

log = structlog.get_logger("chat-summarizer.llm")


@dataclass(slots=True)
class LlmWindowMessage:
    tg_message_id: int
    tg_sender_id: int | None
    tg_sender_name: str | None
    text: str
    occurred_at: str


class ChatSummaryEngine:
    def __init__(self, mode: str) -> None:
        self._mode = mode
        self._client = None

        if mode in {"cloud", "hybrid"}:
            config = WormsoftConfig(
                api_base=settings.wormsoft_api_base,
                api_key=settings.wormsoft_api_key,
                model=settings.wormsoft_model_default,
                max_parallel_requests=settings.wormsoft_max_simultaneous_requests,
                min_request_interval_ms=settings.wormsoft_min_request_interval_ms,
                max_retries=settings.wormsoft_max_retries,
            )
            if mode == "cloud" and not config.is_configured:
                raise RuntimeError("chat-summarizer cloud mode requires configured wormsoft credentials")
            if config.is_configured:
                self._client = build_wormsoft_client(config, service_name="chat-summarizer")

    @property
    def mode(self) -> str:
        return self._mode

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()

    async def summarize(self, messages: list[LlmWindowMessage]) -> SummaryResult:
        texts = [message.text for message in messages if message.text.strip()]
        heuristic = summarize_window(texts, max_chars=settings.summarizer_max_summary_chars)
        if self._mode == "local":
            return heuristic
        if self._client is None:
            return heuristic
        try:
            payload = await self._client.complete_summary(
                system_prompt=_SYSTEM_PROMPT,
                user_prompt=_build_user_prompt(messages),
                max_tokens=settings.summarizer_max_tokens_out,
                max_summary_chars=settings.summarizer_max_summary_chars,
                max_tasks=settings.summarizer_max_tasks,
            )
        except Exception as exc:
            if self._mode == "hybrid":
                log.warning("llm_summary_fallback", error=str(exc))
                return heuristic
            raise
        return _summary_from_payload(payload, fallback=heuristic)


def _summary_from_payload(payload: SummaryPayload, *, fallback: SummaryResult) -> SummaryResult:
    summary_text = payload.summary.strip() or fallback.summary
    topics = payload.topics or fallback.topics
    sentiment = payload.sentiment or fallback.sentiment
    return SummaryResult(topics=topics, sentiment=sentiment, summary=summary_text)


def _build_user_prompt(messages: list[LlmWindowMessage]) -> str:
    rendered_messages: list[str] = []
    for index, message in enumerate(messages, start=1):
        author = message.tg_sender_name or (
            f"user:{message.tg_sender_id}" if message.tg_sender_id is not None else "unknown"
        )
        rendered_messages.append(
            f"{index}. [{message.occurred_at}] {author}: {message.text.strip()}"
        )

    return (
        "Summarize this chat window.\n"
        f"Message count: {len(messages)}\n"
        "Messages:\n"
        + "\n".join(rendered_messages)
    )
