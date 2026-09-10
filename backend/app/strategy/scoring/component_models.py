from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

AVAILABILITY_STATES = ("AVAILABLE", "UNAVAILABLE", "NOT_APPLICABLE", "BLOCKED_UPSTREAM")


@dataclass(frozen=True, slots=True)
class ComponentScore:
    component_name: str
    weight: Decimal
    availability_status: str
    raw_input: dict[str, Any]
    component_points: Decimal
    component_max_points: Decimal
    mapping_basis: str

    def __post_init__(self) -> None:
        if self.availability_status not in AVAILABILITY_STATES:
            raise ValueError(f"Unsupported component availability: {self.availability_status}")
        if self.component_points < 0 or self.component_points > self.component_max_points:
            raise ValueError(f"{self.component_name} points are outside the component bounds")

    @property
    def available_weight(self) -> Decimal:
        return self.weight if self.availability_status == "AVAILABLE" else Decimal("0")

    def output_fields(self, prefix: str) -> dict[str, Any]:
        return {
            f"{prefix}_points": self.component_points,
            f"{prefix}_max_points": self.component_max_points,
            f"{prefix}_availability": self.availability_status,
            f"{prefix}_basis": self.mapping_basis,
        }

    def diagnostic_record(self) -> dict[str, Any]:
        return {
            "component_name": self.component_name,
            "weight": self.weight,
            "availability_status": self.availability_status,
            "raw_input": json.dumps(json_safe(self.raw_input), sort_keys=True, separators=(",", ":")),
            "component_points": self.component_points,
            "component_max_points": self.component_max_points,
            "mapping_basis": self.mapping_basis,
        }


def decimal_value(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value
