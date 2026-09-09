from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable

from app.strategy.setup_config import DailySetupEvaluationConfig


@dataclass(frozen=True, slots=True)
class AdjustedDailyOhlc:
    trading_date: str
    symbol: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None


def classify_breakout_state(values: dict[str, Any], config: DailySetupEvaluationConfig) -> str:
    prior_high = values.get("prior_high_20d")
    close = values.get("close")
    high = values.get("high")
    distance = values.get("distance_to_prior_20d_high_pct")
    above_prior = values.get("above_prior_20d_high")
    intraday_above = values.get("intraday_high_above_prior_20d_high")

    if prior_high is None or (close is None and distance is None):
        return "UNAVAILABLE"

    close_above = above_prior is True or (distance is not None and distance > Decimal("0"))
    high_above = intraday_above is True or (
        prior_high is not None and high is not None and high > prior_high
    )

    if close_above:
        if is_close_accepted(values, config):
            return "CLOSE_ACCEPTED"
        return "CLOSE_ABOVE"

    if high_above:
        close_distance = distance
        if close_distance is None and close is not None and prior_high and prior_high > 0:
            close_distance = (close - prior_high) / prior_high
        if (
            close_distance is not None
            and close_distance <= config.breakout.failed_break_close_distance
        ) or weak_rejection_candle(values, config):
            return "FAILED_BREAK"
        return "INTRADAY_BREAK_ONLY"

    if distance is None:
        return "UNAVAILABLE"
    if distance >= config.breakout.testing_high_tolerance:
        return "TESTING"
    if distance >= config.breakout.approaching_high_tolerance:
        return "APPROACHING"
    return "NOT_NEAR_LEVEL"


def is_close_accepted(values: dict[str, Any], config: DailySetupEvaluationConfig) -> bool:
    distance = values.get("distance_to_prior_20d_high_pct")
    close_location = values.get("close_location_value")
    upper_wick = values.get("upper_wick_pct")
    max_rvol = max_decimal(values.get("relative_volume_20d"), values.get("relative_volume_5d"))
    if distance is None or close_location is None:
        return False
    if distance < config.breakout.close_acceptance_distance:
        return False
    if close_location < config.acceptance.moderate_close_location:
        return False
    if upper_wick is not None and upper_wick > config.acceptance.large_upper_wick_pct:
        return False
    return max_rvol is not None and max_rvol >= config.volume.good_threshold


def classify_level_quality(
    values: dict[str, Any],
    prior_bars: list[AdjustedDailyOhlc],
    config: DailySetupEvaluationConfig,
) -> tuple[str, dict[str, Any]]:
    prior_high = values.get("prior_high_20d")
    if prior_high is None or prior_high <= 0:
        return "WEAK", {"reason": "prior_high_20d_unavailable", "touches": 0, "days_since_prior_high": ""}

    recent_bars = prior_bars[-20:]
    touches = 0
    days_since_prior_high = ""
    for offset, bar in enumerate(reversed(recent_bars), start=1):
        if bar.high is None:
            continue
        distance = abs(bar.high - prior_high) / prior_high
        if distance <= config.level_quality.touch_tolerance:
            touches += 1
            if days_since_prior_high == "":
                days_since_prior_high = offset

    distance_to_level = values.get("distance_to_prior_20d_high_pct")
    near_level = distance_to_level is not None and distance_to_level >= config.consolidation.price_near_high_tolerance
    range_width = values.get("range_width_20d_pct")
    compressed = range_width is not None and range_width <= config.consolidation.tight_range_20d

    if (
        touches >= config.level_quality.strong_min_touches
        and days_since_prior_high != ""
        and int(days_since_prior_high) <= config.level_quality.recent_level_max_sessions
        and near_level
        and compressed
    ):
        quality = "STRONG"
    elif touches >= config.level_quality.good_min_touches and near_level:
        quality = "GOOD"
    elif days_since_prior_high != "" and int(days_since_prior_high) < config.level_quality.stale_level_min_sessions:
        quality = "FAIR"
    else:
        quality = "WEAK"

    return quality, {
        "touches": touches,
        "days_since_prior_high": days_since_prior_high,
        "near_level": near_level,
        "range_width_20d_pct": range_width,
    }


