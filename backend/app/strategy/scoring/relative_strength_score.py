from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.strategy.scoring.component_models import ComponentScore
from app.strategy.scoring.score_config import StrategyScoreConfig, points_mapping


def score_relative_strength(setup_row: dict[str, Any], config: StrategyScoreConfig) -> ComponentScore:
    descriptor = str(setup_row.get("benchmark_rs_context", "")).upper()
    raw_input = {
        "benchmark_rs_context": descriptor or None,
        "relative_return_5d_vs_nifty500": setup_row.get("relative_return_5d_vs_nifty500"),
        "relative_return_20d_vs_nifty500": setup_row.get("relative_return_20d_vs_nifty500"),
    }
    mapping = points_mapping(config.relative_strength.points)
    if descriptor not in mapping:
        return ComponentScore(
            "relative_strength",
            config.weights.relative_strength,
            "UNAVAILABLE",
            raw_input,
            Decimal("0"),
            config.weights.relative_strength,
            "UPSTREAM_BENCHMARK_RS_UNAVAILABLE",
        )
    return ComponentScore(
        "relative_strength",
        config.weights.relative_strength,
        "AVAILABLE",
        raw_input,
        mapping[descriptor],
        config.weights.relative_strength,
        f"UPSTREAM_BENCHMARK_RS_{descriptor}",
    )
