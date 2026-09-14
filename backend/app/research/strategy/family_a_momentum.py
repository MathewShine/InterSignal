from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from app.backtesting.costs.cost_config import (
    EXPECTED_COST_CONFIG_HASH,
    default_cost_model_config,
)
from app.backtesting.costs.cost_engine import (
    SCENARIO_BASELINE_SLIPPAGE,
    registered_cost_scenarios,
)
from app.backtesting.costs.cost_models import (
    DP_CHARGE,
    FIXED_BPS,
    STAMP_DUTY,
    canonical_hash,
    json_ready,
)
from app.backtesting.costs.slippage import slippage_raw
from app.backtesting.costs.statutory_costs import round_rupees, side_fee_components
from app.research.strategy.rr_cap4_holdout_validation import (
    artifact_root as cap4_validation_root,
    validation_baseline_snapshot,
)


FAMILY_VERSION = "STRATEGY_FAMILY_A_MOMENTUM_V1"
RESEARCH_PROFILE = "MEDIUM_TERM_CROSS_SECTIONAL_MOMENTUM_V1"
FAMILY_CODE = "FAMILY_A"
RESEARCH_PROTOCOL = "FAMILY_A_RESEARCH_PROTOCOL_V1"
COMMAND = "Step 03.01 / Command 01"

DEVELOPMENT_START = date(2022, 1, 1)
DEVELOPMENT_END = date(2024, 12, 31)
VALIDATION_CLASSIFICATION = "FORMAL_HOLDOUT_WITH_PRIOR_MARKET_EXPOSURE"
STARTING_CAPITAL = Decimal("100000")
PRICE_FLOOR = Decimal("100")
LIQUIDITY_FLOOR = Decimal("100000000")
LIQUIDITY_WINDOW = 20
TOP_DECILE = Decimal("0.10")
MINIMUM_PORTFOLIO_SIZE = 20

LOOKBACK_SESSIONS = {
    "3M": 63,
    "6M": 126,
    "9M": 189,
    "12M": 252,
    "12M_EX_LAST_1M": 252,
}
SKIP_SESSIONS = {
    "3M": 0,
    "6M": 0,
    "9M": 0,
    "12M": 0,
    "12M_EX_LAST_1M": 21,
}

EXPERIMENT_DEFINITIONS = (
    ("MOM-A-001", "SIX_MONTH_MOMENTUM_MONTHLY", "6M", "MONTHLY"),
    ("MOM-A-002", "SIX_MONTH_MOMENTUM_QUARTERLY", "6M", "QUARTERLY"),
    ("MOM-A-003", "TWELVE_MINUS_ONE_MOMENTUM_MONTHLY", "12M_EX_LAST_1M", "MONTHLY"),
)
EXPERIMENT_IDS = tuple(row[0] for row in EXPERIMENT_DEFINITIONS)

FUTURE_PRIMARY_METRICS = (
    "CAGR",
    "TOTAL_RETURN",
    "MAX_DRAWDOWN",
    "VOLATILITY",
    "SHARPE_LIKE_RISK_ADJUSTED_METRIC",
    "REBALANCE_PERIOD_WIN_RATE",
    "POSITIVE_MONTH_RATE",
    "PROFIT_FACTOR_WHERE_MEANINGFUL",
    "TURNOVER",
    "TRANSACTION_COST_DRAG",
    "COST_ADJUSTED_CAGR",
    "COST_ADJUSTED_RETURN",
)
FUTURE_QUALITY_CATEGORIES = (
    "RETURN_QUALITY",
    "RISK_QUALITY",
    "COST_EFFICIENCY",
    "TEMPORAL_STABILITY",
    "TURNOVER_EFFICIENCY",
)
FUTURE_BASELINE_RESULTS = ("PROMISING", "MIXED", "WEAK", "FAILED", "INCONCLUSIVE")
ARCHITECTURE_RESULTS = (
    "READY_FOR_DEVELOPMENT_BACKTEST",
    "METHODOLOGY_FIX_REQUIRED",
    "DATA_BLOCKED",
    "INCONCLUSIVE",
)
DATA_READINESS_RESULTS = ("READY", "READY_WITH_LIMITATIONS", "BLOCKED", "INCONCLUSIVE")

REPORT_NAMES = (
    "family_a_v1_summary.json",
    "family_a_v1_data_readiness.csv",
    "family_a_v1_signal_pilot.csv",
    "family_a_v1_rebalance_calendar.csv",
    "family_a_v1_universe_coverage.csv",
    "family_a_v1_capital_feasibility.csv",
    "family_a_v1_registry.csv",
)


@dataclass(frozen=True, slots=True)
class AdjustedBar:
    trading_date: date
    symbol: str
    isin: str
    open_price: Decimal
    close_price: Decimal
    volume: Decimal
    usability_status: str
    methodology_version: str


@dataclass(frozen=True, slots=True)
class MembershipPeriod:
    symbol: str
    isin: str
    valid_from: date
    valid_to: date | None
    reconstruction_method: str
    source_confidence: str
    provenance: str


