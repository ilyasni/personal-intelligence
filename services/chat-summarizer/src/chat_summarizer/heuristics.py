import re
from collections import Counter
from dataclasses import dataclass

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "i", "in", "is", "it",
    "of", "on", "or", "that", "the", "to", "we", "with", "you", "я", "и", "в", "во", "на",
    "не", "что", "это", "как", "по", "к", "ко", "у", "за", "но", "да", "ты", "мы", "вы",
    "он", "она", "они", "мне", "тебе", "нам", "вам", "из", "от", "до", "ли", "же", "ну",
}

POSITIVE_WORDS = {
    "good", "great", "thanks", "thank", "nice", "done", "ready", "cool", "отлично", "спасибо",
    "супер", "хорошо", "готово", "класс", "ок", "окей",
}

NEGATIVE_WORDS = {
    "bad", "issue", "problem", "fail", "blocked", "broken", "hate", "плохо", "проблема",
    "ошибка", "сломалось", "блокер", "задержка", "не работает",
}

WORD_RE = re.compile(r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_-]{2,}")


@dataclass(frozen=True)
class SummaryResult:
    topics: list[str]
    sentiment: str
    summary: str


def summarize_window(texts: list[str], *, max_chars: int) -> SummaryResult:
    cleaned = [text.strip() for text in texts if text and text.strip()]
    if not cleaned:
        return SummaryResult(topics=[], sentiment="neutral", summary="No meaningful messages in the window.")

    topics = extract_topics(cleaned)
    sentiment = detect_sentiment(cleaned)
    summary = build_summary(cleaned, topics=topics, sentiment=sentiment, max_chars=max_chars)
    return SummaryResult(topics=topics, sentiment=sentiment, summary=summary)


def extract_topics(texts: list[str], *, limit: int = 5) -> list[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        for token in WORD_RE.findall(text.lower()):
            if token in STOPWORDS or token.isdigit():
                continue
            counts[token] += 1
    return [token for token, _ in counts.most_common(limit)]


def detect_sentiment(texts: list[str]) -> str:
    positive = 0
    negative = 0
    for text in texts:
        lowered = text.lower()
        positive += sum(word in lowered for word in POSITIVE_WORDS)
        negative += sum(word in lowered for word in NEGATIVE_WORDS)
    if positive and negative:
        return "mixed"
    if positive:
        return "positive"
    if negative:
        return "negative"
    return "neutral"


def build_summary(
    texts: list[str],
    *,
    topics: list[str],
    sentiment: str,
    max_chars: int,
) -> str:
    first = texts[0]
    last = texts[-1]
    parts = [f"{len(texts)} messages"]
    if topics:
        parts.append(f"topics: {', '.join(topics[:3])}")
    parts.append(f"sentiment: {sentiment}")
    parts.append(f"start: {truncate(first, 100)}")
    if len(texts) > 1:
        parts.append(f"end: {truncate(last, 100)}")
    return truncate("; ".join(parts), max_chars)


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3].rstrip()}..."
