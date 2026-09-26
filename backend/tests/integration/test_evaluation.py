"""Evaluation dataset build + run against real PostgreSQL. All records are SYNTHETIC."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.evaluation.dataset import build_dataset, read_dataset, write_dataset
from recallgraph.evaluation.runner import run_evaluation
from recallgraph.ingestion.runner import run_ingestion
from recallgraph.normalization.service import normalize_cpsc_records, normalize_source_records
from tests.integration.test_nhtsa_ingestion import _adapter
from tests.integration.test_normalization import _store
from tests.integration.test_search_api import HEATER
from tests.test_cpsc_normalizer import synthetic_payload
from tests.test_nhtsa_normalizer import synthetic_nhtsa

pytestmark = pytest.mark.integration


@pytest.fixture
async def catalog(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _store(session_factory, [synthetic_payload(RecallID=1), HEATER])
    await normalize_cpsc_records(session_factory)
    await run_ingestion(session_factory, _adapter([synthetic_nhtsa()]))
    await normalize_source_records(session_factory, "nhtsa")


async def test_dataset_is_reproducible_and_labels_come_from_data(
    catalog: None, session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with session_factory() as session:
        first = await build_dataset(session, seed=7, identifiers=10, products=10, negatives=4)
        second = await build_dataset(session, seed=7, identifiers=10, products=10, negatives=4)

    assert first == second
    kinds = {c.kind for c in first}
    assert {"identifier", "product", "negative_model", "negative_manufacturer"} <= kinds
    af100 = next(c for c in first if c.case_id == "identifier-AF100X")
    assert af100.expected == [["cpsc", "1"]]
    assert all(c.expected == [] for c in first if c.kind.startswith("negative"))

    path = tmp_path / "eval.jsonl"
    write_dataset(path, first)
    assert read_dataset(path) == first


async def test_evaluation_reports_metrics_on_synthetic_catalog(
    catalog: None, session_factory: async_sessionmaker[AsyncSession], tmp_path: Path
) -> None:
    async with session_factory() as session:
        cases = await build_dataset(session, seed=7, identifiers=10, products=10, negatives=4)
    path = tmp_path / "eval.jsonl"
    write_dataset(path, cases)

    report = await run_evaluation(session_factory, path, limit=20)

    strict = report["metrics"]["strict"]
    assert strict["identifier"]["recall"] == 1.0
    assert strict["identifier"]["precision"] == 1.0
    assert strict["product"]["hit_at_1"] == 1.0
    assert strict["overall"]["false_positive_rate"] == 0.0
    assert report["dataset"]["cases"] == len(cases)
    assert len(report["dataset"]["sha256"]) == 64