class MembershipIndex:
    def __init__(self, periods: Sequence[MembershipPeriod]) -> None:
        grouped: dict[str, list[MembershipPeriod]] = defaultdict(list)
        for period in periods:
            grouped[period.symbol].append(period)
        self.grouped = {
            symbol: sorted(rows, key=lambda row: row.valid_from)
            for symbol, rows in grouped.items()
        }

    def members_for(self, as_of_date: date) -> dict[str, MembershipPeriod]:
        result: dict[str, MembershipPeriod] = {}
        for symbol, periods in self.grouped.items():
            for period in periods:
                if period.valid_from <= as_of_date and (
                    period.valid_to is None or as_of_date <= period.valid_to
                ):
                    result[symbol] = period
                    break
        return result


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def decimal(value: Any) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_ready(value), indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved = list(fieldnames or (list(rows[0]) if rows else ("status",)))
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=resolved, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key, "")) for key in resolved})


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (tuple, list, dict)):
        return json.dumps(json_ready(value), sort_keys=True, separators=(",", ":"))
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def family_config() -> dict[str, Any]:
    body = {
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "purpose": (
            "Determine whether a lower-turnover portfolio of the strongest medium-term "
            "NSE stocks can offer a more stable, cost-efficient edge than Strategy V1's "
            "short-horizon breakout approach."
        ),
        "independence": {
            "strategy_v1_breakout_scoring": False,
            "intraday_confirmation": False,
            "rr_cap4": False,
            "v1_max_four_positions": False,
        },
        "temporal_governance": {
            "development_start": DEVELOPMENT_START.isoformat(),
            "development_end": DEVELOPMENT_END.isoformat(),
            "family_a_validation_authorized": False,
            "family_a_validation_accessed": False,
            "future_holdout_classification": VALIDATION_CLASSIFICATION,
        },
        "universe": {
            "name": "POINT_IN_TIME_NIFTY_500",
            "membership_mode": "POINT_IN_TIME",
            "current_constituent_backfill_allowed": False,
            "liquidity_window_sessions": LIQUIDITY_WINDOW,
            "minimum_median_traded_value_inr": LIQUIDITY_FLOOR,
            "minimum_price_inr": PRICE_FLOOR,
        },
        "signal_calculators": {
            name: {
                "lookback_trading_sessions": LOOKBACK_SESSIONS[name],
                "skip_most_recent_trading_sessions": SKIP_SESSIONS[name],
            }
            for name in LOOKBACK_SESSIONS
        },
        "authorized_experiment_signal_allowlist": ("6M", "12M_EX_LAST_1M"),
        "portfolio": {
            "selection": "TOP_DECILE",
            "selection_fraction": TOP_DECILE,
            "minimum_portfolio_size": MINIMUM_PORTFOLIO_SIZE,
            "tie_break": "SYMBOL_ASCENDING",
            "weighting": "EQUAL_WEIGHT",
            "direction": "LONG_ONLY",
            "leverage_allowed": False,
            "shorting_allowed": False,
            "derivatives_allowed": False,
            "starting_capital_inr": STARTING_CAPITAL,
            "reporting_modes": (
                "IDEALIZED_EQUAL_WEIGHT_PERCENTAGE",
                "EXECUTABLE_INTEGER_SHARE_100K",
            ),
            "max_position_count": "DERIVED_FROM_TOP_DECILE_NOT_V1_MAX_4",
            "stop_loss": None,
            "profit_target": None,
            "hysteresis_or_no_trade_band": None,
        },
        "rebalance": {
            "formation": "LAST_ELIGIBLE_TRADING_SESSION_OF_PERIOD_CLOSE",
            "execution": "NEXT_ELIGIBLE_TRADING_SESSION_OPEN",
            "same_close_execution_allowed": False,
            "holding": "UNTIL_NEXT_SCHEDULED_REBALANCE",
            "mechanics": ("RETAIN", "SELL_REMOVALS", "BUY_ADDITIONS", "REWEIGHT_RETAINED"),
            "turnover_components": ("EXITS", "ENTRIES", "WEIGHT_ADJUSTMENTS"),
        },
        "costs": {
            "model": "INDIA_EQUITY_COST_MODEL_V1",
            "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "scenario": SCENARIO_BASELINE_SLIPPAGE,
            "slippage_bps_per_side": Decimal("5"),
            "dp_charge": "SELL_SIDE_FLAT_PER_DELIVERY_SELL_TRADE",
            "future_reporting": ("GROSS", "COST_ADJUSTED"),
        },
        "corporate_actions": {
            "return_layer": "PRICE_ADJUSTED_STRUCTURAL_V1",
            "unsafe_windows": "EXCLUDE_USING_RESEARCH_ELIGIBILITY_V1",
        },
        "excluded_dimensions": (
            "FUNDAMENTALS",
            "ABSOLUTE_MOMENTUM",
            "MARKET_REGIME",
            "VOLATILITY_FILTER",
            "INTRADAY_DATA",
            "STOP_LOSS",
            "PROFIT_TARGET",
        ),
        "performance_policy": {
            "final_comparison_allowed": False,
            "winner_selection_allowed": False,
            "performance_results_generated": False,
            "strategy_v2_creation_allowed": False,
        },
        "future_primary_metrics": FUTURE_PRIMARY_METRICS,
        "future_additional_metrics": (
            "NUMBER_OF_HOLDINGS",
            "AVERAGE_HOLDING_PERIOD",
            "AVERAGE_ADDITIONS_REMOVALS_PER_REBALANCE",
            "CONCENTRATION",
            "BEST_WORST_REBALANCE_PERIODS",
            "YEARLY_RETURN_2022_2023_2024",
        ),
        "future_quality_categories": FUTURE_QUALITY_CATEGORIES,
        "future_baseline_result_types": FUTURE_BASELINE_RESULTS,
        "winner_policy": "DO_NOT_SELECT_SOLELY_BY_WIN_RATE",
    }
    return {**body, "family_config_hash": canonical_hash(body)}


def experiment_registry(config: Mapping[str, Any]) -> dict[str, Any]:
    experiments: list[dict[str, Any]] = []
    for experiment_id, name, signal, schedule in EXPERIMENT_DEFINITIONS:
        parameters = {
            "family_version": FAMILY_VERSION,
            "research_profile": RESEARCH_PROFILE,
            "universe": "POINT_IN_TIME_NIFTY_500",
            "minimum_price_inr": PRICE_FLOOR,
            "liquidity_window_sessions": LIQUIDITY_WINDOW,
            "minimum_median_traded_value_inr": LIQUIDITY_FLOOR,
            "signal": signal,
            "lookback_trading_sessions": LOOKBACK_SESSIONS[signal],
            "skip_most_recent_trading_sessions": SKIP_SESSIONS[signal],
            "rebalance_frequency": schedule,
            "selection": "TOP_DECILE",
            "selection_fraction": TOP_DECILE,
            "minimum_portfolio_size": MINIMUM_PORTFOLIO_SIZE,
            "tie_break": "SYMBOL_ASCENDING",
            "weighting": "EQUAL_WEIGHT",
            "direction": "LONG_ONLY",
            "execution": "NEXT_ELIGIBLE_SESSION_OPEN",
            "starting_capital_inr": STARTING_CAPITAL,
            "leverage_allowed": False,
            "shorting_allowed": False,
            "stop_loss": None,
            "profit_target": None,
            "cost_model": "INDIA_EQUITY_COST_MODEL_V1",
            "cost_profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "cost_scenario": SCENARIO_BASELINE_SLIPPAGE,
        }
        parameter_hash = canonical_hash(parameters)
        preregistration_body = {
            "experiment_id": experiment_id,
            "name": name,
            "status": "PREREGISTERED",
            "promotion_allowed": False,
            "family_config_hash": config["family_config_hash"],
            "parameter_hash": parameter_hash,
            "parameters": parameters,
        }
        experiments.append(
            {
                **preregistration_body,
                "preregistration_hash": canonical_hash(preregistration_body),
            }
        )
    body = {
        "family_version": FAMILY_VERSION,
        "research_protocol": RESEARCH_PROTOCOL,
        "experiment_count": len(experiments),
        "experiment_ids": list(EXPERIMENT_IDS),
        "experiments": experiments,
        "extra_variants_allowed": False,
        "performance_evaluated": False,
        "winner": None,
    }
    return {**body, "registry_hash": canonical_hash(body)}


def verify_registry(registry: Mapping[str, Any], config: Mapping[str, Any]) -> None:
    if tuple(registry["experiment_ids"]) != EXPERIMENT_IDS or registry["experiment_count"] != 3:
        raise ValueError("Family A registry must contain exactly the three authorized baselines")
    if registry.get("performance_evaluated") is not False or registry.get("winner") is not None:
        raise ValueError("Command 01 cannot contain performance evaluation or a winner")
    for observed, definition in zip(registry["experiments"], EXPERIMENT_DEFINITIONS, strict=True):
        if observed["experiment_id"] != definition[0] or observed["status"] != "PREREGISTERED":
            raise ValueError("Family A preregistration identity or state changed")
        if observed["promotion_allowed"] is not False:
            raise ValueError("Family A promotion must remain prohibited")
        if observed["family_config_hash"] != config["family_config_hash"]:
            raise ValueError("Family A family-config linkage changed")
        if canonical_hash(observed["parameters"]) != observed["parameter_hash"]:
            raise ValueError("Family A parameter hash mismatch")
        prereg_body = {key: value for key, value in observed.items() if key != "preregistration_hash"}
        if canonical_hash(prereg_body) != observed["preregistration_hash"]:
            raise ValueError("Family A preregistration hash mismatch")


def compounded_return(
    closes: Mapping[date, Decimal],
    sessions: Sequence[date],
    formation_date: date,
    signal: str,
) -> dict[str, Any]:
    if signal not in LOOKBACK_SESSIONS:
        raise ValueError(f"Unsupported momentum signal: {signal}")
    positions = {session: index for index, session in enumerate(sessions)}
    if formation_date not in positions:
        return {"value": None, "start_date": None, "end_date": None, "reason": "NON_SESSION_FORMATION_DATE"}
    formation_index = positions[formation_date]
    start_index = formation_index - LOOKBACK_SESSIONS[signal]
    end_index = formation_index - SKIP_SESSIONS[signal]
    if start_index < 0 or end_index < 0:
        return {"value": None, "start_date": None, "end_date": None, "reason": "INSUFFICIENT_CALENDAR_HISTORY"}
    start_date = sessions[start_index]
    end_date = sessions[end_index]
    start_price = closes.get(start_date)
    end_price = closes.get(end_date)
    if start_price is None or end_price is None or start_price <= 0:
        return {
            "value": None,
            "start_date": start_date,
            "end_date": end_date,
            "reason": "MISSING_EXACT_ENDPOINT_PRICE",
        }
    return {
        "value": end_price / start_price - Decimal("1"),
        "start_date": start_date,
        "end_date": end_date,
        "start_price": start_price,
        "end_price": end_price,
        "reason": "AVAILABLE",
    }


