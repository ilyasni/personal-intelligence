"""spaCy-based NER. Loads models lazily and caches them per language."""
import re
from dataclasses import dataclass, field

import spacy
from langdetect import detect, LangDetectException

_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_EMAIL_RE = re.compile(r"\S+@\S+\.\S+")
_PHONE_RE = re.compile(r"[\+\d][\d\s\-\(\)]{7,}\d")

# spaCy label → our kind
_LABEL_MAP: dict[str, str] = {
    "PER": "person",
    "PERSON": "person",
    "ORG": "organization",
    "GPE": "topic",
    "LOC": "topic",
    "NORP": "topic",
    "WORK_OF_ART": "topic",
    "EVENT": "topic",
}

_nlp_cache: dict[str, spacy.Language] = {}


@dataclass
class RawEntity:
    kind: str
    surface: str
    normalized: str
    confidence: float = 0.75


def _get_nlp(lang: str) -> spacy.Language:
    if lang not in _nlp_cache:
        model = "ru_core_news_sm" if lang == "ru" else "en_core_web_sm"
        _nlp_cache[lang] = spacy.load(model)
    return _nlp_cache[lang]


def detect_language(text: str) -> str:
    try:
        lang = detect(text)
        return lang if lang in ("ru", "en") else "en"
    except LangDetectException:
        return "en"


def _preprocess(text: str) -> str:
    text = _URL_RE.sub("__URL__", text)
    text = _EMAIL_RE.sub("__EMAIL__", text)
    text = _PHONE_RE.sub("__PHONE__", text)
    return text


def extract(text: str, min_confidence: float = 0.6) -> tuple[str, list[RawEntity]]:
    """Return (language, list[RawEntity]) from message text."""
    if not text or not text.strip():
        return "en", []

    lang = detect_language(text)
    processed = _preprocess(text)
    nlp = _get_nlp(lang)
    doc = nlp(processed)

    results: list[RawEntity] = []
    seen: set[str] = set()

    for ent in doc.ents:
        kind = _LABEL_MAP.get(ent.label_)
        if kind is None:
            continue
        surface = ent.text.strip()
        if not surface or surface.startswith("__"):
            continue
        normalized = surface.lower().strip()
        key = f"{kind}:{normalized}"
        if key in seen:
            continue
        seen.add(key)
        results.append(RawEntity(kind=kind, surface=surface, normalized=normalized))

    return lang, [e for e in results if e.confidence >= min_confidence]
