"""Deterministic text normalization helpers (pure functions, fully unit-tested)."""

import re
from datetime import date

_WHITESPACE = re.compile(r"\s+")
_OF_LOCATION = re.compile(r",\s*of\s+", re.IGNORECASE)
_NON_ALNUM_LOWER = re.compile(r"[^a-z0-9]+")
_NON_ALNUM_UPPER = re.compile(r"[^A-Z0-9]")
_MODEL_MENTION = re.compile(
    r"\bmodel(?:\s+(?:number|no\.?|#))?s?\s*[:#]?\s*[\"“”']?([A-Za-z0-9][A-Za-z0-9\-./]{1,39})",
    re.IGNORECASE,
)
LEGAL_SUFFIXES = frozenset(
    {"inc", "llc", "ltd", "co", "corp", "corporation", "company", "limited", "plc", "gmbh", "lp"}
)


def clean(value: object) -> str | None:
    """Collapse whitespace; non-strings and blank strings become None."""
    if not isinstance(value, str):
        return None
    collapsed = _WHITESPACE.sub(" ", value).strip()
    return collapsed or None


def parse_date(value: object) -> date | None:
    """Accepts ISO dates or datetimes such as '2026-09-24T00:00:00'."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def company_display_name(raw: str) -> str | None:
    """'Char-Broil LLC, of Columbus, Georgia' -> 'Char-Broil LLC'."""
    name = _OF_LOCATION.split(raw, maxsplit=1)[0].strip(" ,;")
    return name or None


def normalize_company_name(name: str) -> str | None:
    """Dedup key: lowercase alphanumeric tokens without legal suffixes ('char broil')."""
    tokens = _NON_ALNUM_LOWER.split(name.lower().replace("&", " and "))
    kept = [t for t in tokens if t and t not in LEGAL_SUFFIXES]
    return " ".join(kept) or None


def normalize_identifier(value: str) -> str:
    """'XR-8801' -> 'XR8801'. Used as the identifier matching key."""
    return _NON_ALNUM_UPPER.sub("", value.upper())


def extract_model_numbers(text: str) -> list[str]:
    """Model numbers explicitly introduced by 'model', 'model no.', 'model number' (with digits)."""
    found: list[str] = []
    for match in _MODEL_MENTION.finditer(text):
        candidate = match.group(1).rstrip(".-/")
        if any(ch.isdigit() for ch in candidate) and candidate not in found:
            found.append(candidate)
    return found
