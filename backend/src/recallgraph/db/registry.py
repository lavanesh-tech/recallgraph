"""Imports every model module so Base.metadata is complete (Alembic autogenerate/check)."""

from recallgraph.auth import models as auth_models
from recallgraph.inventory import models as inventory_models
from recallgraph.provenance import models as provenance_models
from recallgraph.recalls import models as recall_models

__all__ = ["auth_models", "inventory_models", "provenance_models", "recall_models"]