def classify_consolidation(
    values: dict[str, Any],
    config: DailySetupEvaluationConfig,
) -> tuple[str, str, set[str]]:
    range_5d = values.get("range_width_5d_pct")
    range_10d = values.get("range_width_10d_pct")
    range_20d = values.get("range_width_20d_pct")
    atr_contraction = values.get("atr_contraction_ratio")
    distance = values.get("distance_to_prior_20d_high_pct")
    evidence: set[str] = set()

    if range_20d is None:
        return "NONE", "WEAK", evidence

    if range_20d <= config.consolidation.very_tight_range_20d:
        state = "VERY_TIGHT"
    elif range_20d <= config.consolidation.tight_range_20d:
        state = "TIGHT"
    elif range_20d <= config.consolidation.moderate_range_20d:
        state = "MODERATE"
    elif range_20d <= config.consolidation.loose_range_20d:
        state = "LOOSE"
    else:
        state = "NONE"

    if atr_contraction is not None and atr_contraction <= config.consolidation.strong_atr_contraction:
        evidence.add("LOWER_ATR_SHORT_TERM")
    elif atr_contraction is not None and atr_contraction <= config.consolidation.moderate_atr_contraction:
        evidence.add("ATR_CONTRACTION")

    if (
        range_5d is not None
        and range_10d is not None
        and range_20d is not None
        and range_5d <= range_10d <= range_20d
    ):
        evidence.add("NARROWING_RANGE")

    if distance is not None and distance >= config.consolidation.price_near_high_tolerance:
        evidence.add("PRICE_HOLDING_NEAR_HIGH")

    if state in {"VERY_TIGHT", "TIGHT"} and {"ATR_CONTRACTION", "LOWER_ATR_SHORT_TERM"} & evidence and "PRICE_HOLDING_NEAR_HIGH" in evidence:
        quality = "STRONG"
    elif state in {"VERY_TIGHT", "TIGHT", "MODERATE"} and evidence:
        quality = "GOOD"
    elif state in {"MODERATE", "LOOSE"}:
        quality = "FAIR"
    else:
        quality = "WEAK"

    return state, quality, evidence


def classify_acceptance_state(
    values: dict[str, Any],
    breakout_state: str,
    volume_confirmation: str,
    benchmark_rs_context: str,
    config: DailySetupEvaluationConfig,
) -> tuple[str, set[str]]:
    if breakout_state not in {"CLOSE_ABOVE", "CLOSE_ACCEPTED"}:
        return "NONE", set()

    evidence: set[str] = {"CLOSE_ABOVE_PRIOR_HIGH"}
    distance = values.get("distance_to_prior_20d_high_pct")
    close_location = values.get("close_location_value")
    body = values.get("body_pct")
    upper_wick = values.get("upper_wick_pct")

    if distance is not None and distance >= config.breakout.close_acceptance_distance:
        evidence.add("CLOSE_DISTANCE_ACCEPTED")
    if close_location is not None and close_location >= config.acceptance.strong_close_location:
        evidence.add("STRONG_CLOSE_LOCATION")
    elif close_location is not None and close_location >= config.acceptance.moderate_close_location:
        evidence.add("GOOD_CLOSE_LOCATION")
    if body is not None and body >= config.acceptance.meaningful_body_pct:
        evidence.add("MEANINGFUL_BODY")
    if upper_wick is not None and upper_wick <= config.acceptance.contained_upper_wick_pct:
        evidence.add("CONTAINED_UPPER_WICK")
    if volume_confirmation in {"GOOD", "STRONG", "EXCEPTIONAL"}:
        evidence.add("VOLUME_SUPPORT")
    if benchmark_rs_context in {"POSITIVE", "STRONG"}:
        evidence.add("BENCHMARK_RS_SUPPORT")

    if breakout_state == "CLOSE_ACCEPTED" and len(evidence) >= 6:
        return "STRONG", evidence
    if len(evidence) >= 4:
        return "MODERATE", evidence
    return "WEAK", evidence


