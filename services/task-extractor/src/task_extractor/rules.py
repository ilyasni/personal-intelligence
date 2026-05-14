import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

try:
    from dateparser.search import search_dates
except ImportError:  # pragma: no cover - optional in thin local environments
    search_dates = None

PROMISE_PATTERNS = (
    r"\bсделаю\b",
    r"\bпришлю\b",
    r"\bотправлю\b",
    r"\bзакину\b",
    r"\bсогласую\b",
    r"\bуточню\b",
    r"\bподготовлю\b",
    r"\bдобью\b",
    r"\bдоделаю\b",
    r"\bпереведу\b",
    r"\b(?:i|i[' ]?ll)\s+(?:will\s+)?(?:send|prepare|check|share|update)\b",
    r"\bwill\s+(?:send|prepare|check|share|update)\b",
    r"\blet me check\b",
)

REQUEST_PATTERNS = (
    r"\b(?:нужно|надо)\s+(?:сделать|отправить|прислать|проверить|подготовить|согласовать|сканировать|перевести|написать)\b",
    r"\bотправь(?:те)?(?:\s+мне)?\b",
    r"\bпришли(?:те)?(?:\s+мне)?\b",
    r"\bнапиш(?:и|ешь|ите)\b",
    r"\bпроверь(?:те)?\b",
    r"\bскинь(?:те)?\b",
    r"\bсможешь\b",
    r"\bcan you\b",
    r"\bcould you\b",
    r"\bplease\s+(?:send|share|check|review|prepare)\b",
    r"\bsend me\b",
    r"\bneed to\s+(?:send|share|check|review|prepare)\b",
)

RESOLUTION_PATTERNS = (
    r"\bсделал\b",
    r"\bсделано\b",
    r"\bготово\b",
    r"\bготов\b",
    r"\bвот ссылка\b",
    r"\bdone\b",
    r"\bcompleted\b",
    r"\bsent\b",
)

_PROMISE_RE = re.compile("|".join(PROMISE_PATTERNS), re.IGNORECASE)
_REQUEST_RE = re.compile("|".join(REQUEST_PATTERNS), re.IGNORECASE)
_RESOLUTION_RE = re.compile("|".join(RESOLUTION_PATTERNS), re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class TaskCandidate:
    kind: Literal["promise", "request"]
    title: str
    description: str
    due_at: datetime | None
    priority: int
    confidence: float
    evidence: str


def extract_task_candidate(text: str, *, now: datetime | None = None) -> TaskCandidate | None:
    source = text.strip()
    if not source:
        return None

    normalized = _normalize_text(source)
    if len(normalized) < 8:
        return None

    kind: Literal["promise", "request"] | None = None
    confidence = 0.0

    if _PROMISE_RE.search(normalized):
        kind = "promise"
        confidence = 0.65
    elif _REQUEST_RE.search(normalized):
        kind = "request"
        confidence = 0.55

    if kind is None:
        return None

    due_at = _extract_due_at(normalized, now=now)
    priority = 3 if due_at else 2
    title = _make_title(normalized)
    if due_at:
        confidence = max(confidence, 0.7)

    return TaskCandidate(
        kind=kind,
        title=title,
        description=normalized,
        due_at=due_at,
        priority=priority,
        confidence=round(confidence, 3),
        evidence=normalized[:400],
    )


def detect_resolution(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(normalized and _RESOLUTION_RE.search(normalized))


def _normalize_text(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _make_title(text: str) -> str:
    title = text.strip(" .,:;!-")
    if len(title) <= 80:
        return title
    return f"{title[:77].rstrip()}..."


def _extract_due_at(text: str, *, now: datetime | None) -> datetime | None:
    base = now or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)

    fallback = _extract_due_at_fallback(text, base)
    if search_dates is None:
        return fallback

    try:
        matches = search_dates(
            text,
            languages=["ru", "en"],
            settings={
                "PREFER_DATES_FROM": "future",
                "RELATIVE_BASE": base,
                "RETURN_AS_TIMEZONE_AWARE": True,
            },
        )
    except Exception:
        return None

    if not matches:
        return fallback

    for _, parsed in matches:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=base.tzinfo)
        if parsed >= base:
            return parsed
    return fallback


def _extract_due_at_fallback(text: str, base: datetime) -> datetime | None:
    lowered = text.lower()
    if "завтра" in lowered or "tomorrow" in lowered:
        return base + timedelta(days=1)
    if "eod" in lowered:
        return base.replace(hour=18, minute=0, second=0, microsecond=0)
    if "eow" in lowered:
        days = max(0, 4 - base.weekday())
        return (base + timedelta(days=days)).replace(hour=18, minute=0, second=0, microsecond=0)
    if "eom" in lowered:
        next_month = (base.replace(day=28) + timedelta(days=4)).replace(day=1)
        return (next_month - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    return None