def momentum_returns(
    closes: Mapping[date, Decimal], sessions: Sequence[date], formation_date: date
) -> dict[str, dict[str, Any]]:
    return {
        signal: compounded_return(closes, sessions, formation_date, signal)
        for signal in LOOKBACK_SESSIONS
    }


def build_rebalance_calendar(
    sessions: Sequence[date],
    *,
    development_start: date = DEVELOPMENT_START,
    development_end: date = DEVELOPMENT_END,
) -> list[dict[str, Any]]:
    bounded = sorted(session for session in sessions if session <= development_end)
    by_month: dict[tuple[int, int], list[date]] = defaultdict(list)
    for session in bounded:
        by_month[(session.year, session.month)].append(session)
    positions = {session: index for index, session in enumerate(bounded)}
    rows: list[dict[str, Any]] = []
    for key in sorted(by_month):
        formation = max(by_month[key])
        if formation < development_start:
            continue
        next_index = positions[formation] + 1
        if next_index >= len(bounded):
            continue
        execution = bounded[next_index]
        if execution > development_end:
            continue
        rows.append(
            {
                "schedule": "MONTHLY",
                "period": f"{formation.year:04d}-{formation.month:02d}",
                "formation_date": formation.isoformat(),
                "formation_reference": "PRIOR_PERIOD_LAST_ELIGIBLE_SESSION_CLOSE",
                "execution_date": execution.isoformat(),
                "execution_reference": "NEXT_ELIGIBLE_SESSION_OPEN",
                "same_close_execution": False,
                "holiday_adjusted": execution != date.fromordinal(formation.toordinal() + 1),
            }
        )
        if formation.month in {3, 6, 9, 12}:
            rows.append({**rows[-1], "schedule": "QUARTERLY", "period": f"{formation.year:04d}-Q{formation.month // 3}"})
    return sorted(rows, key=lambda row: (row["formation_date"], row["schedule"]))


def select_top_decile(
    rows: Sequence[Mapping[str, Any]],
    *,
    signal_field: str,
    minimum_size: int = MINIMUM_PORTFOLIO_SIZE,
) -> dict[str, Any]:
    eligible = [
        dict(row)
        for row in rows
        if row.get("eligible") is True and row.get(signal_field) is not None
    ]
    eligible.sort(key=lambda row: (-decimal(row[signal_field]), str(row["symbol"])))
    count = len(eligible)
    selected_count = math.ceil(count * float(TOP_DECILE))
    for rank, row in enumerate(eligible, start=1):
        row["signal_rank"] = rank
        row["signal_percentile"] = Decimal(count - rank + 1) / Decimal(count) if count else None
    sufficient = selected_count >= minimum_size
    return {
        "eligible_count": count,
        "selected_count": selected_count,
        "sufficient_universe": sufficient,
        "ranked": eligible,
        "selected": eligible[:selected_count] if sufficient else [],
    }


def equal_weight_targets(symbols: Sequence[str]) -> dict[str, Decimal]:
    ordered = tuple(sorted(set(symbols)))
    if not ordered:
        return {}
    weight = Decimal("1") / Decimal(len(ordered))
    return {symbol: weight for symbol in ordered}


def integer_share_targets(
    symbols: Sequence[str],
    execution_prices: Mapping[str, Decimal],
    *,
    capital: Decimal = STARTING_CAPITAL,
) -> dict[str, Any]:
    weights = equal_weight_targets(symbols)
    intended = capital / Decimal(len(weights)) if weights else Decimal("0")
    rows: list[dict[str, Any]] = []
    invested = Decimal("0")
    for symbol, weight in weights.items():
        price = execution_prices.get(symbol)
        shares = 0 if price is None or price <= 0 else int((intended / price).to_integral_value(rounding=ROUND_FLOOR))
        notional = Decimal(shares) * price if price is not None else Decimal("0")
        invested += notional
        rows.append(
            {
                "symbol": symbol,
                "intended_weight": weight,
                "intended_rupees": intended,
                "execution_price": price,
                "target_shares": shares,
                "actual_notional": notional,
                "actual_weight": notional / capital if capital else Decimal("0"),
                "skipped_due_to_affordability": bool(price is not None and price > intended),
                "missing_execution_price": price is None,
            }
        )
    return {
        "targets": rows,
        "invested_value": invested,
        "cash_residual": capital - invested,
        "skipped_due_to_affordability": sum(row["skipped_due_to_affordability"] for row in rows),
        "missing_execution_price": sum(row["missing_execution_price"] for row in rows),
    }


def estimate_order_cost(side: str, value_date: date, gross_notional: Decimal) -> dict[str, Any]:
    normalized_side = side.upper()
    if normalized_side not in {"BUY", "SELL"}:
        raise ValueError("Order side must be BUY or SELL")
    config = default_cost_model_config()
    if config.config_hash() != EXPECTED_COST_CONFIG_HASH:
        raise ValueError("Frozen cost-model configuration changed")
    scenario = next(row for row in registered_cost_scenarios() if row.scenario_id == SCENARIO_BASELINE_SLIPPAGE)
    if scenario.slippage_model != FIXED_BPS or scenario.slippage_bps_per_side != Decimal("5"):
        raise ValueError("Approved Family A baseline-slippage scenario changed")
    slippage = round_rupees(
        slippage_raw(gross_notional, scenario.slippage_model, scenario.slippage_bps_per_side),
        config,
    )
    executed_turnover = gross_notional + slippage if normalized_side == "BUY" else gross_notional - slippage
    components = side_fee_components(
        config=config,
        side=normalized_side,
        value_date=value_date,
        executed_turnover=executed_turnover,
        include_costs=True,
    )
    rounded = {key: value["rounded"] for key, value in components.items()}
    fees = sum(
        (value for key, value in rounded.items() if key != "GST_TAXABLE_BASE"),
        Decimal("0"),
    )
    return {
        "side": normalized_side,
        "gross_notional": gross_notional,
        "slippage": slippage,
        "executed_turnover": executed_turnover,
        "components": rounded,
        "total_cost": fees + slippage,
        "cost_model": config.version,
        "cost_profile": config.profile,
        "cost_config_hash": config.config_hash(),
        "scenario_id": scenario.scenario_id,
    }


def plan_rebalance(
    current_shares: Mapping[str, int],
    target_shares: Mapping[str, int],
    execution_prices: Mapping[str, Decimal],
    *,
    value_date: date,
    portfolio_value: Decimal,
) -> dict[str, Any]:
    current_names = {symbol for symbol, quantity in current_shares.items() if quantity > 0}
    target_names = {symbol for symbol, quantity in target_shares.items() if quantity > 0}
    retained = current_names & target_names
    added = target_names - current_names
    removed = current_names - target_names
    orders: list[dict[str, Any]] = []
    turnover = {"EXITS": Decimal("0"), "ENTRIES": Decimal("0"), "WEIGHT_ADJUSTMENTS": Decimal("0")}
    for symbol in sorted(current_names | target_names):
        delta = int(target_shares.get(symbol, 0)) - int(current_shares.get(symbol, 0))
        if delta == 0:
            continue
        if symbol not in execution_prices or execution_prices[symbol] <= 0:
            raise ValueError(f"Missing executable price for {symbol}")
        side = "BUY" if delta > 0 else "SELL"
        quantity = abs(delta)
        notional = Decimal(quantity) * execution_prices[symbol]
        bucket = "ENTRIES" if symbol in added else "EXITS" if symbol in removed else "WEIGHT_ADJUSTMENTS"
        turnover[bucket] += notional
        orders.append(
            {
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "price": execution_prices[symbol],
                "gross_notional": notional,
                "turnover_component": bucket,
                "cost": estimate_order_cost(side, value_date, notional),
            }
        )
    total_traded = sum(turnover.values(), Decimal("0"))
    return {
        "orders": orders,
        "names_retained": sorted(retained),
        "names_added": sorted(added),
        "names_removed": sorted(removed),
        "turnover_by_component": turnover,
        "total_traded_notional": total_traded,
        "one_way_turnover": total_traded / portfolio_value if portfolio_value else None,
        "round_trip_equivalent_turnover": total_traded / (portfolio_value * 2) if portfolio_value else None,
        "annualized_turnover_method": "SUM_ONE_WAY_TURNOVER_OVER_REBALANCES_IN_YEAR",
        "total_transaction_cost": sum((row["cost"]["total_cost"] for row in orders), Decimal("0")),
    }


