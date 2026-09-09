from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Sequence

from app.risk.risk_config import (
    MOMENTUM_FIRST_METHODOLOGY,
    SETUP_SPECIFIC_FIRST_METHODOLOGY,
    RiskStructureConfig,
    RiskStructureV11Config,
)


@dataclass(frozen=True, slots=True)
class RiskDailyBar:
    trading_date: str
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal


@dataclass(frozen=True, slots=True)
class StopCandidate:
    basis: str
    level: Decimal
    details: str


@dataclass(frozen=True, slots=True)
class StopCandidateAssessment:
    candidate: StopCandidate
    eligible: bool
    stop_price: Decimal | None
    distance_pct: Decimal | None
    distance_atr: Decimal | None
    band: str
    quality: str
    valid: bool


@dataclass(frozen=True, slots=True)
class StopSelectionResult:
    candidate: StopCandidate | None
    priority_reason: str
    fallback_used: bool
    fallback_reason: str
    setup_specific_available: bool
    setup_specific_valid: bool


def build_ohlc_index(history: dict[str, Sequence[RiskDailyBar]]) -> dict[tuple[str, str], int]:
    return {
        (bar.trading_date, symbol): index
        for symbol, bars in history.items()
        for index, bar in enumerate(bars)
    }


def calculate_stop_structure(
    *,
    entry_row: dict[str, Any],
    setup_row: dict[str, Any],
    feature_row: dict[str, Any] | None,
    bars: Sequence[RiskDailyBar],
    bar_index: int | None,
    assumed_entry_price: Decimal | None,
    atr_14: Decimal | None,
    config: RiskStructureConfig = RiskStructureV11Config(),
) -> dict[str, Any]:
    warnings: list[str] = []
    rejections: list[str] = []
    if assumed_entry_price is None or assumed_entry_price <= 0:
        return invalid_stop("ENTRY_REFERENCE_UNAVAILABLE")
    if atr_14 is None or atr_14 <= 0:
        return invalid_stop("ATR_UNAVAILABLE")
    if bar_index is None or bar_index < 0 or bar_index >= len(bars):
        return invalid_stop("PRICE_HISTORY_UNAVAILABLE")

    candidates = stop_candidates(
        entry_row=entry_row,
        setup_row=setup_row,
        feature_row=feature_row,
        bars=bars,
        bar_index=bar_index,
        config=config,
    )
    selection = select_stop_candidate_with_context(
        candidates=candidates,
        setup_row=setup_row,
        assumed_entry_price=assumed_entry_price,
        atr_14=atr_14,
        config=config,
    )
    selected = selection.candidate
    if selected is None:
        return invalid_stop("NO_VALID_TECHNICAL_INVALIDATION_LEVEL", selection=selection)

    atr_buffer = atr_14 * config.stop.atr_buffer_multiple
    stop_price = selected.level - atr_buffer
    if stop_price <= 0:
        return invalid_stop("STOP_PRICE_NOT_POSITIVE")
    if stop_price >= assumed_entry_price:
        return invalid_stop("STOP_NOT_BELOW_ASSUMED_ENTRY")

    distance = assumed_entry_price - stop_price
    distance_pct = distance / assumed_entry_price * Decimal("100")
    distance_atr = distance / atr_14
    band = stop_distance_band(distance_pct=distance_pct, distance_atr=distance_atr, config=config)
    quality = stop_quality(basis=selected.basis, band=band, config=config)
    if band == "TOO_TIGHT":
        warnings.append("STOP_TOO_TIGHT")
    elif band == "TOO_WIDE":
        warnings.append("STOP_TOO_WIDE")
    elif band == "WIDE":
        warnings.append("WIDE_STOP_DISTANCE")
    if quality == "WEAK":
        warnings.append("WEAK_STOP_STRUCTURE")

    stop_valid = quality in {"ACCEPTABLE", "GOOD"}
    if not stop_valid:
        rejections.append("INVALID_OR_WEAK_STOP_STRUCTURE")
    return {
        "technical_invalidation_level": selected.level,
        "invalidation_basis": selected.basis,
        "invalidation_details": selected.details,
        "atr_buffer_value": atr_buffer,
        "stop_price": stop_price,
        "stop_distance_abs": distance,
        "stop_distance_pct": distance_pct,
        "stop_distance_atr_multiple": distance_atr,
        "stop_distance_band": band,
        "stop_quality": quality,
        "stop_valid": stop_valid,
        "selected_stop_priority_reason": selection.priority_reason,
        "fallback_stop_used": selection.fallback_used,
        "fallback_reason": selection.fallback_reason,
        "setup_specific_stop_available": selection.setup_specific_available,
        "setup_specific_stop_valid": selection.setup_specific_valid,
        "stop_rejection_reasons": rejections,
        "stop_warning_flags": warnings,
    }


