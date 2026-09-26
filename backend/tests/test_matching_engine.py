"""Pure scoring-engine tests on SYNTHETIC candidate profiles (no database)."""

from dataclasses import replace
from datetime import date

import pytest

from recallgraph.matching.engine import (
    CandidateProfile,
    MatchQuery,
    MatchResult,
    Signal,
    rank,
    score_candidate,
    title_tokens,
)
from recallgraph.matching.text import content_terms, extract_year, tokenize


def profile(
    recall_id: int = 1,
    title: str = "SYNTHETIC Acme Recalls Air Fryers Due to Fire Hazard",
    text: str = "acme air fryers overheat fire hazard",
    recall_date: date | None = date(2026, 9, 24),
    identifiers: tuple[tuple[str, str, str], ...] = (("model", "AF-100X", "AF100X"),),
    companies: tuple[tuple[str, str, str], ...] = (
        ("acme manufacturing", "Acme Manufacturing Co., Ltd.", "manufacturer"),
    ),
) -> CandidateProfile:
    return CandidateProfile(
        recall_id=recall_id,
        source="cpsc",
        source_record_id=str(recall_id),
        recall_number=None,
        title=title,
        recall_date=recall_date,
        url=None,
        text_tokens=frozenset(tokenize(f"{title} {text}")),
        product_tokens=frozenset(tokenize(f"{title} {text}")),
        title_tokens=title_tokens(title),
        identifiers=identifiers,
        companies=companies,
    )


def signal(result: MatchResult | None, name: str) -> Signal:
    assert result is not None
    return next(s for s in result.signals if s.name == name)


def test_tokenization_folds_plurals_and_drops_purchase_words() -> None:
    assert tokenize("Air Fryers, batteries") == ["air", "fryer", "battery"]
    assert content_terms("black air fryer bought around 2024") == ["black", "air", "fryer"]
    assert extract_year("bought around 2024") == 2024


def test_exact_model_is_an_identifier_match() -> None:
    result = score_candidate(MatchQuery(model="af-100x"), profile())

    assert result is not None
    assert (result.tier, result.score) == ("identifier_match", 1.0)
    assert "equals recall model identifier 'AF-100X'" in signal(result, "identifier").evidence


def test_model_family_prefix_scores_partial() -> None:
    result = score_candidate(MatchQuery(model="AF-100", description="air fryer"), profile())

    assert result is not None
    assert signal(result, "identifier").value == 0.6
    assert result.tier == "likely"


def test_loose_description_without_identity_is_only_possible() -> None:
    q = MatchQuery(description="black air fryer bought around 2024")
    result = score_candidate(q, profile())

    assert result is not None
    assert result.tier == "possible"
    lexical = signal(result, "lexical")
    assert lexical.value == pytest.approx(2 / 3, abs=1e-4)
    assert "not found: black" in lexical.evidence
    assert signal(result, "date").value == 1.0


def test_manufacturer_plus_description_is_likely() -> None:
    result = score_candidate(MatchQuery(manufacturer="Acme", description="air fryer"), profile())

    assert result is not None
    assert result.tier == "likely"
    assert signal(result, "manufacturer").value == 0.7


def test_manufacturer_alone_is_not_enough_for_likely() -> None:
    result = score_candidate(MatchQuery(manufacturer="Acme Manufacturing"), profile())

    assert result is not None
    assert result.tier == "possible"


def test_brand_in_title_counts_as_weaker_manufacturer_evidence() -> None:
    result = score_candidate(
        MatchQuery(manufacturer="Acme", description="air fryer"), profile(companies=())
    )

    assert result is not None
    assert signal(result, "manufacturer").value == 0.5


def test_unrelated_candidate_is_dropped() -> None:
    heater = profile(title="SYNTHETIC Beta Space Heaters", text="beta heater", identifiers=())

    assert score_candidate(MatchQuery(description="black air fryer"), heater) is None


def test_contributions_sum_to_score_and_ignore_missing_fields() -> None:
    result = score_candidate(MatchQuery(model="AF-100X", description="air fryer"), profile())

    assert result is not None
    assert sum(s.contribution for s in result.signals) == pytest.approx(result.score, abs=1e-3)
    assert all(s.contribution == 0.0 for s in result.signals if not s.applicable)


def test_old_recall_decays_date_compatibility() -> None:
    old = profile(recall_date=date(2010, 1, 1))
    result = score_candidate(MatchQuery(description="acme air fryer", purchase_year=2024), old)

    assert result is not None
    assert signal(result, "date").value == 0.0


def test_ranking_orders_by_tier_then_score() -> None:
    exact = score_candidate(MatchQuery(model="AF-100X"), profile(recall_id=1))
    loose = score_candidate(MatchQuery(description="air fryer"), profile(recall_id=2))
    assert exact is not None and loose is not None

    assert [r.profile.recall_id for r in rank([loose, exact])] == [1, 2]


def test_lexical_evidence_ignores_long_defect_text() -> None:
    p = profile(text="acme air fryers")
    generic = replace(p, text_tokens=p.text_tokens | {"brake"})

    result = score_candidate(MatchQuery(manufacturer="Acme", description="brake"), generic)

    assert result is not None
    assert signal(result, "lexical").value == 0.0
    assert result.tier == "possible"


def test_likely_requires_full_product_term_coverage() -> None:
    q = MatchQuery(manufacturer="Acme Manufacturing", description="air fryer basket")

    result = score_candidate(q, profile())

    assert result is not None
    assert result.tier == "possible"


def test_rank_breaks_score_ties_by_title_similarity() -> None:
    q = MatchQuery(description="air fryer")
    close = score_candidate(q, profile(recall_id=5, title="Air Fryers Recalled", text=""))
    far = score_candidate(
        q, profile(recall_id=4, title="Kitchen Appliance Recall Air Fryers and Ovens", text="")
    )
    assert close is not None and far is not None
    assert close.score == far.score

    assert [r.profile.recall_id for r in rank([far, close], q)] == [5, 4]
