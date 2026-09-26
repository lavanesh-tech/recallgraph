import math

import pytest

from recallgraph.provenance.hashing import canonical_json, content_hash


def test_hash_ignores_key_order() -> None:
    assert content_hash({"a": 1, "b": {"x": 1, "y": 2}}) == content_hash(
        {"b": {"y": 2, "x": 1}, "a": 1}
    )


def test_hash_changes_when_any_value_changes() -> None:
    assert content_hash({"title": "Recall A"}) != content_hash({"title": "Recall B"})


def test_hash_is_sha256_hex() -> None:
    digest = content_hash({"id": 1})
    assert len(digest) == 64
    int(digest, 16)


def test_canonical_json_is_compact_and_preserves_unicode() -> None:
    assert canonical_json({"b": "é", "a": [1, 2]}) == '{"a":[1,2],"b":"é"}'


def test_non_finite_numbers_are_rejected() -> None:
    with pytest.raises(ValueError):
        content_hash({"value": math.nan})
