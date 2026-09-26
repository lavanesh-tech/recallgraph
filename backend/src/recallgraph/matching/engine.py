"""Explainable product-to-recall scoring.

Every signal is a pure function returning (applicable, value in [0, 1], evidence text).
score = sum(weight * value) / sum(weight) over APPLICABLE signals only, so a query that omits a
field is neither rewarded nor penalized for it. Contributions sum exactly to the score.
Nothing here is a learned or "AI" confidence: weights and thresholds are explicit constants,
to be tuned only against the labeled evaluation set (Steps 13-14).
"""

from dataclasses import dataclass
from datetime import date

from recallgraph.matching.text import content_terms, extract_year, tokenize
from recallgraph.normalization.text import normalize_company_name, normalize_identifier

ENGINE_VERSION = "match-2"
WEIGHTS: dict[str, float] = {
    "identifier": 0.40,
    "manufacturer": 0.25,
    "category": 0.10,
    "lexical": 0.20,
    "date": 0.05,
}
LIKELY_THRESHOLD = 0.60
POSSIBLE_THRESHOLD = 0.35
IDENTITY_MIN = 0.6  # identifier-family or manufacturer evidence needed for "likely"
# match-2: every product term must appear in the recall's title/product names for "likely"
# (dev-split error analysis: all true matches had full coverage; partial coverage drove FPs).
PRODUCT_EVIDENCE_MIN = 1.0
FAMILY_MIN_LENGTH = 4
TIER_RANK = {"identifier_match": 0, "likely": 1, "possible": 2}


@dataclass(frozen=True, slots=True)
class MatchQuery:
    description: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    upc: str | None = None
    category: str | None = None
    purchase_year: int | None = None

    def effective_purchase_year(self) -> int | None:
        return self.purchase_year or extract_year(self.description)


@dataclass(frozen=True, slots=True)
class CandidateProfile:
    recall_id: int
    source: str
    source_record_id: str
    recall_number: str | None
    title: str
    recall_date: date | None
    url: str | None
    text_tokens: frozenset[str]  # title + description + product names (retrieval context)
    product_tokens: frozenset[str]  # title + product names/types only (lexical evidence)
    title_tokens: frozenset[str]
    identifiers: tuple[tuple[str, str, str], ...]  # (kind, value, normalized_value)
    companies: tuple[tuple[str, str, str], ...]  # (normalized_name, display_name, role)
    semantic_similarity: float | None = None  # cosine similarity, when semantic is enabled


@dataclass(frozen=True, slots=True)
class Signal:
    name: str
    applicable: bool
    weight: float
    value: float
    contribution: float
    evidence: str


@dataclass(frozen=True, slots=True)
class MatchResult:
    profile: CandidateProfile
    score: float
    tier: str
    signals: tuple[Signal, ...]


Raw = tuple[bool, float, str]
NOT_APPLICABLE: Raw = (False, 0.0, "not provided")


def _identifier(q: MatchQuery, p: CandidateProfile) -> Raw:
    inputs = [(v, normalize_identifier(v)) for v in (q.model, q.upc) if v]
    inputs = [(raw, key) for raw, key in inputs if key]
    if not inputs:
        return NOT_APPLICABLE
    best: Raw = (True, 0.0, "no recall identifier matches " + ", ".join(r for r, _ in inputs))
    for raw, key in inputs:
        for kind, value, norm in p.identifiers:
            if norm == key:
                return (True, 1.0, f"'{raw}' equals recall {kind} identifier '{value}'")
            family = min(len(key), len(norm)) >= FAMILY_MIN_LENGTH and (
                norm.startswith(key) or key.startswith(norm)
            )
            if family and best[1] < IDENTITY_MIN:
                best = (True, 0.6, f"'{raw}' shares a model-family prefix with '{value}'")
    return best


def _manufacturer(q: MatchQuery, p: CandidateProfile) -> Raw:
    key = normalize_company_name(q.manufacturer) if q.manufacturer else None
    if not key:
        return NOT_APPLICABLE
    wanted = set(key.split())
    best: Raw = (True, 0.0, f"'{q.manufacturer}' is not named on this recall")
    for norm, display, role in p.companies:
        if norm == key:
            return (True, 1.0, f"'{q.manufacturer}' is the recall's {role} '{display}'")
        if wanted <= set(norm.split()) and best[1] < 0.7:
            best = (True, 0.7, f"'{q.manufacturer}' is part of {role} name '{display}'")
    if best[1] < 0.5 and wanted <= p.title_tokens:
        best = (True, 0.5, f"'{q.manufacturer}' appears in the recall title")
    return best


