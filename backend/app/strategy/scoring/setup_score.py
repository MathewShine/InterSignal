from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.strategy.scoring.component_models import ComponentScore
from app.strategy.scoring.score_config import StrategyScoreConfig, points_mapping


def score_setup(setup_row: dict[str, Any], config: StrategyScoreConfig) -> ComponentScore:
    quality = str(setup_row.get("setup_quality", "")).upper()
    mapping = points_mapping(config.setup.points)
    if quality not in mapping:
        return ComponentScore(
            "setup",
            config.weights.setup,
            "UNAVAILABLE",
            {"setup_quality": quality or None},
            Decimal("0"),
            config.weights.setup,
            "SETUP_QUALITY_UNAVAILABLE",
        )
    return ComponentScore(
        "setup",
        config.weights.setup,
        "AVAILABLE",
        {"setup_quality": quality},
        mapping[quality],
        config.weights.setup,
        f"UPSTREAM_SETUP_QUALITY_{quality}",
    )
