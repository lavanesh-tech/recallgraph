"""CPSC normalizer tests on a SYNTHETIC payload shaped like the real SaferProducts.gov API."""

from datetime import date
from typing import Any

import pytest

from recallgraph.normalization.cpsc import normalize_cpsc


def synthetic_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "RecallID": 900001,
        "RecallNumber": "S-0001",
        "RecallDate": "2026-09-24T00:00:00",
        "LastPublishDate": "2026-09-25T00:00:00",
        "Title": "SYNTHETIC Acme Recalls Air Fryers Due to Fire Hazard",
        "Description": "This recall involves Acme air fryers with model number AF-100X.",
        "URL": "https://example.invalid/recalls/900001",
        "ConsumerContact": "Acme toll-free at 800-000-0000",
        "Products": [
            {
                "Name": "Acme Air Fryers",
                "Model": "AF-100X, AF-200X",
                "Type": "Air Fryers",
                "CategoryID": "123",
                "NumberOfUnits": "About 1,000",
            }
        ],
        "Hazards": [{"Name": "The fryer can overheat, posing a fire hazard.", "HazardType": ""}],
        "Remedies": [{"Name": "Stop using the fryer and contact Acme for a refund."}],
        "RemedyOptions": [{"Option": "Refund"}, {"Option": "Refund"}],
        "Injuries": [{"Name": "None reported"}],
        "Manufacturers": [{"Name": "Acme Manufacturing Co., Ltd., of China", "CompanyID": ""}],
        "Importers": [{"Name": "Acme USA LLC, of Austin, Texas", "CompanyID": ""}],
        "Distributors": [],
        "Retailers": [{"Name": "Sold At:\nExample stores from 2025 for $50.", "CompanyID": ""}],
        "ManufacturerCountries": [{"Country": "China"}],
        "ProductUPCs": [{"UPC": "012345678905"}],
    }
    payload.update(overrides)
    return payload


def test_maps_core_fields_and_dates() -> None:
    recall = normalize_cpsc(synthetic_payload())

    assert recall.recall_number == "S-0001"
    assert recall.recall_date == date(2026, 9, 24)
    assert recall.published_date == date(2026, 9, 25)
    assert recall.url == "https://example.invalid/recalls/900001"
    assert recall.remedy_options == ("Refund",)
    assert recall.manufacturer_countries == ("China",)
    assert recall.injuries_summary == "None reported"
    assert recall.products[0].product_type == "Air Fryers"
    assert recall.hazards[0].hazard_type is None


def test_sales_text_is_not_treated_as_a_company() -> None:
    recall = normalize_cpsc(synthetic_payload())

    assert recall.sold_at == "Sold At: Example stores from 2025 for $50."
    assert [(c.role, c.normalized_name) for c in recall.companies] == [
        ("manufacturer", "acme manufacturing"),
        ("importer", "acme usa"),
    ]


def test_identifiers_from_model_field_upc_and_text() -> None:
    recall = normalize_cpsc(synthetic_payload())

    keys = {(i.kind, i.normalized_value) for i in recall.identifiers}
    assert ("model", "AF100X") in keys
    assert ("model", "AF200X") in keys
    assert ("upc", "012345678905") in keys
    assert ("model_text", "AF100X") in keys


def test_missing_title_is_rejected() -> None:
    with pytest.raises(ValueError, match="Title"):
        normalize_cpsc(synthetic_payload(Title="  "))


def test_tolerates_missing_optional_sections() -> None:
    recall = normalize_cpsc({"Title": "SYNTHETIC minimal"})

    assert recall.products == ()
    assert recall.companies == ()
    assert recall.recall_date is None
