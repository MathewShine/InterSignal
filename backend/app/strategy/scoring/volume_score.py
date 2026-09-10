from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.strategy.scoring.component_models import ComponentScore
from app.strategy.scoring.score_config import StrategyScoreConfig, points_mapping


def score_relative_volume(setup_row: dict[str, Any], config: StrategyScoreConfig) -> ComponentScore:
    descriptor = str(setup_row.get("volume_confirmation", "")).upper()
    raw_input = {
        "volume_confirmation": descriptor or None,
        "relative_volume_20d": setup_row.get("relative_volume_20d"),
        "relative_volume_5d": setup_row.get("relative_volume_5d"),
    }
    mapping = points_mapping(config.rvol.points)
    if descriptor not in mapping:
        return ComponentScore(
            "rvol",
            config.weights.rvol,
            "UNAVAILABLE",
            raw_input,
            Decimal("0"),
            config.weights.rvol,
            "UPSTREAM_VOLUME_CONFIRMATION_UNAVAILABLE",
        )
    return ComponentScore(
        "rvol",
        config.weights.rvol,
        "AVAILABLE",
        raw_input,
        mapping[descriptor],
        config.weights.rvol,
        f"UPSTREAM_VOLUME_CONFIRMATION_{descriptor}",
    )
