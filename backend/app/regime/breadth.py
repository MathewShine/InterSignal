from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Sequence

from app.regime.regime_config import BreadthRules


@dataclass(slots=True)
class BreadthAggregate:
    symbols: set[str] = field(default_factory=set)
    advancers: int = 0
    decliners: int = 0
    unchanged: int = 0
    return_1d_usable: int = 0
    above_sma20: int = 0
    sma20_usable: int = 0
    above_sma50: int = 0
    sma50_usable: int = 0
    positive_5d: int = 0
    return_5d_usable: int = 0
    positive_20d: int = 0
    return_20d_usable: int = 0


def update_breadth_aggregate(aggregate: BreadthAggregate, row: dict[str, Any]) -> None:
    symbol = str(row.get("symbol", "")).strip()
    if symbol:
        aggregate.symbols.add(symbol)

    return_1d = parse_decimal(row.get("return_1d"))
    if return_1d is not None:
        aggregate.return_1d_usable += 1
        if return_1d > 0:
            aggregate.advancers += 1
        elif return_1d < 0:
            aggregate.decliners += 1
        else:
            aggregate.unchanged += 1

    distance_sma20 = parse_decimal(row.get("distance_from_sma_20_pct"))
    if distance_sma20 is not None:
        aggregate.sma20_usable += 1
        if distance_sma20 > 0:
            aggregate.above_sma20 += 1

    distance_sma50 = parse_decimal(row.get("distance_from_sma_50_pct"))
    if distance_sma50 is not None:
        aggregate.sma50_usable += 1
        if distance_sma50 > 0:
            aggregate.above_sma50 += 1

    return_5d = parse_decimal(row.get("return_5d"))
    if return_5d is not None:
        aggregate.return_5d_usable += 1
        if return_5d > 0:
            aggregate.positive_5d += 1

    return_20d = parse_decimal(row.get("return_20d"))
    if return_20d is not None:
        aggregate.return_20d_usable += 1
        if return_20d > 0:
            aggregate.positive_20d += 1


def finalize_breadth_component(
    trading_date: date,
    aggregate: BreadthAggregate | None,
    *,
    expected_members: int,
    membership_status: str,
    target_weight: Decimal,
    rules: BreadthRules,
) -> dict[str, Any]:
    aggregate = aggregate or BreadthAggregate()
    coverage_pct = pct_decimal(aggregate.return_1d_usable, expected_members)
    advancer_pct = pct_decimal(aggregate.advancers, aggregate.return_1d_usable)
    pct_above_sma20 = pct_decimal(aggregate.above_sma20, aggregate.sma20_usable)
    pct_above_sma50 = pct_decimal(aggregate.above_sma50, aggregate.sma50_usable)
    pct_positive_5d = pct_decimal(aggregate.positive_5d, aggregate.return_5d_usable)
    pct_positive_20d = pct_decimal(aggregate.positive_20d, aggregate.return_20d_usable)
    evidence = {
        "trading_date": trading_date,
        "breadth_membership_status": membership_status or "UNAVAILABLE",
        "expected_members": expected_members,
        "usable_members": aggregate.return_1d_usable,
        "feature_row_symbols": len(aggregate.symbols),
        "breadth_coverage_pct": coverage_pct,
        "advancers": aggregate.advancers,
        "decliners": aggregate.decliners,
        "unchanged": aggregate.unchanged,
        "advance_decline_ratio": safe_ratio(aggregate.advancers, aggregate.decliners),
        "advancer_pct": advancer_pct,
        "pct_above_sma20": pct_above_sma20,
        "pct_above_sma50": pct_above_sma50,
        "pct_positive_5d": pct_positive_5d,
        "pct_positive_20d": pct_positive_20d,
        "sma20_usable": aggregate.sma20_usable,
        "sma50_usable": aggregate.sma50_usable,
        "return_5d_usable": aggregate.return_5d_usable,
        "return_20d_usable": aggregate.return_20d_usable,
    }
    if (
        expected_members <= 0
        or aggregate.return_1d_usable < rules.minimum_usable_members
        or coverage_pct < rules.minimum_breadth_coverage_pct
    ):
        return component(
            status="UNAVAILABLE",
            state="UNAVAILABLE",
            target_weight=target_weight,
            available_weight=Decimal("0"),
            signed_contribution=None,
            evidence=evidence,
            warnings=("NIFTY500_BREADTH_INSUFFICIENT_COVERAGE",),
        )

    score_points, max_points = breadth_score(evidence, rules)
    ratio = score_points / Decimal(max_points) if max_points else Decimal("0")
    state = state_from_ratio(ratio)
    status = "PARTIAL" if membership_status == "PARTIAL_HISTORY" or coverage_pct < Decimal("95") else "AVAILABLE"
    return component(
        status=status,
        state=state,
        target_weight=target_weight,
        available_weight=target_weight,
        signed_contribution=contribution_for_state(state, target_weight),
        evidence={**evidence, "score_points": score_points, "score_ratio": ratio},
        warnings=("NIFTY500_MEMBERSHIP_PARTIAL_HISTORY",) if membership_status == "PARTIAL_HISTORY" else (),
    )


def breadth_score(evidence: dict[str, Any], rules: BreadthRules) -> tuple[Decimal, int]:
    checks = [
        (evidence.get("advancer_pct"), 2),
        (evidence.get("pct_above_sma20"), 1),
        (evidence.get("pct_above_sma50"), 1),
        (evidence.get("pct_positive_5d"), 1),
        (evidence.get("pct_positive_20d"), 1),
    ]
    score = Decimal("0")
    max_points = 0
    for value, weight in checks:
        if value is None:
            continue
        max_points += weight
        score += pct_points(value, weight, rules)
    return score, max_points


def pct_points(value: Decimal, weight: int, rules: BreadthRules) -> Decimal:
    if value >= rules.strongly_bullish_pct:
        return Decimal(weight)
    if value >= rules.bullish_pct:
        return Decimal(weight) * Decimal("0.5")
    if value <= rules.strongly_bearish_pct:
        return Decimal(-weight)
    if value <= rules.bearish_pct:
        return Decimal(-weight) * Decimal("0.5")
    return Decimal("0")


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
        "component_name": "NIFTY500_BREADTH",
        "component_status": status,
        "component_state": state,
        "target_weight": target_weight,
        "available_weight": available_weight,
        "signed_contribution": signed_contribution,
        "evidence": evidence,
        "source_version": "DAILY_FEATURES_V1_PLUS_POINT_IN_TIME_MEMBERSHIP",
        "coverage_metadata": {
            "historical_source": "data/research/features/daily/v1/daily_features_v1.csv.gz",
            "membership_source": "data/reference/nifty500/history/membership_periods.csv",
            "point_in_time_safety": "PARTIAL_HISTORY_POINT_IN_TIME_MEMBERSHIP",
            "coverage_pct": evidence.get("breadth_coverage_pct", Decimal("0")),
        },
        "warnings": tuple(warnings),
    }


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


def safe_ratio(numerator: int, denominator: int) -> Decimal | None:
    if denominator == 0:
        return None
    return Decimal(numerator) / Decimal(denominator)


def pct_decimal(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return Decimal(numerator) / Decimal(denominator) * Decimal("100")


def parse_decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None

