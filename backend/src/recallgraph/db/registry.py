"""Imports every model module so Base.metadata is complete (Alembic autogenerate/check)."""

from recallgraph.provenance import models as provenance_models

__all__ = ["provenance_models"]
