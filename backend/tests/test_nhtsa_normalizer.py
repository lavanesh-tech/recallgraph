"""NHTSA normalizer tests on a SYNTHETIC payload shaped like the real dataset."""

from datetime import date
from typing import Any

import pytest

from recallgraph.normalization.nhtsa import normalize_nhtsa


def synthetic_nhtsa(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "report_received_date": "2026-09-23T00:00:00.000",
        "nhtsa_id": "99V000001",
        "recall_link": {"url": "https://example.invalid/99V000001", "description": "Go to Recall"},
        "manufacturer": "Example Motors, LLC",
        "subject": "SYNTHETIC Brake Hose May Leak",
        "component": "SERVICE BRAKES, HYDRAULIC",
        "recall_type": "Vehicle",
        "potentially_affected": "1200",
        "defect_summary": "Example Motors is recalling certain 2026 Example sedans.",
        "consequence_summary": "A leak can reduce braking, increasing the risk of a crash.",
        "corrective_action": "Dealers will replace the hose, free of charge.",
        "fire_risk_when_parked": "No",
        "do_not_drive": "Yes",
    }
    payload.update(overrides)
    return payload


def test_maps_campaign_fields() -> None:
    recall = normalize_nhtsa(synthetic_nhtsa())

    assert recall.recall_number == "99V000001"
    assert recall.recall_date == date(2026, 9, 23)
    assert recall.url == "https://example.invalid/99V000001"
    assert recall.remedies == ("Dealers will replace the hose, free of charge.",)
    product = recall.products[0]
    assert (product.product_type, product.description, product.units_text) == (
        "Vehicle",
        "SERVICE BRAKES, HYDRAULIC",
        "1200",
    )
    assert [(c.role, c.normalized_name) for c in recall.companies] == [
        ("manufacturer", "example motors")
    ]


def test_safety_flags_become_explicit_hazards() -> None:
    recall = normalize_nhtsa(synthetic_nhtsa(fire_risk_when_parked="Yes"))

    assert [h.hazard_type for h in recall.hazards] == [None, "park_outside", "do_not_drive"]


def test_missing_subject_is_rejected() -> None:
    with pytest.raises(ValueError, match="subject"):
        normalize_nhtsa(synthetic_nhtsa(subject=None))