def classify_candle_quality(values: dict[str, Any], config: DailySetupEvaluationConfig) -> str:
    close_location = values.get("close_location_value")
    upper_wick = values.get("upper_wick_pct")
    body = values.get("body_pct")
    if close_location is None:
        return "UNAVAILABLE"
    if close_location < config.candle.poor_close_location:
        return "POOR"
    if (
        upper_wick is not None
        and upper_wick >= config.candle.large_upper_wick_pct
        and close_location < config.candle.good_close_location
    ):
        return "POOR"
    if (
        close_location >= config.candle.strong_close_location
        and (upper_wick is None or upper_wick <= config.candle.contained_upper_wick_pct)
        and body is not None
        and body >= config.candle.meaningful_body_pct
    ):
        return "STRONG"
    if close_location >= config.candle.good_close_location and (
        upper_wick is None or upper_wick <= config.candle.large_upper_wick_pct
    ):
        return "GOOD"
    if close_location >= config.candle.fair_close_location:
        return "FAIR"
    return "POOR"


def classify_volume_confirmation(values: dict[str, Any], config: DailySetupEvaluationConfig) -> str:
    max_rvol = max_decimal(values.get("relative_volume_20d"), values.get("relative_volume_5d"))
    if max_rvol is None:
        return "UNKNOWN"
    if max_rvol >= config.volume.exceptional_threshold:
        return "EXCEPTIONAL"
    if max_rvol >= config.volume.strong_threshold:
        return "STRONG"
    if max_rvol >= config.volume.good_threshold:
        return "GOOD"
    if max_rvol >= config.volume.normal_threshold:
        return "NORMAL"
    return "WEAK"


def classify_benchmark_rs_context(values: dict[str, Any], config: DailySetupEvaluationConfig) -> str:
    rs5 = values.get("relative_return_5d_vs_nifty500")
    rs20 = values.get("relative_return_20d_vs_nifty500")
    if rs5 is None and rs20 is None:
        return "UNKNOWN"
    if (
        rs5 is not None
        and rs20 is not None
        and rs5 >= config.benchmark_rs.strong_5d_threshold
        and rs20 >= config.benchmark_rs.positive_threshold
    ) or (
        rs5 is not None
        and rs20 is not None
        and rs20 >= config.benchmark_rs.strong_20d_threshold
        and rs5 >= config.benchmark_rs.positive_threshold
    ):
        return "STRONG"
    if (rs5 is not None and rs5 > config.benchmark_rs.positive_threshold) or (
        rs20 is not None and rs20 > config.benchmark_rs.positive_threshold
    ):
        return "POSITIVE"
    if (
        rs5 is not None
        and rs20 is not None
        and rs5 <= config.benchmark_rs.weak_5d_threshold
        and rs20 <= config.benchmark_rs.weak_20d_threshold
    ):
        return "WEAK"
    return "NEUTRAL"


def classify_extension_risk(values: dict[str, Any], config: DailySetupEvaluationConfig) -> str:
    current_status = str(values.get("candidate_extension_status") or "").upper()
    atr = values.get("atr_percent_14")
    return_1d = abs(values["return_1d"]) if values.get("return_1d") is not None else None
    return_5d = abs(values["return_5d"]) if values.get("return_5d") is not None else None
    sma_distance = abs(values["distance_from_sma_20_pct"]) if values.get("distance_from_sma_20_pct") is not None else None

    if current_status == "EXTREME":
        return "EXTREME"
    if atr is None or atr <= 0:
        return "UNAVAILABLE"

    return_1d_multiple = return_1d / atr if return_1d is not None else Decimal("0")
    return_5d_multiple = return_5d / atr if return_5d is not None else Decimal("0")

    if (
        return_1d_multiple >= config.extension.extreme_return_1d_atr_multiple
        or return_5d_multiple >= config.extension.extreme_return_5d_atr_multiple
        or (sma_distance is not None and sma_distance >= config.extension.extreme_sma20_distance)
    ):
        return "EXTREME"
    if current_status == "EXTENDED" or (
        return_1d_multiple >= config.extension.high_return_1d_atr_multiple
        or return_5d_multiple >= config.extension.high_return_5d_atr_multiple
        or (sma_distance is not None and sma_distance >= config.extension.high_sma20_distance)
    ):
        return "HIGH"
    if current_status == "ELEVATED" or (
        return_1d_multiple >= config.extension.moderate_return_1d_atr_multiple
        or return_5d_multiple >= config.extension.moderate_return_5d_atr_multiple
        or (sma_distance is not None and sma_distance >= config.extension.moderate_sma20_distance)
    ):
        return "MODERATE"
    return "LOW"


