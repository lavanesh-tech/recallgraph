import pytest

from recallgraph.evaluation.metrics import CaseOutcome, evaluate


def outcome(
    case_id: str, kind: str, expected: set[str], ranked: list[tuple[str, str]]
) -> CaseOutcome:
    return CaseOutcome(
        case_id=case_id,
        kind=kind,
        expected=frozenset(("cpsc", e) for e in expected),
        ranked=tuple((("cpsc", rid), tier) for rid, tier in ranked),
    )


OUTCOMES = [
    # TP at strict; an extra "possible" result only counts as FP at lenient.
    outcome("a", "identifier", {"1"}, [("1", "identifier_match"), ("9", "possible")]),
    # Expected recall only found as "possible": FN at strict, TP at lenient.
    outcome("b", "product", {"2"}, [("2", "possible")]),
    # Wrong "likely" answer: FP and FN at both points.
    outcome("c", "product", {"3"}, [("7", "likely"), ("3", "possible")]),
    # Negative case with a strict positive -> false positive case.
    outcome("d", "negative_model", set(), [("8", "likely")]),
    # Clean negative case.
    outcome("e", "negative_model", set(), []),
]


def test_strict_metrics() -> None:
    strict = evaluate(OUTCOMES)["strict"]["overall"]

    assert (strict["tp"], strict["fp"], strict["fn"]) == (1, 2, 2)
    assert strict["precision"] == pytest.approx(1 / 3, abs=1e-4)
    assert strict["recall"] == pytest.approx(1 / 3, abs=1e-4)
    assert strict["f1"] == pytest.approx(1 / 3, abs=1e-4)
    assert strict["false_negative_rate"] == pytest.approx(2 / 3, abs=1e-4)
    assert strict["false_positive_rate"] == 0.5


def test_lenient_metrics_count_possible_tier() -> None:
    lenient = evaluate(OUTCOMES)["lenient"]["overall"]

    assert (lenient["tp"], lenient["fp"], lenient["fn"]) == (3, 3, 0)
    assert lenient["recall"] == 1.0


def test_hit_at_k_and_per_kind_breakdown() -> None:
    result = evaluate(OUTCOMES)["strict"]

    assert result["overall"]["hit_at_1"] == pytest.approx(2 / 3, abs=1e-4)
    assert result["overall"]["hit_at_5"] == 1.0
    assert set(result) == {"overall", "identifier", "product", "negative_model"}
    assert result["negative_model"]["recall"] is None


def test_empty_input_has_no_ratios() -> None:
    assert evaluate([])["strict"]["overall"]["precision"] is None
