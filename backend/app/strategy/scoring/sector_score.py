from __future__ import annotations

from decimal import Decimal

from app.strategy.scoring.component_models import ComponentScore
from app.strategy.scoring.score_config import StrategyScoreConfig


def score_sector(config: StrategyScoreConfig) -> ComponentScore:
    return ComponentScore(
        "sector",
        config.weights.sector,
        "UNAVAILABLE",
        {"status": config.sector_history_status},
        Decimal("0"),
        config.weights.sector,
        "NO_POINT_IN_TIME_STOCK_TO_SECTOR_MAPPING",
    )
