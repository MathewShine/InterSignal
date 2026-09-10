from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.strategy.scoring.component_models import ComponentScore
from app.strategy.scoring.score_config import StrategyScoreConfig, points_mapping


def score_regime(risk_row: dict[str, Any], entry_row: dict[str, Any], config: StrategyScoreConfig) -> ComponentScore:
    state = str(risk_row.get("regime_state", "")).upper()
    raw_input = {
        "regime_state": state or None,
        "regime_confidence_state": entry_row.get("regime_confidence_state"),
        "regime_confidence_score": entry_row.get("regime_confidence_score"),
    }
    mapping = points_mapping(config.regime.points)
    if state not in mapping:
        return ComponentScore(
            "regime",
            config.weights.regime,
            "UNAVAILABLE",
            raw_input,
            Decimal("0"),
            config.weights.regime,
            "MARKET_REGIME_V1_UNAVAILABLE_CONSERVATIVE",
        )
    return ComponentScore(
        "regime",
        config.weights.regime,
        "AVAILABLE",
        raw_input,
        mapping[state],
        config.weights.regime,
        f"MARKET_REGIME_V1_{state};CONFIDENCE_CONTEXT_ONLY",
    )
