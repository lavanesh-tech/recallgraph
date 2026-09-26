"""Deterministic tokenization used by the matching engine (no ML, fully reproducible)."""

import re

_TOKEN = re.compile(r"[a-z0-9]+")
_YEAR = re.compile(r"\b(19[5-9]\d|20\d\d)\b")

# Words that describe the purchase, not the product; they must not count as product evidence.
# fmt: off
STOPWORDS = frozenset(
    {
        "a", "about", "ago", "an", "and", "approximately", "around", "at", "bought", "by",
        "for", "from", "got", "i", "in", "is", "it", "its", "maybe", "my", "new", "of", "old",
        "on", "or", "our", "purchased", "roughly", "some", "that", "the", "this", "to", "used",
        "was", "we", "with", "year", "years",
    }
)
# fmt: on


def normalize_token(token: str) -> str:
    """Light plural folding so 'fryers' matches 'fryer' and 'batteries' matches 'battery'."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str | None) -> list[str]:
    return [normalize_token(t) for t in _TOKEN.findall((text or "").lower())]


def content_terms(text: str | None) -> list[str]:
    """Distinct product-describing terms: no stopwords, no 4-digit years, at least 2 chars."""
    terms: list[str] = []
    for token in tokenize(text):
        is_year = token.isdigit() and len(token) == 4
        if len(token) >= 2 and token not in STOPWORDS and not is_year and token not in terms:
            terms.append(token)
    return terms


def extract_year(text: str | None) -> int | None:
    match = _YEAR.search(text or "")
    return int(match.group(1)) if match else None
