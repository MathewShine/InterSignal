from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

STRATEGY_SCORE_VERSION = "STRATEGY_SCORE_V1"
SWING_DAILY_EOD_PROFILE = "SWING_DAILY_EOD_V1"
FUTURE_INTRADAY_SCORE_PROFILE = "INTRADAY_SCORE_V1"


@dataclass(frozen=True, slots=True)
class ComponentWeights:
    setup: Decimal = Decimal("20")
    momentum: Decimal = Decimal("20")
    rvol: Decimal = Decimal("15")
    relative_strength: Decimal = Decimal("15")
    regime: Decimal = Decimal("10")
    sector: Decimal = Decimal("10")
    catalyst: Decimal = Decimal("5")
    reward_risk: Decimal = Decimal("5")

    def total(self) -> Decimal:
        return sum(asdict(self).values(), Decimal("0"))


@dataclass(frozen=True, slots=True)
class ScoreThresholds:
    minimum_score_coverage_pct: Decimal = Decimal("80")
    entry_eligible: Decimal = Decimal("80")
    high_conviction: Decimal = Decimal("90")
    diagnostic_thresholds: tuple[Decimal, ...] = (
        Decimal("75"),
        Decimal("80"),
        Decimal("85"),
        Decimal("90"),
        Decimal("95"),
    )


@dataclass(frozen=True, slots=True)
class SetupScoreRules:
    points: tuple[tuple[str, Decimal], ...] = (
        ("STRONG", Decimal("20")),
        ("VALID", Decimal("16")),
        ("WATCH", Decimal("8")),
        ("POOR", Decimal("0")),
    )


@dataclass(frozen=True, slots=True)
class MomentumScoreRules:
    return_5d_emerging: Decimal = Decimal("0.015")
    return_5d_confirmed: Decimal = Decimal("0.025")
    return_5d_emerging_points: Decimal = Decimal("3")
    return_5d_confirmed_points: Decimal = Decimal("4")
    return_10d_emerging: Decimal = Decimal("-0.010")
    return_10d_confirmed: Decimal = Decimal("0.040")
    return_10d_emerging_points: Decimal = Decimal("2")
    return_10d_confirmed_points: Decimal = Decimal("4")
    return_20d_positive: Decimal = Decimal("0")
    return_20d_confirmed: Decimal = Decimal("0.060")
    return_20d_positive_points: Decimal = Decimal("2")
    return_20d_confirmed_points: Decimal = Decimal("4")
    up_days_ratio_10_emerging: Decimal = Decimal("0.50")
    up_days_ratio_10_confirmed: Decimal = Decimal("0.60")
    up_days_ratio_10_emerging_points: Decimal = Decimal("3")
    up_days_ratio_10_confirmed_points: Decimal = Decimal("4")
    up_days_ratio_20_confirmed: Decimal = Decimal("0.55")
    up_days_ratio_20_confirmed_points: Decimal = Decimal("4")


@dataclass(frozen=True, slots=True)
class RelativeVolumeScoreRules:
    points: tuple[tuple[str, Decimal], ...] = (
        ("EXCEPTIONAL", Decimal("15")),
        ("STRONG", Decimal("13")),
        ("GOOD", Decimal("10")),
        ("NORMAL", Decimal("6")),
        ("WEAK", Decimal("0")),
    )


@dataclass(frozen=True, slots=True)
class RelativeStrengthScoreRules:
    points: tuple[tuple[str, Decimal], ...] = (
        ("STRONG", Decimal("15")),
        ("POSITIVE", Decimal("11")),
        ("NEUTRAL", Decimal("6")),
        ("WEAK", Decimal("0")),
    )


@dataclass(frozen=True, slots=True)
class RegimeScoreRules:
    points: tuple[tuple[str, Decimal], ...] = (
        ("BULLISH", Decimal("10")),
        ("NEUTRAL", Decimal("5")),
        ("BEARISH", Decimal("0")),
    )


@dataclass(frozen=True, slots=True)
class RewardRiskScoreRules:
    minimum: Decimal = Decimal("1.50")
    preferred: Decimal = Decimal("2.00")
    strong: Decimal = Decimal("2.50")
    minimum_points: Decimal = Decimal("3")
    preferred_points: Decimal = Decimal("4")
    strong_points: Decimal = Decimal("5")


@dataclass(frozen=True, slots=True)
class StrategyScoreConfig:
    score_version: str = STRATEGY_SCORE_VERSION
    score_profile: str = SWING_DAILY_EOD_PROFILE
    availability: str = "DAILY_EOD"
    decision_use: str = "NEXT_SESSION_SWING_LONG_RESEARCH"
    weights: ComponentWeights = ComponentWeights()
    thresholds: ScoreThresholds = ScoreThresholds()
    setup: SetupScoreRules = SetupScoreRules()
    momentum: MomentumScoreRules = MomentumScoreRules()
    rvol: RelativeVolumeScoreRules = RelativeVolumeScoreRules()
    relative_strength: RelativeStrengthScoreRules = RelativeStrengthScoreRules()
    regime: RegimeScoreRules = RegimeScoreRules()
    reward_risk: RewardRiskScoreRules = RewardRiskScoreRules()
    sector_history_status: str = "UNAVAILABLE_POINT_IN_TIME_MAPPING"
    catalyst_history_status: str = "UNAVAILABLE_HISTORICAL_CATALYST_LAYER"
    normalized_score_usage: str = "DIAGNOSTIC_ONLY"
    trade_signal_status: str = "NOT_GENERATED"
    execution_status: str = "NOT_IMPLEMENTED"
    notes: str = (
        "Deterministic evidence-ranking score only. Gates precede score; missing sector and "
        "catalyst evidence is not rescaled or fabricated for eligibility."
    )

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))

    def config_hash(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def points_mapping(values: tuple[tuple[str, Decimal], ...]) -> dict[str, Decimal]:
    return dict(values)


def json_ready(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [json_ready(item) for item in value]
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    return value