def false_breakout_flags(
    values: dict[str, Any],
    breakout_state: str,
    volume_confirmation: str,
    config: DailySetupEvaluationConfig,
) -> set[str]:
    flags: set[str] = set()
    prior_high = values.get("prior_high_20d")
    high = values.get("high")
    close = values.get("close")
    close_location = values.get("close_location_value")
    upper_wick = values.get("upper_wick_pct")
    gap_open = values.get("gap_open_pct")
    breakout_attempt = breakout_state in {"INTRADAY_BREAK_ONLY", "FAILED_BREAK", "CLOSE_ABOVE", "CLOSE_ACCEPTED"}

    if prior_high is not None and high is not None and close is not None and high > prior_high and close <= prior_high:
        flags.add("INTRADAY_BREAK_FAILED")
    if breakout_state in {"CLOSE_ABOVE", "CLOSE_ACCEPTED"} and weak_rejection_candle(values, config):
        flags.add("CLOSE_REJECTION")
    if (
        breakout_attempt
        and upper_wick is not None
        and upper_wick >= config.acceptance.large_upper_wick_pct
        and (close_location is None or close_location < config.acceptance.moderate_close_location)
    ):
        flags.add("UPPER_WICK_REJECTION")
    if breakout_attempt and volume_confirmation in {"WEAK", "UNKNOWN"}:
        flags.add("LOW_VOLUME_BREAK")
    if (
        breakout_attempt
        and gap_open is not None
        and gap_open >= config.extension.gap_fade_threshold
        and (close_location is None or close_location < config.acceptance.weak_close_location)
    ):
        flags.add("GAP_FADE")
    if flags & {"INTRADAY_BREAK_FAILED", "CLOSE_REJECTION", "UPPER_WICK_REJECTION", "GAP_FADE"}:
        flags.add("POSSIBLE_FALSE_BREAKOUT")
    return flags


def weak_rejection_candle(values: dict[str, Any], config: DailySetupEvaluationConfig) -> bool:
    close_location = values.get("close_location_value")
    upper_wick = values.get("upper_wick_pct")
    return bool(
        close_location is not None
        and close_location < config.acceptance.weak_close_location
        and upper_wick is not None
        and upper_wick >= config.acceptance.large_upper_wick_pct
    )


def daily_reclaim_context(
    values: dict[str, Any],
    config: DailySetupEvaluationConfig,
) -> tuple[bool, Decimal | None, str]:
    prior_high = values.get("prior_high_20d")
    low = values.get("low")
    close = values.get("close")
    if prior_high is None or low is None or close is None or prior_high <= 0:
        return False, None, "UNAVAILABLE"
    if low < prior_high < close:
        depth = (prior_high - low) / prior_high
        if depth <= config.reclaim.shallow_depth:
            return True, depth, "SHALLOW"
        if depth <= config.reclaim.moderate_depth:
            return True, depth, "MODERATE"
        return True, depth, "DEEP"
    return False, None, "NONE"


def classify_overhead_resistance(values: dict[str, Any], config: DailySetupEvaluationConfig) -> str:
    distance = values.get("distance_to_prior_52w_high_pct")
    above_52w = values.get("above_prior_52w_high")
    if distance is None:
        return "UNAVAILABLE"
    if above_52w is True or distance >= Decimal("0"):
        return "NONE"
    proximity = abs(distance)
    if proximity <= config.resistance.high_proximity:
        return "HIGH"
    if proximity <= config.resistance.moderate_proximity:
        return "MODERATE"
    if proximity <= config.resistance.low_proximity:
        return "LOW"
    return "NONE"


