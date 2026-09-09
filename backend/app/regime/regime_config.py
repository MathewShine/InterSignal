from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

MARKET_REGIME_VERSION = "MARKET_REGIME_V1"


@dataclass(frozen=True, slots=True)
class RegimeWeights:
    nifty_trend: Decimal = Decimal("30")
    nifty500_breadth: Decimal = Decimal("20")
    sector_participation: Decimal = Decimal("15")
    global_gift: Decimal = Decimal("15")
    india_vix: Decimal = Decimal("10")
    intraday_confirmation: Decimal = Decimal("10")


@dataclass(frozen=True, slots=True)
class RegimeClassificationRules:
    bullish_min: Decimal = Decimal("30")
    bearish_max: Decimal = Decimal("-30")
    minimum_available_weight_pct: Decimal = Decimal("60")


@dataclass(frozen=True, slots=True)
class NiftyTrendRules:
    positive_return_5d: Decimal = Decimal("0.010")
    strong_positive_return_5d: Decimal = Decimal("0.020")
    negative_return_5d: Decimal = Decimal("-0.010")
    strong_negative_return_5d: Decimal = Decimal("-0.020")
    positive_return_20d: Decimal = Decimal("0.020")
    strong_positive_return_20d: Decimal = Decimal("0.040")
    negative_return_20d: Decimal = Decimal("-0.020")
    strong_negative_return_20d: Decimal = Decimal("-0.040")
    sma_slope_positive: Decimal = Decimal("0.003")
    sma_slope_negative: Decimal = Decimal("-0.003")
    minimum_metric_coverage_pct: Decimal = Decimal("50")


@dataclass(frozen=True, slots=True)
class BreadthRules:
    minimum_breadth_coverage_pct: Decimal = Decimal("65")
    minimum_usable_members: int = 300
    bullish_pct: Decimal = Decimal("52")
    strongly_bullish_pct: Decimal = Decimal("60")
    bearish_pct: Decimal = Decimal("48")
    strongly_bearish_pct: Decimal = Decimal("40")


@dataclass(frozen=True, slots=True)
class SectorParticipationRules:
    minimum_sector_coverage_pct: Decimal = Decimal("50")
    minimum_available_sector_indexes: int = 10
    bullish_pct: Decimal = Decimal("52")
    strongly_bullish_pct: Decimal = Decimal("60")
    bearish_pct: Decimal = Decimal("48")
    strongly_bearish_pct: Decimal = Decimal("40")


@dataclass(frozen=True, slots=True)
class IndiaVixRules:
    risk_on_level: Decimal = Decimal("13")
    risk_off_level: Decimal = Decimal("18")
    strongly_risk_off_level: Decimal = Decimal("22")
    falling_5d_pct: Decimal = Decimal("-0.050")
    rising_5d_pct: Decimal = Decimal("0.050")


@dataclass(frozen=True, slots=True)
class ConfidenceRules:
    high_threshold: Decimal = Decimal("75")
    medium_threshold: Decimal = Decimal("50")
    availability_weight: Decimal = Decimal("0.45")
    agreement_weight: Decimal = Decimal("0.30")
    coverage_weight: Decimal = Decimal("0.25")
    partial_membership_penalty: Decimal = Decimal("5")


@dataclass(frozen=True, slots=True)
class MarketRegimeConfig:
    regime_version: str = MARKET_REGIME_VERSION
    weights: RegimeWeights = RegimeWeights()
    classification: RegimeClassificationRules = RegimeClassificationRules()
    trend: NiftyTrendRules = NiftyTrendRules()
    breadth: BreadthRules = BreadthRules()
    sector: SectorParticipationRules = SectorParticipationRules()
    india_vix: IndiaVixRules = IndiaVixRules()
    confidence: ConfidenceRules = ConfidenceRules()
    regime_availability: str = "DAILY_EOD_REGIME"
    decision_use: str = "NEXT_SESSION_CONTEXT"
    notes: str = "Historical EOD market-regime foundation; unavailable components are not treated as neutral evidence."

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

