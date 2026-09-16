from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence, Set
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


HASH_VERSION = "INTERSIGNAL_CANONICAL_SHA256_V1"


def _normalized_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Canonical timestamps must be timezone-aware")
    utc = value.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_for_hash(value: Any) -> Any:
    """Convert supported domain values to deterministic JSON-compatible values."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="python")
    if isinstance(value, datetime):
        return _normalized_datetime(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return normalize_for_hash(value.value)
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, Mapping):
        return {
            str(key): normalize_for_hash(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, Set):
        normalized = [normalize_for_hash(item) for item in value]
        return sorted(
            normalized,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [normalize_for_hash(item) for item in value]
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("NaN and infinity are not canonical JSON values")
    return value


def canonical_json(
    value: Any, *, exclude_fields: frozenset[str] = frozenset()
) -> str:
    normalized = normalize_for_hash(value)
    if exclude_fields:
        if not isinstance(normalized, dict):
            raise TypeError("exclude_fields requires a top-level object")
        normalized = {
            key: item for key, item in normalized.items() if key not in exclude_fields
        }
    return json.dumps(
        normalized,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_hash(
    value: Any, *, exclude_fields: frozenset[str] = frozenset()
) -> str:
    payload = canonical_json(value, exclude_fields=exclude_fields).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def deterministic_id(prefix: str, *identity_parts: Any) -> str:
    clean_prefix = prefix.strip().upper()
    if not clean_prefix:
        raise ValueError("ID prefix is required")
    digest = canonical_hash(
        {"hash_version": HASH_VERSION, "identity_parts": identity_parts}
    )
    return f"{clean_prefix}-{digest[:24]}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = (
    "HASH_VERSION",
    "canonical_hash",
    "canonical_json",
    "deterministic_id",
    "file_sha256",
    "normalize_for_hash",
)
