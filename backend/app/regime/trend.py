from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Sequence

from app.regime.regime_config import NiftyTrendRules


@dataclass(frozen=True, slots=True)
class BenchmarkBar:
    trading_date: date
    close: Decimal


def build_nifty_trend_components(
    bars: Sequence[BenchmarkBar],
    *,
    target_weight: Decimal,
    rules: NiftyTrendRules,
) -> dict[date, dict[str, Any]]:
    ordered = sorted(bars, key=lambda row: row.trading_date)
    closes = [row.close for row in ordered]
    components: dict[date, dict[str, Any]] = {}
    for index, row in enumerate(ordered):
        metrics = trend_metrics(closes, index)
        component = classify_nifty_trend(metrics, target_weight=target_weight, rules=rules)
        component["evidence"]["trading_date"] = row.trading_date
        components[row.trading_date] = component
    return components


def trend_metrics(closes: Sequence[Decimal], index: int) -> dict[str, Decimal | None]:
    close = closes[index]
    sma20 = rolling_mean(closes, index, 20)
    sma50 = rolling_mean(closes, index, 50)
    sma200 = rolling_mean(closes, index, 200)
    prior_sma20 = rolling_mean(closes, index - 10, 20) if index >= 10 else None
    return {
        "nifty50_close": close,
        "nifty50_return_1d": simple_return(close, value_at(closes, index - 1)),
        "nifty50_return_5d": simple_return(close, value_at(closes, index - 5)),
        "nifty50_return_10d": simple_return(close, value_at(closes, index - 10)),
        "nifty50_return_20d": simple_return(close, value_at(closes, index - 20)),
        "nifty50_sma20": sma20,
        "nifty50_sma50": sma50,
        "nifty50_sma200": sma200,
        "nifty50_distance_sma20_pct": distance_pct(close, sma20),
        "nifty50_distance_sma50_pct": distance_pct(close, sma50),
        "nifty50_distance_sma200_pct": distance_pct(close, sma200),
        "nifty50_sma20_slope_10d_pct": simple_return(sma20, prior_sma20),
    }


def classify_nifty_trend(
    metrics: dict[str, Decimal | None],
    *,
    target_weight: Decimal,
    rules: NiftyTrendRules,
) -> dict[str, Any]:
    checks: list[tuple[str, Decimal | None, int]] = [
        ("return_5d", metrics["nifty50_return_5d"], 1),
        ("return_20d", metrics["nifty50_return_20d"], 2),
        ("distance_sma20", metrics["nifty50_distance_sma20_pct"], 1),
        ("distance_sma50", metrics["nifty50_distance_sma50_pct"], 1),
        ("distance_sma200", metrics["nifty50_distance_sma200_pct"], 1),
        ("sma20_slope_10d", metrics["nifty50_sma20_slope_10d_pct"], 1),
    ]
    available_checks = [(name, value, weight) for name, value, weight in checks if value is not None]
    max_points = sum(weight for _, _, weight in available_checks)
    metric_coverage_pct = (
        Decimal(len(available_checks)) / Decimal(len(checks)) * Decimal("100") if checks else Decimal("0")
    )
    if max_points == 0 or metric_coverage_pct < rules.minimum_metric_coverage_pct:
        return component(
            status="UNAVAILABLE",
            state="UNAVAILABLE",
            target_weight=target_weight,
            available_weight=Decimal("0"),
            signed_contribution=None,
            evidence={**metrics, "metric_coverage_pct": metric_coverage_pct, "score_points": None},
            warnings=("NIFTY_TREND_INSUFFICIENT_HISTORY",),
        )

    score_points = Decimal("0")
    score_points += weighted_return_points(metrics["nifty50_return_5d"], 1, rules.strong_positive_return_5d, rules.positive_return_5d, rules.negative_return_5d, rules.strong_negative_return_5d)
    score_points += weighted_return_points(metrics["nifty50_return_20d"], 2, rules.strong_positive_return_20d, rules.positive_return_20d, rules.negative_return_20d, rules.strong_negative_return_20d)
    score_points += sign_points(metrics["nifty50_distance_sma20_pct"], 1)
    score_points += sign_points(metrics["nifty50_distance_sma50_pct"], 1)
    score_points += sign_points(metrics["nifty50_distance_sma200_pct"], 1)
    score_points += threshold_points(metrics["nifty50_sma20_slope_10d_pct"], 1, rules.sma_slope_positive, rules.sma_slope_negative)

    ratio = score_points / Decimal(max_points)
    state = state_from_ratio(ratio)
    status = "AVAILABLE" if len(available_checks) == len(checks) else "PARTIAL"
    available_weight = target_weight * metric_coverage_pct / Decimal("100")
    signed_contribution = contribution_for_state(state, available_weight)
    return component(
        status=status,
        state=state,
        target_weight=target_weight,
        available_weight=available_weight,
        signed_contribution=signed_contribution,
        evidence={**metrics, "metric_coverage_pct": metric_coverage_pct, "score_points": score_points, "score_ratio": ratio},
        warnings=() if status == "AVAILABLE" else ("NIFTY_TREND_PARTIAL_HISTORY",),
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
        "component_name": "NIFTY_TREND",
        "component_status": status,
        "component_state": state,
        "target_weight": target_weight,
        "available_weight": available_weight,
        "signed_contribution": signed_contribution,
        "evidence": evidence,
        "source_version": "BENCHMARK_CONTEXT_V1",
        "coverage_metadata": {
            "historical_source": "data/reference/nse/indices/normalized/benchmark_daily.csv",
            "point_in_time_safety": "OFFICIAL_NSE_INDEX_HISTORY_THROUGH_T",
            "coverage_pct": evidence.get("metric_coverage_pct", Decimal("0")),
        },
        "warnings": tuple(warnings),
    }


