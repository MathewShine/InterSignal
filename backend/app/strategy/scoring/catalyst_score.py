from __future__ import annotations

from decimal import Decimal

from app.strategy.scoring.component_models import ComponentScore
from app.strategy.scoring.score_config import StrategyScoreConfig


def score_catalyst(config: StrategyScoreConfig) -> ComponentScore:
    return ComponentScore(
        "catalyst",
        config.weights.catalyst,
        "UNAVAILABLE",
        {"status": config.catalyst_history_status},
        Decimal("0"),
        config.weights.catalyst,
        "NO_HISTORICAL_POINT_IN_TIME_CATALYST_LAYER",
    )
