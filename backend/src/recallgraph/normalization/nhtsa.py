"""NHTSA raw payload -> NormalizedRecall. Pure and deterministic: no I/O, no AI."""

from typing import Any

from recallgraph.normalization.text import (
    clean,
    company_display_name,
    extract_model_numbers,
    normalize_company_name,
    normalize_identifier,
    parse_date,
)
from recallgraph.normalization.types import (
    NormalizedCompany,
    NormalizedHazard,
    NormalizedIdentifier,
    NormalizedProduct,
    NormalizedRecall,
)

NORMALIZER_VERSION = "nhtsa-1"


def _flag(value: object) -> bool:
    return isinstance(value, str) and value.strip().lower() == "yes"


def normalize_nhtsa(payload: dict[str, Any]) -> NormalizedRecall:
    title = clean(payload.get("subject"))
    if title is None:
        raise ValueError("NHTSA record has no subject")
    description = clean(payload.get("defect_summary"))
    link = payload.get("recall_link")
    url = clean(link.get("url")) if isinstance(link, dict) else None

    hazards: list[NormalizedHazard] = []
    if consequence := clean(payload.get("consequence_summary")):
        hazards.append(NormalizedHazard(consequence, None))
    if _flag(payload.get("fire_risk_when_parked")):
        hazards.append(NormalizedHazard("NHTSA flag: fire risk when parked", "park_outside"))
    if _flag(payload.get("do_not_drive")):
        hazards.append(NormalizedHazard("NHTSA flag: do not drive", "do_not_drive"))

    companies: tuple[NormalizedCompany, ...] = ()
    if raw_manufacturer := clean(payload.get("manufacturer")):
        display = company_display_name(raw_manufacturer)
        key = normalize_company_name(display) if display else None
        if display and key:
            companies = (NormalizedCompany("manufacturer", raw_manufacturer, display, key),)

    identifiers: dict[str, NormalizedIdentifier] = {}
    for text in (title, description):
        for model in extract_model_numbers(text or ""):
            key = normalize_identifier(model)
            if 3 <= len(key) <= 64:
                identifiers.setdefault(key, NormalizedIdentifier("model_text", model, key))

    corrective = clean(payload.get("corrective_action"))
    return NormalizedRecall(
        recall_number=clean(payload.get("nhtsa_id")),
        title=title,
        description=description,
        recall_date=parse_date(payload.get("report_received_date")),
        published_date=None,
        url=url if url and url.startswith("http") else None,
        consumer_contact=None,
        injuries_summary=None,
        sold_at=None,
        remedy_options=(),
        manufacturer_countries=(),
        products=(
            NormalizedProduct(
                name=title,
                description=clean(payload.get("component")),
                model=None,
                product_type=clean(payload.get("recall_type")),
                category_code=None,
                units_text=clean(payload.get("potentially_affected")),
            ),
        ),
        hazards=tuple(hazards),
        remedies=(corrective,) if corrective else (),
        identifiers=tuple(identifiers.values()),
        companies=companies,
    )
