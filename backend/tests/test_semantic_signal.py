from dataclasses import replace

import pytest

from recallgraph.matching.engine import MatchQuery, score_candidate
from tests.test_matching_engine import profile


def test_semantic_signal_is_off_by_default() -> None:
    result = score_candidate(MatchQuery(description="air fryer"), profile())

    assert result is not None
    semantic = next(s for s in result.signals if s.name == "semantic")
    assert (semantic.applicable, semantic.contribution) == (False, 0.0)


def test_semantic_signal_contributes_when_enabled() -> None:
    p = replace(profile(), semantic_similarity=0.5)
    baseline = score_candidate(MatchQuery(description="air fryer"), p)
    with_semantic = score_candidate(MatchQuery(description="air fryer"), p, semantic_weight=0.15)

    assert baseline is not None and with_semantic is not None
    semantic = next(s for s in with_semantic.signals if s.name == "semantic")
    assert semantic.applicable and semantic.value == 0.5
    assert with_semantic.score < baseline.score  # weaker semantic evidence lowers the mean
    assert sum(s.contribution for s in with_semantic.signals) == pytest.approx(
        with_semantic.score, abs=1e-3
    )
