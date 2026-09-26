"""Deterministic content hashing of source payloads (detects unchanged vs. changed records)."""

import hashlib
import json
from typing import Any


def canonical_json(payload: Any) -> str:
    """Key-order-independent, whitespace-free JSON. NaN/Infinity are rejected (not valid JSON)."""
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )


def content_hash(payload: Any) -> str:
    """SHA-256 hex digest (64 chars) of the canonical JSON form."""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