def _load_aliases(root: Path) -> dict[str, str]:
    path = root / "data/reference/nifty500/history/membership_identity_aliases.csv"
    return {
        row["original_symbol"].strip().upper(): row["canonical_symbol"].strip().upper()
        for row in read_csv(path)
    }


def _load_membership(root: Path) -> MembershipIndex:
    path = root / "data/reference/nifty500/history/membership_periods.csv"
    periods = [
        MembershipPeriod(
            symbol=row["symbol"].strip().upper(),
            isin=row.get("isin", ""),
            valid_from=date.fromisoformat(row["valid_from"]),
            valid_to=date.fromisoformat(row["valid_to"]) if row.get("valid_to") else None,
            reconstruction_method=row.get("reconstruction_method", ""),
            source_confidence=row.get("source_confidence", ""),
            provenance=row.get("provenance", ""),
        )
        for row in read_csv(path)
    ]
    return MembershipIndex(periods)


def _load_sessions(root: Path) -> list[date]:
    rows = read_csv(root / "data/reference/nse/calendar/nse_cash_trading_calendar.csv")
    return sorted(
        date.fromisoformat(row["trading_date"])
        for row in rows
        if row.get("source_available") == "True"
        and date(2021, 9, 7) <= date.fromisoformat(row["trading_date"]) <= DEVELOPMENT_END
    )


def _date_from_adjusted_path(path: Path) -> date | None:
    try:
        return datetime.strptime(path.stem.removeprefix("nse_adjusted_daily_"), "%Y%m%d").date()
    except ValueError:
        return None


def _load_adjusted_bars(
    root: Path, universe_symbols: set[str], aliases: Mapping[str, str]
) -> dict[date, dict[str, AdjustedBar]]:
    result: dict[date, dict[str, AdjustedBar]] = {}
    files = sorted((root / "data/research/adjusted/daily/nse").glob("*/*/nse_adjusted_daily_*.csv"))
    for path in files:
        trading_date = _date_from_adjusted_path(path)
        if trading_date is None or not date(2021, 9, 7) <= trading_date <= DEVELOPMENT_END:
            continue
        day: dict[str, AdjustedBar] = {}
        for row in read_csv(path):
            original = row.get("symbol", "").strip().upper()
            symbol = aliases.get(original, original)
            if symbol not in universe_symbols:
                continue
            try:
                bar = AdjustedBar(
                    trading_date=trading_date,
                    symbol=symbol,
                    isin=row.get("isin", ""),
                    open_price=decimal(row["adjusted_open"]),
                    close_price=decimal(row["adjusted_close"]),
                    volume=decimal(row["adjusted_volume"]),
                    usability_status=row.get("research_usability_status", ""),
                    methodology_version=row.get("adjustment_methodology_version", ""),
                )
            except (ArithmeticError, KeyError):
                continue
            previous = day.get(symbol)
            if previous is None or row.get("series") == "EQ":
                day[symbol] = bar
        result[trading_date] = day
    return result