def invalid_stop(reason: str, *, selection: StopSelectionResult | None = None) -> dict[str, Any]:
    return {
        "technical_invalidation_level": None,
        "invalidation_basis": "UNAVAILABLE",
        "invalidation_details": "",
        "atr_buffer_value": None,
        "stop_price": None,
        "stop_distance_abs": None,
        "stop_distance_pct": None,
        "stop_distance_atr_multiple": None,
        "stop_distance_band": "INVALID",
        "stop_quality": "INVALID",
        "stop_valid": False,
        "selected_stop_priority_reason": selection.priority_reason if selection else "",
        "fallback_stop_used": selection.fallback_used if selection else False,
        "fallback_reason": selection.fallback_reason if selection else "",
        "setup_specific_stop_available": selection.setup_specific_available if selection else False,
        "setup_specific_stop_valid": selection.setup_specific_valid if selection else False,
        "stop_rejection_reasons": [reason],
        "stop_warning_flags": [],
    }


def stop_candidates(
    *,
    entry_row: dict[str, Any],
    setup_row: dict[str, Any],
    feature_row: dict[str, Any] | None,
    bars: Sequence[RiskDailyBar],
    bar_index: int,
    config: RiskStructureConfig,
) -> list[StopCandidate]:
    candidates: list[StopCandidate] = []
    prior_high_20d = decimal_value(setup_row.get("prior_high_20d")) or decimal_value((feature_row or {}).get("prior_high_20d"))
    if prior_high_20d is not None:
        candidates.append(StopCandidate("BREAKOUT_STRUCTURE", prior_high_20d, "Prior 20-session high or breakout/reclaim level."))

    daily_reclaim = truthy(setup_row.get("daily_level_reclaim")) or truthy(entry_row.get("daily_level_reclaim"))
    if daily_reclaim:
        current = bars[bar_index]
        candidates.append(StopCandidate("DAILY_RECLAIM_LOW", current.low, "Current-session reclaim low."))

    if should_include_consolidation_low(setup_row):
        level = rolling_low(bars=bars, end_index=bar_index, window=config.stop.consolidation_low_window)
        if level is not None:
            candidates.append(StopCandidate("CONSOLIDATION_LOW", level, f"Causal {config.stop.consolidation_low_window}-session consolidation low."))

    for window in config.stop.causal_rolling_low_windows:
        level = rolling_low(bars=bars, end_index=bar_index, window=window)
        if level is not None:
            candidates.append(StopCandidate(f"RECENT_SWING_LOW_{window}", level, f"Causal {window}-session low including session T."))

    current = bars[bar_index]
    candidates.append(StopCandidate("CANDLE_LOW", current.low, "Current-session low."))

    sma_20 = decimal_value((feature_row or {}).get("sma_20")) or decimal_value(setup_row.get("sma_20"))
    if sma_20 is not None:
        candidates.append(StopCandidate("SMA20_SUPPORT", sma_20, "Same-day SMA20 support reference."))

    return dedupe_candidates(candidates)


def select_stop_candidate(
    *,
    candidates: Sequence[StopCandidate],
    setup_row: dict[str, Any],
    assumed_entry_price: Decimal,
    atr_14: Decimal | None = None,
    config: RiskStructureConfig = RiskStructureV11Config(),
) -> StopCandidate | None:
    return select_stop_candidate_with_context(
        candidates=candidates,
        setup_row=setup_row,
        assumed_entry_price=assumed_entry_price,
        atr_14=atr_14,
        config=config,
    ).candidate


def select_stop_candidate_with_context(
    *,
    candidates: Sequence[StopCandidate],
    setup_row: dict[str, Any],
    assumed_entry_price: Decimal,
    atr_14: Decimal | None,
    config: RiskStructureConfig,
) -> StopSelectionResult:
    assessments = {
        candidate.basis: assess_stop_candidate(
            candidate=candidate,
            assumed_entry_price=assumed_entry_price,
            atr_14=atr_14,
            config=config,
        )
        for candidate in candidates
    }
    active_specific = active_setup_specific_bases(setup_row)
    specific_available = any(basis in assessments for basis in active_specific)
    specific_valid = any(assessments[basis].valid for basis in active_specific if basis in assessments)
    methodology = getattr(config, "stop_selection_methodology", MOMENTUM_FIRST_METHODOLOGY)
    validity_aware = methodology == SETUP_SPECIFIC_FIRST_METHODOLOGY
    for basis in priority_for_setup(setup_row, config):
        assessment = assessments.get(basis)
        if assessment is None or not assessment.eligible:
            continue
        if validity_aware and not assessment.valid:
            continue
        selected_specific = basis in active_specific
        fallback_used = bool(active_specific) and not selected_specific
        return StopSelectionResult(
            candidate=assessment.candidate,
            priority_reason=stop_priority_reason(basis, setup_row),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason(active_specific, specific_available, specific_valid) if fallback_used else "",
            setup_specific_available=specific_available,
            setup_specific_valid=specific_valid,
        )
    return StopSelectionResult(
        candidate=None,
        priority_reason="NO_VALID_CAUSAL_STOP_CANDIDATE",
        fallback_used=bool(active_specific),
        fallback_reason=fallback_reason(active_specific, specific_available, specific_valid),
        setup_specific_available=specific_available,
        setup_specific_valid=specific_valid,
    )


