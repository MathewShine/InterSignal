from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

DAILY_SETUP_EVALUATION_VERSION = "DAILY_SETUP_EVALUATION_V1"


@dataclass(frozen=True, slots=True)
class BreakoutStateRules:
    approaching_high_tolerance: Decimal = Decimal("-0.040")
    testing_high_tolerance: Decimal = Decimal("-0.010")
    close_acceptance_distance: Decimal = Decimal("0.003")
    failed_break_close_distance: Decimal = Decimal("-0.003")


@dataclass(frozen=True, slots=True)
class LevelQualityRules:
    touch_tolerance: Decimal = Decimal("0.005")
    good_min_touches: int = 2
    strong_min_touches: int = 3
    recent_level_max_sessions: int = 20
    stale_level_min_sessions: int = 45


@dataclass(frozen=True, slots=True)
class ConsolidationRules:
    very_tight_range_20d: Decimal = Decimal("0.080")
    tight_range_20d: Decimal = Decimal("0.120")
    moderate_range_20d: Decimal = Decimal("0.180")
    loose_range_20d: Decimal = Decimal("0.250")
    strong_atr_contraction: Decimal = Decimal("0.750")
    moderate_atr_contraction: Decimal = Decimal("0.950")
    price_near_high_tolerance: Decimal = Decimal("-0.040")


@dataclass(frozen=True, slots=True)
class AcceptanceRules:
    weak_close_location: Decimal = Decimal("0.450")
    moderate_close_location: Decimal = Decimal("0.600")
    strong_close_location: Decimal = Decimal("0.750")
    contained_upper_wick_pct: Decimal = Decimal("0.012")
    large_upper_wick_pct: Decimal = Decimal("0.025")
    meaningful_body_pct: Decimal = Decimal("0.004")


@dataclass(frozen=True, slots=True)
class CandleQualityRules:
    poor_close_location: Decimal = Decimal("0.350")
    fair_close_location: Decimal = Decimal("0.450")
    good_close_location: Decimal = Decimal("0.600")
    strong_close_location: Decimal = Decimal("0.750")
    tiny_body_pct: Decimal = Decimal("0.001")
    meaningful_body_pct: Decimal = Decimal("0.004")
    large_upper_wick_pct: Decimal = Decimal("0.025")
    contained_upper_wick_pct: Decimal = Decimal("0.012")


@dataclass(frozen=True, slots=True)
class VolumeConfirmationRules:
    normal_threshold: Decimal = Decimal("1.00")
    good_threshold: Decimal = Decimal("1.20")
    strong_threshold: Decimal = Decimal("1.50")
    exceptional_threshold: Decimal = Decimal("2.00")


@dataclass(frozen=True, slots=True)
class BenchmarkRelativeStrengthRules:
    positive_threshold: Decimal = Decimal("0")
    strong_5d_threshold: Decimal = Decimal("0.020")
    strong_20d_threshold: Decimal = Decimal("0.030")
    weak_5d_threshold: Decimal = Decimal("-0.010")
    weak_20d_threshold: Decimal = Decimal("-0.020")


@dataclass(frozen=True, slots=True)
class ExtensionRiskRules:
    moderate_return_1d_atr_multiple: Decimal = Decimal("1.30")
    high_return_1d_atr_multiple: Decimal = Decimal("2.00")
    extreme_return_1d_atr_multiple: Decimal = Decimal("3.00")
    moderate_return_5d_atr_multiple: Decimal = Decimal("3.00")
    high_return_5d_atr_multiple: Decimal = Decimal("5.00")
    extreme_return_5d_atr_multiple: Decimal = Decimal("8.00")
    moderate_sma20_distance: Decimal = Decimal("0.080")
    high_sma20_distance: Decimal = Decimal("0.120")
    extreme_sma20_distance: Decimal = Decimal("0.180")
    gap_fade_threshold: Decimal = Decimal("0.020")


@dataclass(frozen=True, slots=True)
class ReclaimRules:
    shallow_depth: Decimal = Decimal("0.005")
    moderate_depth: Decimal = Decimal("0.015")


@dataclass(frozen=True, slots=True)
class ResistanceRules:
    high_proximity: Decimal = Decimal("0.010")
    moderate_proximity: Decimal = Decimal("0.030")
    low_proximity: Decimal = Decimal("0.070")
    high_52w_at_tolerance: Decimal = Decimal("0.005")
    high_52w_near_tolerance: Decimal = Decimal("0.030")


@dataclass(frozen=True, slots=True)
class SetupEligibilityRules:
    block_extreme_extension: bool = True
    block_possible_false_breakout: bool = True
    emerging_allows_approaching_or_testing: bool = True
    confirmed_requires_close_or_continuation: bool = True


@dataclass(frozen=True, slots=True)
class DailySetupEvaluationConfig:
    setup_version: str = DAILY_SETUP_EVALUATION_VERSION
    breakout: BreakoutStateRules = BreakoutStateRules()
    level_quality: LevelQualityRules = LevelQualityRules()
    consolidation: ConsolidationRules = ConsolidationRules()
    acceptance: AcceptanceRules = AcceptanceRules()
    candle: CandleQualityRules = CandleQualityRules()
    volume: VolumeConfirmationRules = VolumeConfirmationRules()
    benchmark_rs: BenchmarkRelativeStrengthRules = BenchmarkRelativeStrengthRules()
    extension: ExtensionRiskRules = ExtensionRiskRules()
    reclaim: ReclaimRules = ReclaimRules()
    resistance: ResistanceRules = ResistanceRules()
    eligibility: SetupEligibilityRules = SetupEligibilityRules()
    setup_availability: str = "EOD"
    decision_input_time: str = "NEXT_SESSION_DECISION_INPUT"
    notes: str = "Baseline deterministic setup evaluation defaults only; no outcome optimization."

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
