from __future__ import annotations

from datetime import date
from typing import Iterable

from app.research.temporal_validation.config import DEFAULT_TEMPORAL_CONFIG, SEALED
from app.research.temporal_validation.guard import ValidationAccessError, ValidationAccessGuard

STRUCTURAL_INSPECTION = "DATA_QUALITY_STRUCTURAL_INSPECTION"
PERFORMANCE_RESEARCH = "STRATEGY_PERFORMANCE_RESEARCH"


def validate_intraday_research_scope(
    trading_dates: Iterable[date], *, purpose: str
) -> dict[str, object]:
    dates = tuple(trading_dates)
    config = DEFAULT_TEMPORAL_CONFIG
    guard = ValidationAccessGuard()
    validation_dates = tuple(
        value
        for value in dates
        if config.validation_start <= value <= config.validation_terminal_date
    )
    outside_development = tuple(
        value
        for value in dates
        if not (config.development_start <= value <= config.development_end)
    )
    if purpose == PERFORMANCE_RESEARCH and outside_development:
        raise ValidationAccessError(
            "Intraday performance research is development-window only; validation remains SEALED"
        )
    if purpose not in {STRUCTURAL_INSPECTION, PERFORMANCE_RESEARCH}:
        raise ValueError(f"Unsupported intraday research purpose: {purpose}")
    return {
        "temporal_harness_version": config.harness_version,
        "temporal_protocol_version": config.protocol_version,
        "validation_state": guard.state,
        "validation_state_is_sealed": guard.state == SEALED,
        "purpose": purpose,
        "dates_inspected": [value.isoformat() for value in dates],
        "validation_dates_structural_only": [value.isoformat() for value in validation_dates],
        "performance_accessed": False,
    }
