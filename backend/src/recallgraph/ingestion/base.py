"""The contract every authoritative source adapter implements."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

from recallgraph.provenance.repository import RawRecordInput, SourceSpec


@dataclass(frozen=True, slots=True)
class Batch:
    """One fetched unit of work (a date window, a page). Committed atomically."""

    label: str
    records: list[RawRecordInput]


class SourceAdapter(Protocol):
    spec: SourceSpec

    def parameters(self) -> dict[str, Any]:
        """What this run will fetch; stored on the ingestion run for provenance."""
        ...

    def batches(self) -> AsyncIterator[Batch]:
        """Fetch lazily, one batch at a time."""
        ...
