from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Sequence

from app.regime.regime_config import SectorParticipationRules
from app.regime.trend import distance_pct, rolling_mean, simple_return


@dataclass(frozen=True, slots=True)
class SectorIndexBar:
    trading_date: date
    sector_index_id: str
    close: Decimal


@dataclass(slots=True)
class SectorAggregate:
    sectors: set[str] = field(default_factory=set)
    positive_1d: int = 0
    return_1d_usable: int = 0
    positive_5d: int = 0
    return_5d_usable: int = 0
    positive_20d: int = 0
    return_20d_usable: int = 0
    above_sma20: int = 0
    sma20_usable: int = 0
    returns_1d: list[Decimal] = field(default_factory=list)
    returns_5d: list[Decimal] = field(default_factory=list)


def build_sector_participation_components(
    bars: Sequence[SectorIndexBar],
    *,
    expected_sector_indexes: int,
    target_weight: Decimal,
    rules: SectorParticipationRules,
) -> dict[date, dict[str, Any]]:
    grouped: dict[str, list[SectorIndexBar]] = defaultdict(list)
    for bar in bars:
        grouped[bar.sector_index_id].append(bar)

    daily: dict[date, SectorAggregate] = defaultdict(SectorAggregate)
    for sector_id, sector_bars in grouped.items():
        ordered = sorted(sector_bars, key=lambda row: row.trading_date)
        closes = [row.close for row in ordered]
        for index, bar in enumerate(ordered):
            aggregate = daily[bar.trading_date]
            aggregate.sectors.add(sector_id)
            return_1d = simple_return(bar.close, closes[index - 1] if index >= 1 else None)
            return_5d = simple_return(bar.close, closes[index - 5] if index >= 5 else None)
            return_20d = simple_return(bar.close, closes[index - 20] if index >= 20 else None)
            sma20_distance = distance_pct(bar.close, rolling_mean(closes, index, 20))
            if return_1d is not None:
                aggregate.return_1d_usable += 1
                aggregate.returns_1d.append(return_1d)
                if return_1d > 0:
                    aggregate.positive_1d += 1
            if return_5d is not None:
                aggregate.return_5d_usable += 1
                aggregate.returns_5d.append(return_5d)
                if return_5d > 0:
                    aggregate.positive_5d += 1
            if return_20d is not None:
                aggregate.return_20d_usable += 1
                if return_20d > 0:
                    aggregate.positive_20d += 1
            if sma20_distance is not None:
                aggregate.sma20_usable += 1
                if sma20_distance > 0:
                    aggregate.above_sma20 += 1

    return {
        trading_date: finalize_sector_component(
            trading_date,
            aggregate,
            expected_sector_indexes=expected_sector_indexes,
            target_weight=target_weight,
            rules=rules,
        )
        for trading_date, aggregate in daily.items()
    }


def finalize_sector_component(
    trading_date: date,
    aggregate: SectorAggregate | None,
    *,
    expected_sector_indexes: int,
    target_weight: Decimal,
    rules: SectorParticipationRules,
) -> dict[str, Any]:
    aggregate = aggregate or SectorAggregate()
    coverage_pct = pct_decimal(len(aggregate.sectors), expected_sector_indexes)
    evidence = {
        "trading_date": trading_date,
        "sectors_expected": expected_sector_indexes,
        "sectors_available": len(aggregate.sectors),
        "sector_coverage_pct": coverage_pct,
        "sector_positive_1d_pct": pct_decimal(aggregate.positive_1d, aggregate.return_1d_usable),
        "sector_positive_5d_pct": pct_decimal(aggregate.positive_5d, aggregate.return_5d_usable),
        "sector_positive_20d_pct": pct_decimal(aggregate.positive_20d, aggregate.return_20d_usable),
        "sector_above_sma20_pct": pct_decimal(aggregate.above_sma20, aggregate.sma20_usable),
        "median_sector_return_1d": median_decimal(aggregate.returns_1d),
        "median_sector_return_5d": median_decimal(aggregate.returns_5d),
        "sector_return_1d_dispersion": dispersion(aggregate.returns_1d),
        "sector_return_1d_usable": aggregate.return_1d_usable,
        "sector_return_5d_usable": aggregate.return_5d_usable,
        "sector_return_20d_usable": aggregate.return_20d_usable,
        "sector_sma20_usable": aggregate.sma20_usable,
    }
    if (
        len(aggregate.sectors) < rules.minimum_available_sector_indexes
        or coverage_pct < rules.minimum_sector_coverage_pct
        or aggregate.return_1d_usable < rules.minimum_available_sector_indexes
    ):
        return component(
            status="UNAVAILABLE",
            state="UNAVAILABLE",
            target_weight=target_weight,
            available_weight=Decimal("0"),
            signed_contribution=None,
            evidence=evidence,
            warnings=("SECTOR_INDEX_PARTICIPATION_INSUFFICIENT_COVERAGE",),
        )

    score_points, max_points = sector_score(evidence, rules)
    ratio = score_points / Decimal(max_points) if max_points else Decimal("0")
    state = state_from_ratio(ratio)
    status = "AVAILABLE" if coverage_pct >= Decimal("95") else "PARTIAL"
    warnings = () if status == "AVAILABLE" else ("SECTOR_INDEX_PARTICIPATION_PARTIAL_COVERAGE",)
    return component(
        status=status,
        state=state,
        target_weight=target_weight,
        available_weight=target_weight,
        signed_contribution=contribution_for_state(state, target_weight),
        evidence={**evidence, "score_points": score_points, "score_ratio": ratio},
        warnings=warnings,
    )


def sector_score(evidence: dict[str, Any], rules: SectorParticipationRules) -> tuple[Decimal, int]:
    checks = [
        (evidence.get("sector_positive_1d_pct"), 1),
        (evidence.get("sector_positive_5d_pct"), 1),
        (evidence.get("sector_positive_20d_pct"), 1),
        (evidence.get("sector_above_sma20_pct"), 1),
    ]
    score = Decimal("0")
    max_points = 0
    for value, weight in checks:
        if value is None:
            continue
        max_points += weight
        score += pct_points(value, weight, rules)
    median_5d = evidence.get("median_sector_return_5d")
    if median_5d is not None:
        max_points += 1
        score += Decimal("1") if median_5d > 0 else Decimal("-1") if median_5d < 0 else Decimal("0")
    return score, max_points


def pct_points(value: Decimal, weight: int, rules: SectorParticipationRules) -> Decimal:
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
        "component_name": "SECTOR_INDEX_PARTICIPATION",
        "component_status": status,
        "component_state": state,
        "target_weight": target_weight,
        "available_weight": available_weight,
        "signed_contribution": signed_contribution,
        "evidence": evidence,
        "source_version": "SECTOR_CONTEXT_V1_OFFICIAL_INDEX_HISTORY",
        "coverage_metadata": {
            "historical_source": "data/reference/nse/indices/normalized/sector_index_daily.csv",
            "point_in_time_safety": "OFFICIAL_SECTOR_INDEX_HISTORY_THROUGH_T_NOT_STOCK_SECTOR_BREADTH",
            "coverage_pct": evidence.get("sector_coverage_pct", Decimal("0")),
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


def pct_decimal(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return Decimal(numerator) / Decimal(denominator) * Decimal("100")


def median_decimal(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def dispersion(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return max(values) - min(values)

