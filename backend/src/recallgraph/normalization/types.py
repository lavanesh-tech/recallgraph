"""Source-independent normalized representation produced by source normalizers."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class NormalizedProduct:
    name: str
    description: str | None
    model: str | None
    product_type: str | None
    category_code: str | None
    units_text: str | None


@dataclass(frozen=True, slots=True)
class NormalizedHazard:
    description: str
    hazard_type: str | None


@dataclass(frozen=True, slots=True)
class NormalizedIdentifier:
    kind: str  # 'upc' | 'model' | 'model_text'
    value: str
    normalized_value: str


@dataclass(frozen=True, slots=True)
class NormalizedCompany:
    role: str  # 'manufacturer' | 'importer' | 'distributor' | 'retailer'
    raw_name: str
    display_name: str
    normalized_name: str


@dataclass(frozen=True, slots=True)
class NormalizedRecall:
    recall_number: str | None
    title: str
    description: str | None
    recall_date: date | None
    published_date: date | None
    url: str | None
    consumer_contact: str | None
    injuries_summary: str | None
    sold_at: str | None
    remedy_options: tuple[str, ...]
    manufacturer_countries: tuple[str, ...]
    products: tuple[NormalizedProduct, ...]
    hazards: tuple[NormalizedHazard, ...]
    remedies: tuple[str, ...]
    identifiers: tuple[NormalizedIdentifier, ...]
    companies: tuple[NormalizedCompany, ...]
