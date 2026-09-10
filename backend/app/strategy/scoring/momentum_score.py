from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.strategy.scoring.component_models import ComponentScore, decimal_value
from app.strategy.scoring.score_config import StrategyScoreConfig

MOMENTUM_FIELDS = (
    "return_5d",
    "return_10d",
    "return_20d",
    "up_days_ratio_10",
    "up_days_ratio_20",
)


def score_momentum(candidate_row: dict[str, Any], config: StrategyScoreConfig) -> ComponentScore:
    values = {field: decimal_value(candidate_row.get(field)) for field in MOMENTUM_FIELDS}
    if any(value is None for value in values.values()):
        return ComponentScore(
            "momentum",
            config.weights.momentum,
            "UNAVAILABLE",
            values,
            Decimal("0"),
            config.weights.momentum,
            "CANDIDATE_MOMENTUM_INPUT_INCOMPLETE",
        )
    rules = config.momentum
    parts = {
        "return_5d": two_tier(
            values["return_5d"],
            rules.return_5d_emerging,
            rules.return_5d_confirmed,
            rules.return_5d_emerging_points,
            rules.return_5d_confirmed_points,
        ),
        "return_10d": two_tier(
            values["return_10d"],
            rules.return_10d_emerging,
            rules.return_10d_confirmed,
            rules.return_10d_emerging_points,
            rules.return_10d_confirmed_points,
        ),
        "return_20d": two_tier(
            values["return_20d"],
            rules.return_20d_positive,
            rules.return_20d_confirmed,
            rules.return_20d_positive_points,
            rules.return_20d_confirmed_points,
        ),
        "up_days_ratio_10": two_tier(
            values["up_days_ratio_10"],
            rules.up_days_ratio_10_emerging,
            rules.up_days_ratio_10_confirmed,
            rules.up_days_ratio_10_emerging_points,
            rules.up_days_ratio_10_confirmed_points,
        ),
        "up_days_ratio_20": (
            rules.up_days_ratio_20_confirmed_points
            if values["up_days_ratio_20"] >= rules.up_days_ratio_20_confirmed
            else Decimal("0")
        ),
    }
    points = min(sum(parts.values(), Decimal("0")), config.weights.momentum)
    basis = ";".join(f"{name}={format(value, 'f')}" for name, value in parts.items())
    return ComponentScore(
        "momentum",
        config.weights.momentum,
        "AVAILABLE",
        values,
        points,
        config.weights.momentum,
        f"CANDIDATE_V1_MULTI_DAY_THRESHOLDS:{basis}",
    )


def two_tier(
    value: Decimal,
    lower_threshold: Decimal,
    upper_threshold: Decimal,
    lower_points: Decimal,
    upper_points: Decimal,
) -> Decimal:
    if value >= upper_threshold:
        return upper_points
    if value >= lower_threshold:
        return lower_points
    return Decimal("0")