def weighted_return_points(
    value: Decimal | None,
    weight: int,
    strong_positive: Decimal,
    positive: Decimal,
    negative: Decimal,
    strong_negative: Decimal,
) -> Decimal:
    if value is None:
        return Decimal("0")
    if value >= strong_positive:
        return Decimal(weight)
    if value >= positive:
        return Decimal(weight) * Decimal("0.5")
    if value <= strong_negative:
        return Decimal(-weight)
    if value <= negative:
        return Decimal(-weight) * Decimal("0.5")
    return Decimal("0")


def sign_points(value: Decimal | None, weight: int) -> Decimal:
    if value is None:
        return Decimal("0")
    if value > 0:
        return Decimal(weight)
    if value < 0:
        return Decimal(-weight)
    return Decimal("0")


def threshold_points(value: Decimal | None, weight: int, positive: Decimal, negative: Decimal) -> Decimal:
    if value is None:
        return Decimal("0")
    if value >= positive:
        return Decimal(weight)
    if value <= negative:
        return Decimal(-weight)
    return Decimal("0")


def state_from_ratio(ratio: Decimal) -> str:
    if ratio >= Decimal("0.67"):
        return "STRONGLY_BULLISH"
    if ratio >= Decimal("0.25"):
        return "BULLISH"
    if ratio <= Decimal("-0.67"):
        return "STRONGLY_BEARISH"
    if ratio <= Decimal("-0.25"):
        return "BEARISH"
    return "NEUTRAL"


def contribution_for_state(state: str, available_weight: Decimal) -> Decimal:
    multipliers = {
        "STRONGLY_BULLISH": Decimal("1"),
        "BULLISH": Decimal("0.60"),
        "NEUTRAL": Decimal("0"),
        "BEARISH": Decimal("-0.60"),
        "STRONGLY_BEARISH": Decimal("-1"),
    }
    return available_weight * multipliers.get(state, Decimal("0"))


def value_at(values: Sequence[Decimal], index: int) -> Decimal | None:
    if index < 0 or index >= len(values):
        return None
    return values[index]


def rolling_mean(values: Sequence[Decimal], index: int, window: int) -> Decimal | None:
    if index < 0 or index + 1 < window:
        return None
    chunk = values[index + 1 - window : index + 1]
    return sum(chunk) / Decimal(window)


def simple_return(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    if current is None or prior is None or prior == 0:
        return None
    return current / prior - Decimal("1")


def distance_pct(current: Decimal | None, baseline: Decimal | None) -> Decimal | None:
    if current is None or baseline is None or baseline == 0:
        return None
    return current / baseline - Decimal("1")