def priority_for_setup(setup_row: dict[str, Any], config: RiskStructureConfig) -> tuple[str, ...]:
    methodology = getattr(config, "stop_selection_methodology", MOMENTUM_FIRST_METHODOLOGY)
    if methodology == SETUP_SPECIFIC_FIRST_METHODOLOGY:
        return setup_specific_priority_for_setup(setup_row)
    return momentum_first_priority_for_setup(setup_row)


def momentum_first_priority_for_setup(setup_row: dict[str, Any]) -> tuple[str, ...]:
    flags = split_codes(setup_row.get("setup_type_flags"))
    daily_reclaim = truthy(setup_row.get("daily_level_reclaim"))
    recent = tuple(f"RECENT_SWING_LOW_{window}" for window in (5, 10, 3))
    fallback = ("CANDLE_LOW", "SMA20_SUPPORT")
    if "MOMENTUM_CONTINUATION" in flags:
        return recent + ("CONSOLIDATION_LOW", "DAILY_RECLAIM_LOW", "BREAKOUT_STRUCTURE") + fallback
    if "CONSOLIDATION_BREAKOUT" in flags:
        return ("CONSOLIDATION_LOW", "RECENT_SWING_LOW_5", "DAILY_RECLAIM_LOW", "RECENT_SWING_LOW_10", "BREAKOUT_STRUCTURE") + fallback
    if daily_reclaim:
        return ("DAILY_RECLAIM_LOW", "RECENT_SWING_LOW_5", "CONSOLIDATION_LOW", "BREAKOUT_STRUCTURE", "RECENT_SWING_LOW_10") + fallback
    if "BREAKOUT_20D" in flags:
        return ("BREAKOUT_STRUCTURE", "RECENT_SWING_LOW_5", "DAILY_RECLAIM_LOW", "CONSOLIDATION_LOW", "RECENT_SWING_LOW_10") + fallback
    return ("RECENT_SWING_LOW_5", "RECENT_SWING_LOW_10", "CONSOLIDATION_LOW", "BREAKOUT_STRUCTURE") + fallback


def setup_specific_priority_for_setup(setup_row: dict[str, Any]) -> tuple[str, ...]:
    flags = split_codes(setup_row.get("setup_type_flags"))
    ordered: list[str] = []
    if "CONSOLIDATION_BREAKOUT" in flags:
        ordered.append("CONSOLIDATION_LOW")
    if truthy(setup_row.get("daily_level_reclaim")):
        ordered.append("DAILY_RECLAIM_LOW")
    if "BREAKOUT_20D" in flags:
        ordered.append("BREAKOUT_STRUCTURE")
    ordered.extend(("RECENT_SWING_LOW_5", "RECENT_SWING_LOW_10", "RECENT_SWING_LOW_3"))
    ordered.extend(("CONSOLIDATION_LOW", "DAILY_RECLAIM_LOW", "BREAKOUT_STRUCTURE"))
    ordered.extend(("CANDLE_LOW", "SMA20_SUPPORT"))
    return dedupe_bases(ordered)


def active_setup_specific_bases(setup_row: dict[str, Any]) -> tuple[str, ...]:
    flags = split_codes(setup_row.get("setup_type_flags"))
    active: list[str] = []
    if "CONSOLIDATION_BREAKOUT" in flags:
        active.append("CONSOLIDATION_LOW")
    if truthy(setup_row.get("daily_level_reclaim")):
        active.append("DAILY_RECLAIM_LOW")
    if "BREAKOUT_20D" in flags:
        active.append("BREAKOUT_STRUCTURE")
    return tuple(active)


