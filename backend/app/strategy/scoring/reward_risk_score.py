from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.strategy.scoring.component_models import ComponentScore, decimal_value
from app.strategy.scoring.score_config import StrategyScoreConfig


def score_reward_risk(risk_row: dict[str, Any], config: StrategyScoreConfig) -> ComponentScore:
    ratio = decimal_value(risk_row.get("reward_risk_ratio"))
    if ratio is None:
        return ComponentScore(
            "reward_risk",
            config.weights.reward_risk,
            "UNAVAILABLE",
            {"reward_risk_ratio": None},
            Decimal("0"),
            config.weights.reward_risk,
            "RISK_STRUCTURE_REWARD_RISK_UNAVAILABLE",
        )
    rules = config.reward_risk
    if ratio < rules.minimum:
        points = Decimal("0")
        band = "BELOW_1_5"
    elif ratio < rules.preferred:
        points = rules.minimum_points
        band = "R1_5_TO_2"
    elif ratio < rules.strong:
        points = rules.preferred_points
        band = "R2_TO_2_5"
    else:
        points = rules.strong_points
        band = "R2_5_OR_HIGHER"
    return ComponentScore(
        "reward_risk",
        config.weights.reward_risk,
        "AVAILABLE",
        {"reward_risk_ratio": ratio},
        points,
        config.weights.reward_risk,
        f"RISK_STRUCTURE_V1_1_{band}",
    )