def classify_52w_context(values: dict[str, Any], config: DailySetupEvaluationConfig) -> str:
    distance = values.get("distance_to_prior_52w_high_pct")
    above_52w = values.get("above_prior_52w_high")
    if distance is None:
        return "UNAVAILABLE"
    if above_52w is True or distance > config.resistance.high_52w_at_tolerance:
        return "ABOVE"
    if abs(distance) <= config.resistance.high_52w_at_tolerance:
        return "AT"
    if distance >= -config.resistance.high_52w_near_tolerance:
        return "NEAR"
    return "FAR"


def setup_type_flags(
    values: dict[str, Any],
    *,
    candidate_state: str,
    breakout_state: str,
    consolidation_quality: str,
    benchmark_rs_context: str,
    candle_quality: str,
    extension_risk: str,
    high_52w_context: str,
) -> set[str]:
    flags: set[str] = set()
    if breakout_state in {"APPROACHING", "TESTING", "CLOSE_ACCEPTED", "CLOSE_ABOVE", "INTRADAY_BREAK_ONLY", "FAILED_BREAK"}:
        flags.add("BREAKOUT_20D")
    if breakout_state in {"CLOSE_ACCEPTED", "CLOSE_ABOVE"} and consolidation_quality in {"GOOD", "STRONG"}:
        flags.add("CONSOLIDATION_BREAKOUT")
    if high_52w_context in {"NEAR", "AT", "ABOVE"}:
        flags.add("BREAKOUT_52W_CONTEXT")
    if is_momentum_continuation(
        values,
        candidate_state=candidate_state,
        breakout_state=breakout_state,
        benchmark_rs_context=benchmark_rs_context,
        candle_quality=candle_quality,
        extension_risk=extension_risk,
    ):
        flags.add("MOMENTUM_CONTINUATION")
    if not flags:
        flags.add("NO_CLEAR_BREAKOUT")
    return flags


def is_momentum_continuation(
    values: dict[str, Any],
    *,
    candidate_state: str,
    breakout_state: str,
    benchmark_rs_context: str,
    candle_quality: str,
    extension_risk: str,
) -> bool:
    return_5d = values.get("return_5d")
    return_10d = values.get("return_10d")
    healthy_momentum = (
        return_5d is not None
        and return_5d > Decimal("0")
        and return_10d is not None
        and return_10d >= Decimal("-0.010")
    )
    structurally_above = breakout_state in {"CLOSE_ACCEPTED", "CLOSE_ABOVE"} or values.get("above_prior_20d_high") is True
    return bool(
        candidate_state in {"EMERGING", "CONFIRMED"}
        and structurally_above
        and healthy_momentum
        and benchmark_rs_context in {"POSITIVE", "STRONG", "NEUTRAL"}
        and candle_quality in {"FAIR", "GOOD", "STRONG"}
        and extension_risk not in {"EXTREME", "UNAVAILABLE"}
    )