def _overlap(terms: list[str], p: CandidateProfile, label: str) -> Raw:
    if not terms:
        return NOT_APPLICABLE
    # match-2: long defect descriptions share generic words ("may", "fail", "fmvss"), so
    # evidence is measured against the recall's title and product names only.
    hit = [t for t in terms if t in p.product_tokens]
    miss = [t for t in terms if t not in p.product_tokens]
    evidence = f"{label} terms matched: {', '.join(hit) or 'none'}"
    if miss:
        evidence += f"; not found: {', '.join(miss)}"
    return (True, len(hit) / len(terms), evidence)


def _date(q: MatchQuery, p: CandidateProfile) -> Raw:
    year = q.effective_purchase_year()
    if year is None or p.recall_date is None:
        return NOT_APPLICABLE
    gap = year - p.recall_date.year  # > 0: recall announced before the purchase year
    value = 1.0 if gap <= 2 else max(0.0, 1.0 - (gap - 2) / 10)
    return (True, round(value, 4), f"recall dated {p.recall_date}; purchase year {year}")


def _semantic(p: CandidateProfile, weight: float) -> Raw:
    if weight <= 0 or p.semantic_similarity is None:
        return (False, 0.0, "semantic retrieval not enabled")
    similarity = max(0.0, p.semantic_similarity)
    return (True, similarity, f"embedding cosine similarity {similarity:.3f}")


def score_candidate(
    q: MatchQuery, p: CandidateProfile, semantic_weight: float = 0.0
) -> MatchResult | None:
    """Return a scored, explained match, or None if the candidate is not even 'possible'."""
    weights = {**WEIGHTS, "semantic": semantic_weight}
    raws = {
        "identifier": _identifier(q, p),
        "manufacturer": _manufacturer(q, p),
        "category": _overlap(content_terms(q.category), p, "category"),
        "lexical": _overlap(content_terms(q.description), p, "description"),
        "date": _date(q, p),
        "semantic": _semantic(p, semantic_weight),
    }
    applicable_weight = sum(weights[n] for n, (ok, _, _) in raws.items() if ok)
    if applicable_weight == 0:
        return None
    signals = tuple(
        Signal(
            name=name,
            applicable=ok,
            weight=weights[name],
            value=round(value, 4),
            contribution=round(weights[name] * value / applicable_weight, 4) if ok else 0.0,
            evidence=evidence,
        )
        for name, (ok, value, evidence) in raws.items()
    )
    score = round(sum(s.contribution for s in signals), 4)
    value_of = {s.name: s.value for s in signals}
    identity = max(value_of["identifier"], value_of["manufacturer"])
    product = max(value_of["lexical"], value_of["category"])

    strong = identity >= IDENTITY_MIN and product >= PRODUCT_EVIDENCE_MIN
    if value_of["identifier"] == 1.0:
        tier = "identifier_match"
    elif score >= LIKELY_THRESHOLD and strong:
        tier = "likely"
    elif score >= POSSIBLE_THRESHOLD:
        tier = "possible"
    else:
        return None
    return MatchResult(profile=p, score=score, tier=tier, signals=signals)


def _title_overlap(terms: list[str], p: CandidateProfile) -> float:
    if not terms:
        return 0.0
    matched = len(set(terms) & p.title_tokens)
    return matched / (len(set(terms) | p.title_tokens) or 1)


def rank(results: list[MatchResult], q: MatchQuery | None = None) -> list[MatchResult]:
    """Tier, then score, then (match-2) title similarity to the query as a tie-breaker."""
    terms = query_terms(q) if q else []
    return sorted(
        results,
        key=lambda r: (
            TIER_RANK[r.tier],
            -r.score,
            -_title_overlap(terms, r.profile),
            -(r.profile.recall_date.toordinal() if r.profile.recall_date else 0),
            r.profile.recall_id,
        ),
    )


def query_terms(q: MatchQuery) -> list[str]:
    """Terms used for full-text candidate retrieval."""
    return content_terms(" ".join(v for v in (q.description, q.category) if v))


def title_tokens(title: str) -> frozenset[str]:
    return frozenset(tokenize(title))