def assess_stop_candidate(
    *,
    candidate: StopCandidate,
    assumed_entry_price: Decimal,
    atr_14: Decimal | None,
    config: RiskStructureConfig,
) -> StopCandidateAssessment:
    eligible = candidate.level > 0 and candidate.level < assumed_entry_price and atr_14 is not None and atr_14 > 0
    if not eligible:
        return StopCandidateAssessment(candidate, False, None, None, None, "INVALID", "INVALID", False)
    stop_price = candidate.level - atr_14 * config.stop.atr_buffer_multiple
    if stop_price <= 0 or stop_price >= assumed_entry_price:
        return StopCandidateAssessment(candidate, False, stop_price, None, None, "INVALID", "INVALID", False)
    distance = assumed_entry_price - stop_price
    distance_pct = distance / assumed_entry_price * Decimal("100")
    distance_atr = distance / atr_14
    band = stop_distance_band(distance_pct=distance_pct, distance_atr=distance_atr, config=config)
    quality = stop_quality(basis=candidate.basis, band=band, config=config)
    return StopCandidateAssessment(
        candidate=candidate,
        eligible=True,
        stop_price=stop_price,
        distance_pct=distance_pct,
        distance_atr=distance_atr,
        band=band,
        quality=quality,
        valid=quality in {"ACCEPTABLE", "GOOD"},
    )


def stop_priority_reason(basis: str, setup_row: dict[str, Any]) -> str:
    flags = split_codes(setup_row.get("setup_type_flags"))
    if basis == "CONSOLIDATION_LOW" and "CONSOLIDATION_BREAKOUT" in flags:
        return "CONSOLIDATION_BREAKOUT_VALID"
    if basis == "DAILY_RECLAIM_LOW" and truthy(setup_row.get("daily_level_reclaim")):
        return "DAILY_RECLAIM_VALID"
    if basis == "BREAKOUT_STRUCTURE" and "BREAKOUT_20D" in flags:
        return "BREAKOUT_STRUCTURE_VALID"
    if basis.startswith("RECENT_SWING_LOW_") and "MOMENTUM_CONTINUATION" in flags:
        return "MOMENTUM_CONTINUATION_SWING_SUPPORT"
    return "SAFE_CAUSAL_FALLBACK"


def fallback_reason(active_specific: Sequence[str], available: bool, valid: bool) -> str:
    if not active_specific:
        return "NO_ACTIVE_SETUP_SPECIFIC_CONTEXT"
    if not available:
        return "SETUP_SPECIFIC_STRUCTURE_UNAVAILABLE"
    if not valid:
        return "SETUP_SPECIFIC_STRUCTURE_INVALID"
    return "HIGHER_PRIORITY_SETUP_SPECIFIC_STRUCTURE_NOT_SELECTED"


def dedupe_bases(bases: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(bases))


def rolling_low(*, bars: Sequence[RiskDailyBar], end_index: int, window: int) -> Decimal | None:
    if end_index < 0 or not bars:
        return None
    start = max(0, end_index - window + 1)
    selected = bars[start : end_index + 1]
    if not selected:
        return None
    return min(bar.low for bar in selected)


def stop_distance_band(*, distance_pct: Decimal, distance_atr: Decimal, config: RiskStructureConfig) -> str:
    if distance_pct < config.stop.minimum_stop_distance_pct or distance_atr < config.stop.minimum_stop_distance_atr:
        return "TOO_TIGHT"
    if distance_pct > config.stop.maximum_stop_distance_pct or distance_atr > config.stop.maximum_stop_distance_atr:
        return "TOO_WIDE"
    if distance_pct > config.stop.wide_stop_distance_pct or distance_atr > config.stop.wide_stop_distance_atr:
        return "WIDE"
    return "PRACTICAL"


def stop_quality(*, basis: str, band: str, config: RiskStructureConfig) -> str:
    if band in {"INVALID", "TOO_TIGHT", "TOO_WIDE"}:
        return "INVALID"
    if basis in config.stop.good_invalidation_bases and band == "PRACTICAL":
        return "GOOD"
    if basis in config.stop.good_invalidation_bases and band == "WIDE":
        return "ACCEPTABLE"
    if basis in config.stop.acceptable_invalidation_bases and band == "PRACTICAL":
        return "ACCEPTABLE"
    return "WEAK"


def should_include_consolidation_low(setup_row: dict[str, Any]) -> bool:
    flags = split_codes(setup_row.get("setup_type_flags"))
    quality = str(setup_row.get("consolidation_quality", "")).upper()
    state = str(setup_row.get("consolidation_state", "")).upper()
    return "CONSOLIDATION_BREAKOUT" in flags or quality in {"GOOD", "STRONG"} or state in {"TIGHT", "VERY_TIGHT", "MODERATE"}


def dedupe_candidates(candidates: Sequence[StopCandidate]) -> list[StopCandidate]:
    seen: set[str] = set()
    output: list[StopCandidate] = []
    for candidate in candidates:
        if candidate.basis in seen:
            continue
        seen.add(candidate.basis)
        output.append(candidate)
    return output


def split_codes(value: Any) -> set[str]:
    return {item.strip().upper() for item in str(value or "").split(";") if item.strip()}


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def decimal_value(value: Any) -> Decimal | None:
    if isinstance(value, Decimal):
        return value
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except Exception:
        return None
