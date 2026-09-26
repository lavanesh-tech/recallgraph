"""CPSC raw payload -> NormalizedRecall. Pure and deterministic: no I/O, no AI."""

import re
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

NORMALIZER_VERSION = "cpsc-1"
MAX_IDENTIFIER_LENGTH = 64
_COMPANY_FIELDS = (
    ("Manufacturers", "manufacturer"),
    ("Importers", "importer"),
    ("Distributors", "distributor"),
    ("Retailers", "retailer"),
)
_MODEL_LIST_SEPARATOR = re.compile(r"[,;]\s*|\s+and\s+")


def _items(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _companies(payload: dict[str, Any]) -> tuple[tuple[NormalizedCompany, ...], str | None]:
    companies: list[NormalizedCompany] = []
    sold_at: list[str] = []
    for field, role in _COMPANY_FIELDS:
        for item in _items(payload, field):
            raw = clean(item.get("Name"))
            if raw is None:
                continue
            # CPSC puts "Sold At: ..." sales text in the Retailers list; it is not a company.
            if role == "retailer" and raw.lower().startswith("sold"):
                sold_at.append(raw)
                continue
            display = company_display_name(raw)
            key = normalize_company_name(display) if display else None
            if display and key:
                companies.append(NormalizedCompany(role, raw, display, key))
    return tuple(companies), (" | ".join(sold_at) or None)


def _identifiers(
    payload: dict[str, Any], products: tuple[NormalizedProduct, ...], texts: list[str | None]
) -> tuple[NormalizedIdentifier, ...]:
    found: dict[tuple[str, str], NormalizedIdentifier] = {}

    def add(kind: str, value: str) -> None:
        key = normalize_identifier(value)
        if 3 <= len(key) <= MAX_IDENTIFIER_LENGTH and any(ch.isdigit() for ch in key):
            found.setdefault((kind, key), NormalizedIdentifier(kind, value.strip(), key))

    upcs = payload.get("ProductUPCs")
    for item in upcs if isinstance(upcs, list) else []:
        value = item.get("UPC") if isinstance(item, dict) else item
        if isinstance(value, str | int):
            digits = re.sub(r"\D", "", str(value))
            if 8 <= len(digits) <= 14:
                found.setdefault(("upc", digits), NormalizedIdentifier("upc", str(value), digits))
    for product in products:
        if product.model:
            for part in _MODEL_LIST_SEPARATOR.split(product.model):
                add("model", part)
    for text in texts:
        for model in extract_model_numbers(text or ""):
            add("model_text", model)
    return tuple(found.values())


def normalize_cpsc(payload: dict[str, Any]) -> NormalizedRecall:
    title = clean(payload.get("Title"))
    if title is None:
        raise ValueError("CPSC record has no Title")
    description = clean(payload.get("Description"))

    products = tuple(
        NormalizedProduct(
            name=clean(p.get("Name")) or title,
            description=clean(p.get("Description")),
            model=clean(p.get("Model")),
            product_type=clean(p.get("Type")),
            category_code=clean(p.get("CategoryID")),
            units_text=clean(p.get("NumberOfUnits")),
        )
        for p in _items(payload, "Products")
    )
    hazards = tuple(
        NormalizedHazard(desc, clean(h.get("HazardType")))
        for h in _items(payload, "Hazards")
        if (desc := clean(h.get("Name")))
    )
    remedies = _unique([d for r in _items(payload, "Remedies") if (d := clean(r.get("Name")))])
    injuries = [d for i in _items(payload, "Injuries") if (d := clean(i.get("Name")))]
    companies, sold_at = _companies(payload)
    url = clean(payload.get("URL"))

    return NormalizedRecall(
        recall_number=clean(payload.get("RecallNumber")),
        title=title,
        description=description,
        recall_date=parse_date(payload.get("RecallDate")),
        published_date=parse_date(payload.get("LastPublishDate")),
        url=url if url and url.startswith("http") else None,
        consumer_contact=clean(payload.get("ConsumerContact")),
        injuries_summary=" | ".join(injuries) or None,
        sold_at=sold_at,
        remedy_options=_unique(
            [o for r in _items(payload, "RemedyOptions") if (o := clean(r.get("Option")))]
        ),
        manufacturer_countries=_unique(
            [c for r in _items(payload, "ManufacturerCountries") if (c := clean(r.get("Country")))]
        ),
        products=products,
        hazards=hazards,
        remedies=remedies,
        identifiers=_identifiers(
            payload, products, [title, description, *(p.name for p in products)]
        ),
        companies=companies,
    )