def derive_setup_decision(
    *,
    candidate_state: str,
    research_status: str,
    setup_type_flags_value: set[str],
    breakout_state: str,
    level_quality: str,
    consolidation_quality: str,
    acceptance_state: str,
    candle_quality: str,
    volume_confirmation: str,
    benchmark_rs_context: str,
    extension_risk: str,
    high_52w_context: str,
    daily_level_reclaim: bool,
    false_breakout_flags_value: set[str],
    config: DailySetupEvaluationConfig,
) -> tuple[bool, str, set[str], set[str], set[str]]:
    rejection_reasons: set[str] = set()
    supporting_evidence: set[str] = set()
    warnings: set[str] = set()

    if candidate_state not in {"EMERGING", "CONFIRMED"}:
        rejection_reasons.add("NOT_A_MOMENTUM_CANDIDATE")
    if research_status in {"BLOCKED", "UNAVAILABLE"}:
        rejection_reasons.add(f"RESEARCH_{research_status}")
    if "NO_CLEAR_BREAKOUT" in setup_type_flags_value:
        rejection_reasons.add("NO_CLEAR_BREAKOUT_OR_CONTINUATION")
    if candle_quality == "POOR":
        rejection_reasons.add("POOR_CANDLE_QUALITY")
    if config.eligibility.block_extreme_extension and extension_risk == "EXTREME":
        rejection_reasons.add("EXTREME_EXTENSION")
    if config.eligibility.block_possible_false_breakout and "POSSIBLE_FALSE_BREAKOUT" in false_breakout_flags_value:
        rejection_reasons.add("POSSIBLE_FALSE_BREAKOUT")
    if (
        candidate_state == "CONFIRMED"
        and config.eligibility.confirmed_requires_close_or_continuation
        and breakout_state not in {"CLOSE_ACCEPTED", "CLOSE_ABOVE"}
        and "MOMENTUM_CONTINUATION" not in setup_type_flags_value
    ):
        rejection_reasons.add("CONFIRMED_REQUIRES_CLOSE_OR_CONTINUATION")

    if level_quality in {"GOOD", "STRONG"}:
        supporting_evidence.add(f"LEVEL_{level_quality}")
    if consolidation_quality in {"GOOD", "STRONG"}:
        supporting_evidence.add(f"CONSOLIDATION_{consolidation_quality}")
    if acceptance_state in {"MODERATE", "STRONG"}:
        supporting_evidence.add(f"ACCEPTANCE_{acceptance_state}")
    if candle_quality in {"GOOD", "STRONG"}:
        supporting_evidence.add(f"CANDLE_{candle_quality}")
    if volume_confirmation in {"GOOD", "STRONG", "EXCEPTIONAL"}:
        supporting_evidence.add(f"VOLUME_{volume_confirmation}")
    if benchmark_rs_context in {"POSITIVE", "STRONG"}:
        supporting_evidence.add(f"BENCHMARK_RS_{benchmark_rs_context}")
    if extension_risk == "LOW":
        supporting_evidence.add("LOW_EXTENSION_RISK")
    if high_52w_context in {"NEAR", "AT", "ABOVE"}:
        supporting_evidence.add(f"HIGH_52W_{high_52w_context}")
    if daily_level_reclaim:
        supporting_evidence.add("DAILY_LEVEL_RECLAIM")

    if volume_confirmation in {"WEAK", "UNKNOWN"}:
        warnings.add("WEAK_OR_UNKNOWN_VOLUME_CONFIRMATION")
    if benchmark_rs_context == "UNKNOWN":
        warnings.add("BENCHMARK_RS_UNKNOWN")
    if extension_risk in {"HIGH", "EXTREME"}:
        warnings.add(f"{extension_risk}_EXTENSION_RISK")

    has_actionable_context = bool(
        acceptance_state in {"WEAK", "MODERATE", "STRONG"}
        or "MOMENTUM_CONTINUATION" in setup_type_flags_value
        or (
            candidate_state == "EMERGING"
            and config.eligibility.emerging_allows_approaching_or_testing
            and breakout_state in {"APPROACHING", "TESTING"}
            and len(supporting_evidence) >= 2
        )
    )
    if not has_actionable_context:
        rejection_reasons.add("INSUFFICIENT_SETUP_CONFIRMATION")

    setup_eligible = not rejection_reasons
    if setup_eligible and acceptance_state in {"MODERATE", "STRONG"} and len(supporting_evidence) >= 5 and extension_risk in {"LOW", "MODERATE"}:
        setup_quality = "STRONG"
    elif setup_eligible:
        setup_quality = "VALID"
    elif (
        candidate_state in {"EMERGING", "CONFIRMED"}
        and research_status in {"READY", "PARTIAL"}
        and "POSSIBLE_FALSE_BREAKOUT" not in false_breakout_flags_value
        and "NO_CLEAR_BREAKOUT" not in setup_type_flags_value
    ):
        setup_quality = "WATCH"
    else:
        setup_quality = "POOR"

    return setup_eligible, setup_quality, rejection_reasons, supporting_evidence, warnings


def max_decimal(*values: Decimal | None) -> Decimal | None:
    clean = [value for value in values if value is not None]
    return max(clean) if clean else None


def join_flags(values: Iterable[Any]) -> str:
    return ";".join(str(value) for value in sorted(values) if value not in {"", None})
