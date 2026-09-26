"""Evaluation metrics for the matching engine (pure, unit-tested).

A prediction is "positive" when its tier is in the operating point's tier set:
  strict  = identifier_match, likely          (what the product presents as a match)
  lenient = strict + possible                  (what the product shows as worth checking)
Pair-level (micro) counts over all cases:
  TP = predicted AND expected, FP = predicted NOT expected, FN = expected NOT predicted.
  precision = TP/(TP+FP), recall = TP/(TP+FN), F1, false_negative_rate = FN/(TP+FN).
Query-level false_positive_rate = negative cases (expected = {}) with >= 1 positive prediction
divided by all negative cases. hit@k = positive cases with an expected recall in the top k
results of any tier.
"""

from collections.abc import Iterable
from dataclasses import dataclass

Key = tuple[str, str]  # (source code, source_record_id)
STRICT = frozenset({"identifier_match", "likely"})
LENIENT = frozenset({"identifier_match", "likely", "possible"})
OPERATING_POINTS = {"strict": STRICT, "lenient": LENIENT}


@dataclass(frozen=True, slots=True)
class CaseOutcome:
    case_id: str
    kind: str
    expected: frozenset[Key]
    ranked: tuple[tuple[Key, str], ...]  # (recall key, tier) in rank order


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


@dataclass(slots=True)
class Confusion:
    cases: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    positive_cases: int = 0
    negative_cases: int = 0
    negative_cases_with_positive: int = 0
    hit_at_1: int = 0
    hit_at_5: int = 0

    def add(self, outcome: CaseOutcome, tiers: frozenset[str]) -> None:
        predicted = {key for key, tier in outcome.ranked if tier in tiers}
        self.cases += 1
        self.tp += len(predicted & outcome.expected)
        self.fp += len(predicted - outcome.expected)
        self.fn += len(outcome.expected - predicted)
        if outcome.expected:
            self.positive_cases += 1
            keys = [key for key, _ in outcome.ranked]
            self.hit_at_1 += bool(outcome.expected & set(keys[:1]))
            self.hit_at_5 += bool(outcome.expected & set(keys[:5]))
        else:
            self.negative_cases += 1
            self.negative_cases_with_positive += bool(predicted)

    def report(self) -> dict[str, float | int | None]:
        precision = _ratio(self.tp, self.tp + self.fp)
        recall = _ratio(self.tp, self.tp + self.fn)
        f1 = (
            round(2 * precision * recall / (precision + recall), 4)
            if precision is not None and recall is not None and precision + recall > 0
            else None
        )
        return {
            "cases": self.cases,
            "positive_cases": self.positive_cases,
            "negative_cases": self.negative_cases,
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "false_negative_rate": _ratio(self.fn, self.tp + self.fn),
            "false_positive_rate": _ratio(self.negative_cases_with_positive, self.negative_cases),
            "hit_at_1": _ratio(self.hit_at_1, self.positive_cases),
            "hit_at_5": _ratio(self.hit_at_5, self.positive_cases),
        }


def evaluate(
    outcomes: Iterable[CaseOutcome],
) -> dict[str, dict[str, dict[str, float | int | None]]]:
    """{operating point: {"overall" | kind: metrics}}."""
    items = list(outcomes)
    result: dict[str, dict[str, dict[str, float | int | None]]] = {}
    for point, tiers in OPERATING_POINTS.items():
        groups: dict[str, Confusion] = {"overall": Confusion()}
        for outcome in items:
            groups["overall"].add(outcome, tiers)
            groups.setdefault(outcome.kind, Confusion()).add(outcome, tiers)
        result[point] = {name: c.report() for name, c in sorted(groups.items())}
    return result
