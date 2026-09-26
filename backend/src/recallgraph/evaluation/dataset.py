"""Builds a reproducible, labeled evaluation set from the ingested official data.

Labels are DERIVED from the authoritative records by explicit rules (see evaluation/PROTOCOL.md);
they are never produced by the matching engine itself:
  identifier   query = one model/UPC identifier; expected = every recall carrying that exact
               normalized identifier (complete by construction).
  product      query = the recall's manufacturer + its product name with the brand removed +
               the recall year as purchase year; expected = that source recall only
               (INCOMPLETE: other genuinely matching recalls count as false positives, so
               precision is a lower bound for this kind).
  negative_*   queries with no correct answer (expected = {}): a model number verified absent
               from the data, or a real product description with a fictitious manufacturer.
"""

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import String, and_, cast, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.matching.text import content_terms, tokenize
from recallgraph.provenance.models import Source
from recallgraph.recalls.models import (
    Company,
    Recall,
    RecallCompany,
    RecallIdentifier,
    RecallProduct,
)

DATASET_FORMAT = "recallgraph-eval-1"
MAX_RECALLS_PER_IDENTIFIER = 10
FICTITIOUS_COMPANIES = ("Zorvexa Holdings", "Quintrel Appliance Group", "Varnoth Industries")


def split_of(case_id: str) -> str:
    """Stable 50/50 split: tune on "dev", report held-out results on "test"."""
    return "dev" if int(hashlib.sha256(case_id.encode()).hexdigest()[:8], 16) % 2 == 0 else "test"


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    kind: str
    query: dict[str, Any]
    expected: list[list[str]]
    label_method: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, ensure_ascii=False)

    @staticmethod
    def from_json(line: str) -> "EvalCase":
        data = json.loads(line)
        return EvalCase(
            case_id=data["case_id"],
            kind=data["kind"],
            query=data["query"],
            expected=data["expected"],
            label_method=data["label_method"],
        )


def _order(seed: int, column: Any) -> Any:
    # Deterministic pseudo-random order that does not depend on physical row order.
    return func.md5(func.concat(cast(column, String), f":{seed}"))


async def _identifier_cases(session: AsyncSession, seed: int, n: int) -> list[EvalCase]:
    n_recalls = func.count(distinct(RecallIdentifier.recall_id))
    rows = await session.execute(
        select(RecallIdentifier.normalized_value, func.min(RecallIdentifier.value))
        .where(
            RecallIdentifier.kind.in_(("model", "upc")),
            func.length(RecallIdentifier.normalized_value) >= 4,
        )
        .group_by(RecallIdentifier.normalized_value)
        .having(n_recalls <= MAX_RECALLS_PER_IDENTIFIER)
        .order_by(_order(seed, RecallIdentifier.normalized_value))
        .limit(n)
    )
    cases: list[EvalCase] = []
    for normalized, value in rows.all():
        expected = await session.execute(
            select(Source.code, Recall.source_record_id)
            .distinct()
            .join(Recall, Recall.source_id == Source.id)
            .join(RecallIdentifier, RecallIdentifier.recall_id == Recall.id)
            .where(RecallIdentifier.normalized_value == normalized)
            .order_by(Source.code, Recall.source_record_id)
        )
        cases.append(
            EvalCase(
                case_id=f"identifier-{normalized}",
                kind="identifier",
                query={"model": value},
                expected=[[code, sid] for code, sid in expected],
                label_method="derived: all recalls with the same normalized identifier",
            )
        )
    return cases


async def _product_rows(session: AsyncSession, seed: int, n: int) -> list[tuple[Any, ...]]:
    rows = await session.execute(
        select(
            Recall.id,
            Source.code,
            Recall.source_record_id,
            Recall.recall_date,
            Company.display_name,
            Company.normalized_name,
            RecallProduct.name,
        )
        .join(Source, Source.id == Recall.source_id)
        .join(
            RecallCompany,
            and_(RecallCompany.recall_id == Recall.id, RecallCompany.role == "manufacturer"),
        )
        .join(Company, Company.id == RecallCompany.company_id)
        .join(RecallProduct, RecallProduct.recall_id == Recall.id)
        .where(Recall.recall_date.is_not(None))
        .order_by(_order(seed, Recall.id), RecallCompany.id, RecallProduct.id)
        .limit(n * 4)
    )
    seen: set[int] = set()
    picked: list[tuple[Any, ...]] = []
    for row in rows.all():
        if row[0] in seen:
            continue
        seen.add(row[0])
        picked.append(tuple(row))
    return picked


def _description(product_name: str, company_normalized: str) -> str:
    brand = set(tokenize(company_normalized))
    return " ".join(t for t in content_terms(product_name) if t not in brand)


async def _product_cases(session: AsyncSession, seed: int, n: int) -> list[EvalCase]:
    cases: list[EvalCase] = []
    for _, code, sid, recall_date, display, normalized, product in await _product_rows(
        session, seed, n
    ):
        description = _description(product, normalized)
        if not description:
            continue
        cases.append(
            EvalCase(
                case_id=f"product-{code}-{sid}",
                kind="product",
                query={
                    "manufacturer": display,
                    "description": description,
                    "purchase_year": recall_date.year,
                },
                expected=[[code, sid]],
                label_method="derived: source recall only (incomplete; precision lower bound)",
            )
        )
        if len(cases) == n:
            break
    return cases


async def _negative_cases(session: AsyncSession, seed: int, n: int) -> list[EvalCase]:
    rng = random.Random(seed)  # noqa: S311 - reproducible sampling, not cryptography
    cases: list[EvalCase] = []
    while len(cases) < n // 2:
        model = f"QZ-{rng.randint(10_000, 99_999)}X"
        key = model.replace("-", "")
        present = await session.execute(
            select(func.count())
            .select_from(RecallIdentifier)
            .where(RecallIdentifier.normalized_value.startswith(key[:5], autoescape=True))
        )
        if present.scalar_one() == 0:
            cases.append(
                EvalCase(
                    case_id=f"negative-model-{key}",
                    kind="negative_model",
                    query={"model": model},
                    expected=[],
                    label_method="derived: identifier prefix verified absent from the data",
                )
            )
    rows = await _product_rows(session, seed + 1, n)
    for i, (_, code, sid, _, _, normalized, product) in enumerate(rows[: n - len(cases)]):
        description = _description(product, normalized)
        if description:
            cases.append(
                EvalCase(
                    case_id=f"negative-manufacturer-{code}-{sid}",
                    kind="negative_manufacturer",
                    query={
                        "manufacturer": FICTITIOUS_COMPANIES[i % len(FICTITIOUS_COMPANIES)],
                        "description": description,
                    },
                    expected=[],
                    label_method="derived: fictitious manufacturer; no recall can match it",
                )
            )
    return cases


async def build_dataset(
    session: AsyncSession, *, seed: int, identifiers: int, products: int, negatives: int
) -> list[EvalCase]:
    return [
        *await _identifier_cases(session, seed, identifiers),
        *await _product_cases(session, seed, products),
        *await _negative_cases(session, seed, negatives),
    ]


def write_dataset(path: Path, cases: list[EvalCase]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(case.to_json() + "\n" for case in cases), encoding="utf-8")


def read_dataset(path: Path) -> list[EvalCase]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [EvalCase.from_json(line) for line in lines if line.strip()]
