from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Sequence

from app.regime.regime_config import IndiaVixRules
from app.regime.trend import simple_return


@dataclass(frozen=True, slots=True)
class VixBar:
    trading_date: date
    close: Decimal


def build_india_vix_components(
    bars: Sequence[VixBar],
    *,
    target_weight: Decimal,
    rules: IndiaVixRules,
) -> dict[date, dict[str, Any]]:
    ordered = sorted(bars, key=lambda row: row.trading_date)
    closes = [row.close for row in ordered]
    components: dict[date, dict[str, Any]] = {}
    for index, row in enumerate(ordered):
        change_1d = simple_return(row.close, closes[index - 1] if index >= 1 else None)
        change_5d = simple_return(row.close, closes[index - 5] if index >= 5 else None)
        percentile_20d = trailing_percentile(closes, index, 20)
        components[row.trading_date] = classify_india_vix(
            trading_date=row.trading_date,
            close=row.close,
            change_1d=change_1d,
            change_5d=change_5d,
            percentile_20d=percentile_20d,
            target_weight=target_weight,
            rules=rules,
        )
    return components


def classify_india_vix(
    *,
    trading_date: date,
    close: Decimal,
    change_1d: Decimal | None,
    change_5d: Decimal | None,
    percentile_20d: Decimal | None,
    target_weight: Decimal,
    rules: IndiaVixRules,
) -> dict[str, Any]:
    score = Decimal("0")
    if close <= rules.risk_on_level:
        score += Decimal("1")
    elif close >= rules.strongly_risk_off_level:
        score -= Decimal("2")
    elif close >= rules.risk_off_level:
        score -= Decimal("1")

    if change_5d is not None:
        if change_5d <= rules.falling_5d_pct:
            score += Decimal("1")
        elif change_5d >= rules.rising_5d_pct:
            score -= Decimal("1")

    if percentile_20d is not None:
        if percentile_20d <= Decimal("35"):
            score += Decimal("1")
        elif percentile_20d >= Decimal("90"):
            score -= Decimal("2")
        elif percentile_20d >= Decimal("80"):
            score -= Decimal("1")

    if score >= Decimal("2"):
        state = "STRONGLY_RISK_ON"
    elif score >= Decimal("1"):
        state = "RISK_ON"
    elif score <= Decimal("-3"):
        state = "STRONGLY_RISK_OFF"
    elif score <= Decimal("-1"):
        state = "RISK_OFF"
    else:
        state = "NEUTRAL"

    return component(
        status="AVAILABLE" if percentile_20d is not None else "PARTIAL",
        state=state,
        target_weight=target_weight,
        available_weight=target_weight,
        signed_contribution=contribution_for_state(state, target_weight),
        evidence={
            "trading_date": trading_date,
            "india_vix_close": close,
            "india_vix_change_1d": change_1d,
            "india_vix_change_5d": change_5d,
            "india_vix_percentile_20d": percentile_20d,
            "score_points": score,
        },
        warnings=() if percentile_20d is not None else ("INDIA_VIX_PARTIAL_HISTORY",),
    )


def unavailable_india_vix_component(trading_date: date, *, target_weight: Decimal) -> dict[str, Any]:
    return component(
        status="UNAVAILABLE",
        state="UNAVAILABLE",
        target_weight=target_weight,
        available_weight=Decimal("0"),
        signed_contribution=None,
        evidence={
            "trading_date": trading_date,
            "india_vix_close": None,
            "india_vix_change_1d": None,
            "india_vix_change_5d": None,
            "india_vix_percentile_20d": None,
        },
        warnings=("INDIA_VIX_HISTORY_NOT_AVAILABLE_LOCALLY",),
    )


def component(
    *,
    status: str,
    state: str,
    target_weight: Decimal,
    available_weight: Decimal,
    signed_contribution: Decimal | None,
    evidence: dict[str, Any],
    warnings: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "component_name": "INDIA_VIX",
        "component_status": status,
        "component_state": state,
        "target_weight": target_weight,
        "available_weight": available_weight,
        "signed_contribution": signed_contribution,
        "evidence": evidence,
        "source_version": "UNAVAILABLE_OFFICIAL_HISTORY_NOT_PRESENT" if status == "UNAVAILABLE" else "OFFICIAL_INDIA_VIX_HISTORY",
        "coverage_metadata": {
            "historical_source": "data/reference/nse/indices/normalized/india_vix_daily.csv",
            "point_in_time_safety": "UNAVAILABLE_NOT_IMPUTED" if status == "UNAVAILABLE" else "OFFICIAL_HISTORY_THROUGH_T",
            "coverage_pct": Decimal("0") if status == "UNAVAILABLE" else Decimal("100"),
        },
        "warnings": tuple(warnings),
    }


def contribution_for_state(state: str, target_weight: Decimal) -> Decimal:
    multipliers = {
        "STRONGLY_RISK_ON": Decimal("1"),
        "RISK_ON": Decimal("0.60"),
        "NEUTRAL": Decimal("0"),
        "RISK_OFF": Decimal("-0.60"),
        "STRONGLY_RISK_OFF": Decimal("-1"),
    }
    return target_weight * multipliers.get(state, Decimal("0"))


def trailing_percentile(values: Sequence[Decimal], index: int, window: int) -> Decimal | None:
    if index + 1 < window:
        return None
    current = values[index]
    chunk = values[index + 1 - window : index + 1]
    less_or_equal = sum(1 for value in chunk if value <= current)
    return Decimal(less_or_equal) / Decimal(len(chunk)) * Decimal("100")

