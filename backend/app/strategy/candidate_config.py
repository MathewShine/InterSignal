from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

MOMENTUM_CANDIDATES_VERSION = "MOMENTUM_CANDIDATES_V1"


@dataclass(frozen=True, slots=True)
class PriceRules:
    minimum_price: Decimal = Decimal("100")
    preferred_max_price: Decimal = Decimal("5000")
    hard_max_price: Decimal = Decimal("7000")


@dataclass(frozen=True, slots=True)
class LiquidityRules:
    median_traded_value_20d_min: Decimal = Decimal("100000000")
    description: str = "20-day median traded value must be at least INR 10 crore per day."


@dataclass(frozen=True, slots=True)
class MomentumEvidenceRules:
    emerging_min_return_3d: Decimal = Decimal("0.005")
    emerging_min_return_5d: Decimal = Decimal("0.015")
    emerging_min_return_10d: Decimal = Decimal("-0.010")
    emerging_min_up_days_ratio_10: Decimal = Decimal("0.50")
    emerging_min_evidence_count: int = 4
    confirmed_min_return_5d: Decimal = Decimal("0.025")
    confirmed_min_return_10d: Decimal = Decimal("0.040")
    confirmed_min_return_20d: Decimal = Decimal("0.060")
    confirmed_min_up_days_ratio_10: Decimal = Decimal("0.60")
    confirmed_min_up_days_ratio_20: Decimal = Decimal("0.55")
    confirmed_min_evidence_count: int = 5


@dataclass(frozen=True, slots=True)
class RelativeVolumeRules:
    emerging_threshold: Decimal = Decimal("1.20")
    confirmed_threshold: Decimal = Decimal("1.50")
    future_research_thresholds: tuple[Decimal, ...] = (Decimal("1.20"), Decimal("1.30"), Decimal("1.50"))


@dataclass(frozen=True, slots=True)
class BreakoutContextRules:
    testing_20d_high_distance: Decimal = Decimal("-0.010")
    approaching_20d_high_distance: Decimal = Decimal("-0.040")


@dataclass(frozen=True, slots=True)
class ExtensionRules:
    elevated_return_1d_atr_multiple: Decimal = Decimal("1.30")
    extended_return_1d_atr_multiple: Decimal = Decimal("2.00")
    extreme_return_1d_atr_multiple: Decimal = Decimal("3.00")
    elevated_return_5d_atr_multiple: Decimal = Decimal("3.00")
    extended_return_5d_atr_multiple: Decimal = Decimal("5.00")
    extreme_return_5d_atr_multiple: Decimal = Decimal("8.00")
    elevated_distance_from_sma20: Decimal = Decimal("0.080")
    extended_distance_from_sma20: Decimal = Decimal("0.120")
    extreme_distance_from_sma20: Decimal = Decimal("0.180")


@dataclass(frozen=True, slots=True)
class VolatilityRules:
    low_atr_percent: Decimal = Decimal("0.0075")
    high_atr_percent: Decimal = Decimal("0.0500")
    extreme_atr_percent: Decimal = Decimal("0.1000")


@dataclass(frozen=True, slots=True)
class MomentumCandidateConfig:
    candidate_version: str = MOMENTUM_CANDIDATES_VERSION
    price: PriceRules = PriceRules()
    liquidity: LiquidityRules = LiquidityRules()
    momentum: MomentumEvidenceRules = MomentumEvidenceRules()
    relative_volume: RelativeVolumeRules = RelativeVolumeRules()
    breakout: BreakoutContextRules = BreakoutContextRules()
    extension: ExtensionRules = ExtensionRules()
    volatility: VolatilityRules = VolatilityRules()
    required_feature_fields: tuple[str, ...] = (
        "return_1d",
        "return_3d",
        "return_5d",
        "return_10d",
        "return_20d",
        "relative_volume_5d",
        "relative_volume_20d",
        "up_days_ratio_10",
        "up_days_ratio_20",
        "median_traded_value_20d",
        "atr_percent_14",
        "distance_to_prior_20d_high_pct",
        "above_prior_20d_high",
        "intraday_high_above_prior_20d_high",
        "prior_high_20d",
    )
    ranking_components: tuple[str, ...] = (
        "momentum",
        "relative_volume",
        "benchmark_relative_strength",
        "breakout_context",
    )
    allowed_series: tuple[str, ...] = ("EQ", "")
    primary_benchmark_id: str = "NIFTY_500"
    sector_required: bool = False
    notes: str = "Initial research defaults only; no parameter optimization has been performed."
    extra_metadata: dict[str, str] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return json_ready(asdict(self))

    def config_hash(self) -> str:
        payload = json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


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