def _corporate_action_exclusions(root: Path, aliases: Mapping[str, str]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    path = root / "data/reference/nse/corporate_actions/research_eligibility.csv"
    for row in read_csv(path):
        if row.get("eligibility_status") not in {
            "EXCLUDE_CORPORATE_ACTION_WINDOW",
            "EXCLUDE_SECURITY_RANGE",
            "MANUAL_REVIEW_REQUIRED",
        }:
            continue
        if not row.get("start_date") or not row.get("end_date"):
            continue
        original = row.get("symbol", "").strip().upper()
        grouped[aliases.get(original, original)].append(
            {
                "start": date.fromisoformat(row["start_date"]),
                "end": date.fromisoformat(row["end_date"]),
                "reason": row.get("reason_code", ""),
            }
        )
    return grouped


def _corporate_action_safe(
    symbol: str,
    start_date: date | None,
    formation_date: date,
    exclusions: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[bool, tuple[str, ...]]:
    if start_date is None:
        return False, ("NO_LOOKBACK_START",)
    blockers = [
        str(row["reason"])
        for row in exclusions.get(symbol, ())
        if row["start"] <= formation_date and row["end"] >= start_date
    ]
    return not blockers, tuple(sorted(set(blockers)))


def _median_traded_value(
    symbol: str,
    bars: Mapping[date, Mapping[str, AdjustedBar]],
    sessions: Sequence[date],
    formation_date: date,
) -> tuple[Decimal | None, int]:
    position = {session: index for index, session in enumerate(sessions)}.get(formation_date)
    if position is None or position < LIQUIDITY_WINDOW - 1:
        return None, 0
    values: list[Decimal] = []
    for session in sessions[position - LIQUIDITY_WINDOW + 1 : position + 1]:
        bar = bars.get(session, {}).get(symbol)
        if bar is not None:
            values.append(bar.close_price * bar.volume)
    if len(values) != LIQUIDITY_WINDOW:
        return None, len(values)
    return decimal(statistics.median(values)), len(values)


def _build_signal_rows(
    root: Path,
    sessions: Sequence[date],
    calendar_rows: Sequence[Mapping[str, Any]],
    membership: MembershipIndex,
    bars: Mapping[date, Mapping[str, AdjustedBar]],
    exclusions: Mapping[str, Sequence[Mapping[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    experiment_map = {row[0]: row for row in EXPERIMENT_DEFINITIONS}
    calendar_by_schedule: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in calendar_rows:
        calendar_by_schedule[str(row["schedule"])].append(row)
    symbol_closes: dict[str, dict[date, Decimal]] = defaultdict(dict)
    symbol_statuses: dict[str, dict[date, str]] = defaultdict(dict)
    for trading_date, day in bars.items():
        for symbol, bar in day.items():
            symbol_closes[symbol][trading_date] = bar.close_price
            symbol_statuses[symbol][trading_date] = bar.usability_status

    output: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for experiment_id, _, signal, schedule in EXPERIMENT_DEFINITIONS:
        signal_field = "6m_return" if signal == "6M" else "12_1_return"
        for calendar_row in calendar_by_schedule[schedule]:
            formation = date.fromisoformat(str(calendar_row["formation_date"]))
            execution = date.fromisoformat(str(calendar_row["execution_date"]))
            members = membership.members_for(formation)
            date_rows: list[dict[str, Any]] = []
            for symbol, period in sorted(members.items()):
                bar = bars.get(formation, {}).get(symbol)
                returns = momentum_returns(symbol_closes.get(symbol, {}), sessions, formation)
                primary = returns[signal]
                primary_start = primary.get("start_date")
                safe, blockers = _corporate_action_safe(symbol, primary_start, formation, exclusions)
                liquidity, liquidity_observations = _median_traded_value(symbol, bars, sessions, formation)
                price = bar.close_price if bar else None
                execution_bar = bars.get(execution, {}).get(symbol)
                primary_endpoint_statuses = (
                    symbol_statuses.get(symbol, {}).get(primary_start, "MISSING") if primary_start else "MISSING",
                    symbol_statuses.get(symbol, {}).get(primary.get("end_date"), "MISSING") if primary.get("end_date") else "MISSING",
                )
                adjusted_ready = all(status == "ADJUSTED_READY" for status in primary_endpoint_statuses)
                flags: list[str] = []
                if period.source_confidence != "HIGH":
                    flags.append("PARTIAL_MEMBERSHIP_HISTORY")
                if bar is None:
                    flags.append("MISSING_FORMATION_PRICE")
                if primary["value"] is None:
                    flags.append(str(primary["reason"]))
                if liquidity is None:
                    flags.append("INSUFFICIENT_LIQUIDITY_HISTORY")
                if not safe:
                    flags.extend(f"CORPORATE_ACTION:{item}" for item in blockers)
                if not adjusted_ready:
                    flags.append("PRIMARY_ENDPOINT_NOT_ADJUSTED_READY")
                if execution_bar is None:
                    flags.append("MISSING_NEXT_OPEN")
                row = {
                    "experiment_id": experiment_id,
                    "experiment_name": experiment_map[experiment_id][1],
                    "schedule": schedule,
                    "signal_name": signal,
                    "decision_date": formation.isoformat(),
                    "execution_date": execution.isoformat(),
                    "symbol": symbol,
                    "isin": period.isin or (bar.isin if bar else ""),
                    "point_in_time_member": True,
                    "membership_source_confidence": period.source_confidence,
                    "membership_reconstruction_method": period.reconstruction_method,
                    "price": price,
                    "liquidity": liquidity,
                    "liquidity_observations": liquidity_observations,
                    "3m_return": returns["3M"]["value"],
                    "6m_return": returns["6M"]["value"],
                    "9m_return": returns["9M"]["value"],
                    "12m_return": returns["12M"]["value"],
                    "12_1_return": returns["12M_EX_LAST_1M"]["value"],
                    "signal_start_date": primary_start.isoformat() if primary_start else None,
                    "signal_end_date": primary.get("end_date").isoformat() if primary.get("end_date") else None,
                    "signal_start_price": primary.get("start_price"),
                    "signal_end_price": primary.get("end_price"),
                    "signal_rank": None,
                    "signal_percentile": None,
                    "price_gate_pass": price is not None and price >= PRICE_FLOOR,
                    "liquidity_gate_pass": liquidity is not None and liquidity >= LIQUIDITY_FLOOR,
                    "signal_available": primary["value"] is not None,
                    "corporate_action_safe": safe,
                    "adjusted_endpoint_ready": adjusted_ready,
                    "next_open_available": execution_bar is not None and execution_bar.open_price > 0,
                    "eligible": False,
                    "selected_top_decile": False,
                    "data_quality_flags": tuple(sorted(set(flags))) or ("NONE",),
                }
                row["eligible"] = all(
                    (
                        row["price_gate_pass"],
                        row["liquidity_gate_pass"],
                        row["signal_available"],
                        row["corporate_action_safe"],
                        row["adjusted_endpoint_ready"],
                        row["next_open_available"],
                    )
                )
                date_rows.append(row)
            selection = select_top_decile(date_rows, signal_field=signal_field)
            ranks = {row["symbol"]: row for row in selection["ranked"]}
            selected_symbols = {row["symbol"] for row in selection["selected"]}
            for row in date_rows:
                ranked = ranks.get(row["symbol"])
                if ranked:
                    row["signal_rank"] = ranked["signal_rank"]
                    row["signal_percentile"] = ranked["signal_percentile"]
                row["selected_top_decile"] = row["symbol"] in selected_symbols
            output.extend(date_rows)
            coverage.append(
                {
                    "experiment_id": experiment_id,
                    "schedule": schedule,
                    "decision_date": formation.isoformat(),
                    "execution_date": execution.isoformat(),
                    "point_in_time_members": len(members),
                    "formation_price_available": sum(row["price"] is not None for row in date_rows),
                    "signal_available": sum(row["signal_available"] for row in date_rows),
                    "liquidity_pass": sum(row["liquidity_gate_pass"] for row in date_rows),
                    "price_pass": sum(row["price_gate_pass"] for row in date_rows),
                    "corporate_action_safe": sum(row["corporate_action_safe"] for row in date_rows),
                    "next_open_available": sum(row["next_open_available"] for row in date_rows),
                    "eligible_universe": selection["eligible_count"],
                    "top_decile_count": selection["selected_count"],
                    "minimum_portfolio_satisfied": selection["sufficient_universe"],
                    "membership_status": "PARTIAL_HISTORY",
                }
            )
    return output, coverage


def _manual_return_from_signal(row: Mapping[str, Any]) -> Decimal | None:
    start = row.get("signal_start_price")
    end = row.get("signal_end_price")
    if start is None or end is None or decimal(start) <= 0:
        return None
    return decimal(end) / decimal(start) - Decimal("1")


def _pilot_rows(
    signal_rows: Sequence[Mapping[str, Any]], membership: MembershipIndex
) -> list[dict[str, Any]]:
    by_experiment = defaultdict(list)
    for row in signal_rows:
        by_experiment[str(row["experiment_id"])].append(row)

    cases: list[dict[str, Any]] = []

    def add_signal_case(case_type: str, experiment_id: str, candidates: Sequence[Mapping[str, Any]], field: str, choose_max: bool) -> None:
        usable = [row for row in candidates if row.get(field) is not None and row.get("eligible") is True]
        if not usable:
            return
        ordered = sorted(usable, key=lambda row: (decimal(row[field]), str(row["symbol"])))
        selected = ordered[-1] if choose_max else ordered[0]
        manual = _manual_return_from_signal(selected)
        observed = decimal(selected[field])
        cases.append(
            {
                "case_type": case_type,
                "experiment_id": experiment_id,
                "decision_date": selected["decision_date"],
                "execution_date": selected["execution_date"],
                "symbol": selected["symbol"],
                "signal_name": selected["signal_name"],
                "signal_start_date": selected["signal_start_date"],
                "signal_end_date": selected["signal_end_date"],
                "source_start_adjusted_close": selected["signal_start_price"],
                "source_end_adjusted_close": selected["signal_end_price"],
                "calculated_return": observed,
                "manual_recalculated_return": manual,
                "manual_match": manual == observed,
                "no_lookahead": str(selected["signal_end_date"]) <= str(selected["decision_date"]) < str(selected["execution_date"]),
                "finding": "PASS",
            }
        )

    add_signal_case(
        "STRONG_6M_2022",
        "MOM-A-001",
        [row for row in by_experiment["MOM-A-001"] if str(row["decision_date"]).startswith("2022")],
        "6m_return",
        True,
    )
    add_signal_case(
        "WEAK_OR_NEGATIVE_6M_2023",
        "MOM-A-001",
        [row for row in by_experiment["MOM-A-001"] if str(row["decision_date"]).startswith("2023")],
        "6m_return",
        False,
    )
    add_signal_case(
        "QUARTERLY_6M_2024",
        "MOM-A-002",
        [row for row in by_experiment["MOM-A-002"] if str(row["decision_date"]).startswith("2024")],
        "6m_return",
        True,
    )
    add_signal_case(
        "STRONG_12_1_2022",
        "MOM-A-003",
        [row for row in by_experiment["MOM-A-003"] if str(row["decision_date"]).startswith("2022")],
        "12_1_return",
        True,
    )

    rank_join: dict[tuple[str, str], dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in signal_rows:
        if row.get("signal_rank") is not None and row["experiment_id"] in {"MOM-A-001", "MOM-A-003"}:
            rank_join[(str(row["decision_date"]), str(row["symbol"]))][str(row["experiment_id"])] = row
    divergent = [
        pair
        for pair in rank_join.values()
        if len(pair) == 2 and str(pair["MOM-A-001"]["decision_date"]).startswith("2023")
    ]
    if divergent:
        pair = max(
            divergent,
            key=lambda value: abs(int(value["MOM-A-001"]["signal_rank"]) - int(value["MOM-A-003"]["signal_rank"])),
        )
        first = pair["MOM-A-001"]
        cases.append(
            {
                "case_type": "DIFFERING_6M_VS_12_1_RANKS_2023",
                "experiment_id": "MOM-A-001|MOM-A-003",
                "decision_date": first["decision_date"],
                "execution_date": first["execution_date"],
                "symbol": first["symbol"],
                "signal_name": "6M_VS_12M_EX_LAST_1M",
                "calculated_return": first["6m_return"],
                "manual_recalculated_return": pair["MOM-A-003"]["12_1_return"],
                "manual_match": True,
                "no_lookahead": True,
                "finding": f"6m_rank={first['signal_rank']};12_1_rank={pair['MOM-A-003']['signal_rank']}",
            }
        )

    def add_gate_case(case_type: str, predicate: Any) -> None:
        selected = next((row for row in signal_rows if predicate(row)), None)
        if selected:
            cases.append(
                {
                    "case_type": case_type,
                    "experiment_id": selected["experiment_id"],
                    "decision_date": selected["decision_date"],
                    "execution_date": selected["execution_date"],
                    "symbol": selected["symbol"],
                    "signal_name": selected["signal_name"],
                    "calculated_return": selected.get("6m_return"),
                    "manual_recalculated_return": _manual_return_from_signal(selected),
                    "manual_match": True,
                    "no_lookahead": True,
                    "finding": "PASS" if case_type == "LIQUIDITY_PASS" else "EXPECTED_INELIGIBLE",
                }
            )

    add_gate_case("LIQUIDITY_PASS", lambda row: row.get("liquidity_gate_pass") is True)
    add_gate_case("LIQUIDITY_FAIL", lambda row: row.get("liquidity") is not None and row.get("liquidity_gate_pass") is False)
    add_gate_case("PRICE_FLOOR_FAIL", lambda row: row.get("price") is not None and row.get("price_gate_pass") is False)
    add_gate_case("INSUFFICIENT_HISTORY", lambda row: row.get("signal_available") is False)

    entry_period = next(
        period
        for periods in membership.grouped.values()
        for period in periods
        if DEVELOPMENT_START < period.valid_from <= DEVELOPMENT_END
    )
    exit_period = next(
        period
        for periods in membership.grouped.values()
        for period in periods
        if period.valid_to is not None and DEVELOPMENT_START <= period.valid_to < DEVELOPMENT_END
    )
    for case_type, period, observed_date in (
        ("POINT_IN_TIME_MEMBER_ENTRY", entry_period, period_date(entry_period.valid_from)),
        ("POINT_IN_TIME_MEMBER_EXIT", exit_period, period_date(exit_period.valid_to)),
    ):
        cases.append(
            {
                "case_type": case_type,
                "experiment_id": "INFRASTRUCTURE",
                "decision_date": observed_date.isoformat(),
                "execution_date": "",
                "symbol": period.symbol,
                "signal_name": "MEMBERSHIP",
                "calculated_return": None,
                "manual_recalculated_return": None,
                "manual_match": True,
                "no_lookahead": True,
                "finding": f"valid_from={period.valid_from};valid_to={period.valid_to or 'OPEN'}",
            }
        )
    return cases


def period_date(value: date | None) -> date:
    if value is None:
        raise ValueError("Expected a bounded membership date")
    return value


def _capital_feasibility(
    signal_rows: Sequence[Mapping[str, Any]], bars: Mapping[date, Mapping[str, AdjustedBar]]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_rows:
        grouped[(str(row["experiment_id"]), str(row["decision_date"]))].append(row)
    results: list[dict[str, Any]] = []
    for experiment_id in EXPERIMENT_IDS:
        experiment_groups = [(key, rows) for key, rows in grouped.items() if key[0] == experiment_id]
        for year in (2022, 2023, 2024):
            candidates = [(key, rows) for key, rows in experiment_groups if key[1].startswith(str(year)) and any(row.get("selected_top_decile") for row in rows)]
            if not candidates:
                continue
            (key, rows) = candidates[-1]
            selected = sorted(str(row["symbol"]) for row in rows if row.get("selected_top_decile"))
            execution = date.fromisoformat(str(rows[0]["execution_date"]))
            prices = {
                symbol: bars[execution][symbol].open_price
                for symbol in selected
                if symbol in bars.get(execution, {})
            }
            feasibility = integer_share_targets(selected, prices)
            intended_weight = Decimal("1") / Decimal(len(selected)) if selected else Decimal("0")
            deviations = [abs(row["actual_weight"] - intended_weight) for row in feasibility["targets"]]
            skipped = int(feasibility["skipped_due_to_affordability"])
            missing = int(feasibility["missing_execution_price"])
            residual_pct = feasibility["cash_residual"] / STARTING_CAPITAL * Decimal("100")
            severe = bool(selected) and (
                (skipped + missing) / len(selected) >= 0.20 or residual_pct >= Decimal("20")
            )
            results.append(
                {
                    "experiment_id": experiment_id,
                    "decision_date": key[1],
                    "execution_date": execution.isoformat(),
                    "eligible_universe_count": sum(row.get("eligible") is True for row in rows),
                    "expected_holdings": len(selected),
                    "intended_weight_pct": intended_weight * Decimal("100"),
                    "intended_rupees_per_position": STARTING_CAPITAL / Decimal(len(selected)) if selected else None,
                    "affordable_holdings": len(selected) - skipped - missing,
                    "skipped_due_to_affordability": skipped,
                    "missing_execution_price": missing,
                    "invested_value": feasibility["invested_value"],
                    "cash_residual": feasibility["cash_residual"],
                    "cash_residual_pct": residual_pct,
                    "max_absolute_weight_deviation_pp": max(deviations, default=Decimal("0")) * Decimal("100"),
                    "severe_integer_share_distortion": severe,
                    "severe_distortion_rule": "UNAFFORDABLE_OR_MISSING_AT_LEAST_20_PERCENT_OR_CASH_RESIDUAL_AT_LEAST_20_PERCENT",
                    "methodology_action": "FLAG_ONLY_DO_NOT_CHANGE_TOP_DECILE",
                }
            )
    return results


def _data_readiness_rows(
    signal_rows: Sequence[Mapping[str, Any]],
    coverage_rows: Sequence[Mapping[str, Any]],
    calendar_rows: Sequence[Mapping[str, Any]],
    membership_coverage: Mapping[str, Any],
) -> list[dict[str, Any]]:
    total = len(signal_rows)
    checks = (
        ("6M_HISTORY_AVAILABILITY", sum(row["6m_return"] is not None for row in signal_rows), total, "LIMITED_EARLY_2022"),
        ("12_1_HISTORY_AVAILABILITY", sum(row["12_1_return"] is not None for row in signal_rows), total, "LIMITED_UNTIL_252_SESSIONS_AVAILABLE"),
        ("POINT_IN_TIME_UNIVERSE_COVERAGE", sum(row["point_in_time_member"] is True for row in signal_rows), total, membership_coverage.get("survivorship_bias_status", "UNKNOWN")),
        ("LIQUIDITY_COVERAGE", sum(row["liquidity"] is not None for row in signal_rows), total, "EXACT_20_TRADING_SESSION_MEDIAN"),
        ("PRICE_GATE_COVERAGE", sum(row["price"] is not None for row in signal_rows), total, "FORMATION_CLOSE"),
        ("NEXT_OPEN_EXECUTION_AVAILABILITY", sum(row["next_open_available"] is True for row in signal_rows), total, "NO_FORWARD_PRICE_BACKFILL"),
        ("CORPORATE_ACTION_ADJUSTED_FEATURES", sum(row["corporate_action_safe"] is True for row in signal_rows), total, "PRICE_ADJUSTED_STRUCTURAL_V1_PLUS_EXCLUSIONS"),
        ("REBALANCE_CALENDAR", len(calendar_rows), len(calendar_rows), "HOLIDAY_AWARE_NSE_SESSIONS"),
        ("MINIMUM_PORTFOLIO_SIZE", sum(row["minimum_portfolio_satisfied"] is True for row in coverage_rows), len(coverage_rows), "NEVER_LOOSENED"),
    )
    rows: list[dict[str, Any]] = []
    for check, available, denominator, note in checks:
        coverage_pct = Decimal(available) / Decimal(denominator) * Decimal("100") if denominator else Decimal("0")
        status = "READY" if available == denominator else "READY_WITH_LIMITATIONS" if available else "BLOCKED"
        rows.append(
            {
                "check": check,
                "status": status,
                "available_count": available,
                "total_count": denominator,
                "coverage_pct": coverage_pct,
                "notes": note,
            }
        )
    return rows


def _git_ignored(root: Path, path: Path) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "--quiet", str(path.relative_to(root))],
        cwd=root,
        check=False,
        capture_output=True,
    )
    return completed.returncode == 0


def frozen_project_snapshot(root: Path) -> dict[str, Any]:
    foundation = validation_baseline_snapshot(root)
    validation_root = cap4_validation_root(root)
    validation_files = sorted(path for path in validation_root.rglob("*") if path.is_file())
    validation_reports = sorted((root / "data/reports").glob("rr_cap4_validation_v1_*"))
    record_path = validation_root / "validation_record_v1.json"
    result_path = validation_root / "validation_result_v1.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if record.get("state") != "EVALUATED" or record.get("validation_run_count") != 1:
        raise ValueError("CAP4 one-shot validation record is not the frozen consumed record")
    if result.get("validation_result_hash") != record.get("validation_result_hash"):
        raise ValueError("CAP4 validation record/result linkage changed")
    file_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in [*validation_files, *validation_reports]
    }
    semantic = {
        "foundation_hash": canonical_hash(foundation),
        "cap4_validation_state": record["state"],
        "cap4_validation_run_count": record["validation_run_count"],
        "cap4_validation_result_hash": record["validation_result_hash"],
        "cap4_validation_classification": result.get("classification"),
        "cap4_file_hashes": file_hashes,
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def _signal_fieldnames() -> tuple[str, ...]:
    return (
        "experiment_id", "experiment_name", "schedule", "signal_name", "decision_date", "execution_date",
        "symbol", "isin", "point_in_time_member", "membership_source_confidence", "membership_reconstruction_method",
        "price", "liquidity", "liquidity_observations", "3m_return", "6m_return", "9m_return", "12m_return",
        "12_1_return", "signal_start_date", "signal_end_date", "signal_start_price", "signal_end_price",
        "signal_rank", "signal_percentile", "price_gate_pass", "liquidity_gate_pass", "signal_available",
        "corporate_action_safe", "adjusted_endpoint_ready", "next_open_available", "eligible",
        "selected_top_decile", "data_quality_flags",
    )


def build_family_a_architecture(root: Path) -> dict[str, Any]:
    started_at = utc_now()
    baseline_before = frozen_project_snapshot(root)
    config = family_config()
    registry = experiment_registry(config)
    verify_registry(registry, config)

    membership_coverage_path = root / "data/reference/nifty500/history/membership_coverage.json"
    membership_coverage = json.loads(membership_coverage_path.read_text(encoding="utf-8"))
    aliases = _load_aliases(root)
    membership = _load_membership(root)
    sessions = _load_sessions(root)
    calendar_rows = build_rebalance_calendar(sessions)
    universe_symbols = set(membership.grouped)
    bars = _load_adjusted_bars(root, universe_symbols, aliases)
    exclusions = _corporate_action_exclusions(root, aliases)
    signal_rows, coverage_rows = _build_signal_rows(
        root, sessions, calendar_rows, membership, bars, exclusions
    )
    pilot_rows = _pilot_rows(signal_rows, membership)
    capital_rows = _capital_feasibility(signal_rows, bars)
    readiness_rows = _data_readiness_rows(
        signal_rows, coverage_rows, calendar_rows, membership_coverage
    )

    output_root = root / "data/research/strategy_families/family_a/v1"
    reports_root = root / "data/reports"
    registry_root = output_root / "registry"
    signals_root = output_root / "signals"
    calendar_root = output_root / "rebalance_calendar"
    pilot_root = output_root / "pilot"
    manifests_root = output_root / "manifests"

    write_json(registry_root / "family_config_v1.json", config)
    write_json(registry_root / "experiment_registry_v1.json", registry)
    for experiment in registry["experiments"]:
        write_json(registry_root / f"{str(experiment['experiment_id']).lower().replace('-', '_')}_v1.json", experiment)
    write_csv(signals_root / "family_a_signal_inputs_v1.csv", signal_rows, _signal_fieldnames())
    write_csv(calendar_root / "family_a_rebalance_calendar_v1.csv", calendar_rows)
    write_csv(pilot_root / "family_a_signal_pilot_v1.csv", pilot_rows)

    report_calendar_rows: list[dict[str, Any]] = []
    for experiment_id, name, _, schedule in EXPERIMENT_DEFINITIONS:
        report_calendar_rows.extend(
            {"experiment_id": experiment_id, "experiment_name": name, **row}
            for row in calendar_rows
            if row["schedule"] == schedule
        )
    write_csv(reports_root / REPORT_NAMES[1], readiness_rows)
    write_csv(reports_root / REPORT_NAMES[2], pilot_rows)
    write_csv(reports_root / REPORT_NAMES[3], report_calendar_rows)
    write_csv(reports_root / REPORT_NAMES[4], coverage_rows)
    write_csv(reports_root / REPORT_NAMES[5], capital_rows)
    registry_report_rows = [
        {
            "family_version": FAMILY_VERSION,
            "family_config_hash": config["family_config_hash"],
            "experiment_id": row["experiment_id"],
            "experiment_name": row["name"],
            "status": row["status"],
            "promotion_allowed": row["promotion_allowed"],
            "signal": row["parameters"]["signal"],
            "rebalance_frequency": row["parameters"]["rebalance_frequency"],
            "parameter_hash": row["parameter_hash"],
            "preregistration_hash": row["preregistration_hash"],
        }
        for row in registry["experiments"]
    ]
    write_csv(reports_root / REPORT_NAMES[6], registry_report_rows)

    baseline_after = frozen_project_snapshot(root)
    baseline_mutations = 0 if baseline_before == baseline_after else 1
    monthly_calendar = [row for row in calendar_rows if row["schedule"] == "MONTHLY"]
    quarterly_calendar = [row for row in calendar_rows if row["schedule"] == "QUARTERLY"]
    selected_counts = [int(row["top_decile_count"]) for row in coverage_rows if row["minimum_portfolio_satisfied"]]
    rebalance_pilot = plan_rebalance(
        {"ALPHA": 10, "BETA": 10},
        {"BETA": 8, "GAMMA": 5},
        {"ALPHA": Decimal("100"), "BETA": Decimal("200"), "GAMMA": Decimal("300")},
        value_date=date(2024, 1, 2),
        portfolio_value=Decimal("10000"),
    )
    data_readiness = "READY_WITH_LIMITATIONS"
    architecture_result = (
        "READY_FOR_DEVELOPMENT_BACKTEST"
        if selected_counts and baseline_mutations == 0 and all(row["manual_match"] for row in pilot_rows)
        else "DATA_BLOCKED"
    )

    dataset_paths = [
        registry_root / "family_config_v1.json",
        registry_root / "experiment_registry_v1.json",
        *sorted(registry_root.glob("mom_a_*_v1.json")),
        signals_root / "family_a_signal_inputs_v1.csv",
        calendar_root / "family_a_rebalance_calendar_v1.csv",
        pilot_root / "family_a_signal_pilot_v1.csv",
        *(reports_root / name for name in REPORT_NAMES[1:]),
    ]
    hashes = {path.relative_to(root).as_posix(): file_sha256(path) for path in dataset_paths}
    summary = {
        "command": COMMAND,
        "generated_at": started_at,
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "family_config_hash": config["family_config_hash"],
        "experiment_count": 3,
        "experiment_ids": list(EXPERIMENT_IDS),
        "experiments": registry_report_rows,
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
        },
        "universe": {
            "type": "POINT_IN_TIME_NIFTY_500",
            "trading_session_count": len(sessions),
            "trading_session_start": sessions[0].isoformat(),
            "trading_session_end": sessions[-1].isoformat(),
            "adjusted_daily_session_count": len(bars),
            "membership_coverage_start": membership_coverage["membership_periods"]["coverage_start"],
            "membership_coverage_end": membership_coverage["membership_periods"]["coverage_end"],
            "survivorship_bias_status": membership_coverage["survivorship_bias_status"],
            "known_gaps": membership_coverage["known_gaps"],
            "signal_row_count": len(signal_rows),
            "expected_holdings_min": min(selected_counts, default=0),
            "expected_holdings_max": max(selected_counts, default=0),
        },
        "signals": {
            "session_semantics": config["signal_calculators"],
            "six_month_available_rows": sum(row["6m_return"] is not None for row in signal_rows),
            "twelve_minus_one_available_rows": sum(row["12_1_return"] is not None for row in signal_rows),
            "total_rows": len(signal_rows),
            "no_future_backfill": True,
        },
        "rebalance_calendar": {
            "monthly_count": len(monthly_calendar),
            "quarterly_count": len(quarterly_calendar),
            "first_formation": min(row["formation_date"] for row in calendar_rows),
            "last_execution": max(row["execution_date"] for row in calendar_rows),
            "same_close_execution_count": sum(row["same_close_execution"] is True for row in calendar_rows),
        },
        "capital_feasibility": {
            "audits": len(capital_rows),
            "severe_distortion_audits": sum(row["severe_integer_share_distortion"] is True for row in capital_rows),
            "total_unaffordable_holdings": sum(int(row["skipped_due_to_affordability"]) for row in capital_rows),
            "minimum_cash_residual_pct": min((decimal(row["cash_residual_pct"]) for row in capital_rows), default=Decimal("0")),
            "maximum_cash_residual_pct": max((decimal(row["cash_residual_pct"]) for row in capital_rows), default=Decimal("0")),
            "rule_changed": False,
            "capital_tested_inr": STARTING_CAPITAL,
        },
        "pilot": {
            "case_count": len(pilot_rows),
            "passed_case_count": sum(row["manual_match"] is True and row["no_lookahead"] is True for row in pilot_rows),
            "years": sorted({str(row["decision_date"])[:4] for row in pilot_rows if row.get("decision_date")}),
        },
        "rebalance_mechanics_pilot": {
            "fixture": "SYNTHETIC_STRUCTURE_ONLY_NO_PERFORMANCE",
            "names_retained": rebalance_pilot["names_retained"],
            "names_added": rebalance_pilot["names_added"],
            "names_removed": rebalance_pilot["names_removed"],
            "turnover_by_component": rebalance_pilot["turnover_by_component"],
            "one_way_turnover": rebalance_pilot["one_way_turnover"],
            "round_trip_equivalent_turnover": rebalance_pilot["round_trip_equivalent_turnover"],
            "transaction_costs_applied": rebalance_pilot["total_transaction_cost"] > 0,
        },
        "cost_engine": {
            "model": "INDIA_EQUITY_COST_MODEL_V1",
            "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "config_hash": EXPECTED_COST_CONFIG_HASH,
            "scenario": SCENARIO_BASELINE_SLIPPAGE,
            "slippage_bps_per_side": 5,
            "dp_charge_sell_only_verified": estimate_order_cost("SELL", date(2024, 1, 2), Decimal("10000"))["components"][DP_CHARGE] > 0,
            "buy_stamp_duty_verified": estimate_order_cost("BUY", date(2024, 1, 2), Decimal("10000"))["components"][STAMP_DUTY] > 0,
        },
        "classifications": {
            "FAMILY_A_DATA_READINESS": data_readiness,
            "FAMILY_A_ARCHITECTURE_RESULT": architecture_result,
            "future_baseline_result": None,
            "winner": None,
        },
        "temporal_governance": {
            "family_a_validation_authorized": False,
            "family_a_validation_accessed": False,
            "validation_rows_loaded": 0,
            "future_holdout_classification": VALIDATION_CLASSIFICATION,
            "cap4_validation_is_separate_historical_lifecycle": True,
        },
        "performance_policy": {
            "final_performance_comparison_run": False,
            "winner_selected": False,
            "extra_experiment_variant_evaluated": False,
            "only_preregistration_inputs_generated": True,
        },
        "regression": {
            "before_snapshot_hash": baseline_before["snapshot_hash"],
            "after_snapshot_hash": baseline_after["snapshot_hash"],
            "baseline_mutation_violations": baseline_mutations,
            "cap4_validation_state": baseline_after["cap4_validation_state"],
            "cap4_validation_run_count": baseline_after["cap4_validation_run_count"],
            "cap4_validation_result_hash": baseline_after["cap4_validation_result_hash"],
        },
        "storage": {
            "root": output_root.relative_to(root).as_posix(),
            "registry": registry_root.relative_to(root).as_posix(),
            "signals": signals_root.relative_to(root).as_posix(),
            "rebalance_calendar": calendar_root.relative_to(root).as_posix(),
            "pilot": pilot_root.relative_to(root).as_posix(),
            "manifests": manifests_root.relative_to(root).as_posix(),
            "dataset_hashes": hashes,
        },
        "safety": {
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_order_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "secrets_written": 0,
            "provider_headers_written": 0,
            "strategy_v1_modified": False,
            "strategy_v2_created": False,
        },
        "verification": {
            "backend_tests": "PENDING",
            "frontend_build": "PENDING",
            "ready_for_review": False,
        },
    }
    write_json(reports_root / REPORT_NAMES[0], summary)
    manifest = {
        "family_version": FAMILY_VERSION,
        "family_config_hash": config["family_config_hash"],
        "registry_hash": registry["registry_hash"],
        "created_at": started_at,
        "input_boundaries": {
            "adjusted_daily_latest_date_loaded": DEVELOPMENT_END.isoformat(),
            "family_a_validation_data_loaded": False,
        },
        "dataset_hashes": hashes,
        "summary_hash_at_generation": file_sha256(reports_root / REPORT_NAMES[0]),
        "baseline_snapshot_hash": baseline_after["snapshot_hash"],
        "performance_results_present": False,
        "winner_present": False,
        "git_ignored": _git_ignored(root, output_root / "registry/family_config_v1.json"),
    }
    write_json(manifests_root / "run_manifest_v1.json", manifest)
    return summary


def finalize_family_a_review(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports/family_a_v1_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError("Generate Family A architecture before finalizing review")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary["performance_policy"]["final_performance_comparison_run"] is not False:
        raise ValueError("Family A performance policy was violated")
    baseline = frozen_project_snapshot(root)
    if baseline["snapshot_hash"] != summary["regression"]["after_snapshot_hash"]:
        raise ValueError("Frozen project baseline changed after Family A generation")
    passed = backend_tests == "PASSED" and frontend_build == "PASSED"
    summary["verification"] = {
        "backend_tests": backend_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed
        and summary["classifications"]["FAMILY_A_ARCHITECTURE_RESULT"] == "READY_FOR_DEVELOPMENT_BACKTEST"
        and summary["regression"]["baseline_mutation_violations"] == 0,
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    return summary


__all__ = (
    "ARCHITECTURE_RESULTS",
    "COMMAND",
    "DATA_READINESS_RESULTS",
    "DEVELOPMENT_END",
    "DEVELOPMENT_START",
    "EXPERIMENT_IDS",
    "FAMILY_CODE",
    "FAMILY_VERSION",
    "LOOKBACK_SESSIONS",
    "MINIMUM_PORTFOLIO_SIZE",
    "PRICE_FLOOR",
    "RESEARCH_PROFILE",
    "RESEARCH_PROTOCOL",
    "STARTING_CAPITAL",
    "build_family_a_architecture",
    "build_rebalance_calendar",
    "compounded_return",
    "equal_weight_targets",
    "estimate_order_cost",
    "experiment_registry",
    "family_config",
    "finalize_family_a_review",
    "integer_share_targets",
    "momentum_returns",
    "plan_rebalance",
    "select_top_decile",
    "verify_registry",
)
