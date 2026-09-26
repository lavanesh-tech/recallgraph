from datetime import date

import pytest

from recallgraph.normalization.text import (
    clean,
    company_display_name,
    extract_model_numbers,
    normalize_company_name,
    normalize_identifier,
    parse_date,
)


def test_clean_collapses_whitespace_and_blanks() -> None:
    assert clean("  Sold  At:\nAmazon.com ") == "Sold At: Amazon.com"
    assert clean("   ") is None
    assert clean(42) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("2026-09-24T00:00:00", date(2026, 9, 24)), ("2026-09-24", date(2026, 9, 24)), ("", None)],
)
def test_parse_date(raw: str, expected: date | None) -> None:
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    ("raw", "display", "key"),
    [
        ("Char-Broil LLC, of Columbus, Georgia", "Char-Broil LLC", "char broil"),
        (
            "Hayward Industries, Inc., of Charlotte, North Carolina",
            "Hayward Industries, Inc.",
            "hayward industries",
        ),
        ("Melissa & Doug, of Wilton, Connecticut", "Melissa & Doug", "melissa and doug"),
    ],
)
def test_company_names(raw: str, display: str, key: str) -> None:
    assert company_display_name(raw) == display
    assert normalize_company_name(display) == key


def test_normalize_identifier() -> None:
    assert normalize_identifier("xr-8801 ") == "XR8801"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("“Model No.: YD-001,” printed on a label", ["YD-001"]),
        ("helmets with model number XR-8801.", ["XR-8801"]),
        ('model numbers "SME004" or other', ["SME004"]),
        ("model descriptions Bistro Pro", []),
    ],
)
def test_extract_model_numbers(text: str, expected: list[str]) -> None:
    assert extract_model_numbers(text) == expected
