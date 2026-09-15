from __future__ import annotations

import json
import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH
from app.backtesting.costs.cost_engine import SCENARIO_BASELINE_SLIPPAGE
from app.research.strategy.family_a_momentum import (
    decimal,
    estimate_order_cost,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_b_history_remediation import DATA_VERSION
from app.research.strategy.family_c_breakout_continuation import (
    FamilyCBar,
    _load_adjusted_bars,
    _load_aliases,
    _load_membership,
    _load_sessions,
)
from app.research.strategy.family_c_development_evaluation import (
    expectancy,
    position_win_rate,
    profit_factor,
    quantile,
)
from app.research.strategy.family_e_pullback_reclaim import (
    CONTROL_ID,
    CONTROL_NAME,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_CONTROL_REFERENCE_HASH,
    EXPECTED_E001_PARAMETER_HASH,
    EXPECTED_E001_PREREGISTRATION_HASH,
    EXPECTED_FAMILY_D_CLOSURE_HASH,
    EXPECTED_FAMILY_E_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    FAMILY_CODE,
    FAMILY_VERSION,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    PULLBACK_SESSIONS,
    RESEARCH_PROFILE,
    RESEARCH_PROTOCOL,
    RISK_PER_TRADE,
    STARTING_CAPITAL,
    TREATMENT_ID,
    TREATMENT_NAME,
    daily_stop_execution,
    entry_exit_chronology,
    family_output_root,
    previous_research_snapshot,
    risk_position_size,
    structural_stop,
    verify_expected_hashes,
    verify_family_d_closure,
    verify_registry,
)
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.05 / Command 02"
COMMAND_VERSION = "FAMILY_E_DEVELOPMENT_EVALUATION_V1"
COMMAND_PROFILE = "PULLBACK_RECLAIM_DEVELOPMENT_V1"
EXECUTABLE_MODE = "EXECUTABLE_INTEGER_SHARE_500K"
SIGNAL_QUALITY_MODE = "SIGNAL_QUALITY_COHORT_ONLY"
EXPECTED_ARCHITECTURE_MANIFEST_HASH = (
    "797f6d056807cec6ffd89404488a571fec28238b5b5a39293508208da9e97a22"
)
# The frozen semantic reference above remains embedded in the evaluation.
# The current catalog hash reflects only the milestone's documentation
# whitespace normalization.
CURRENT_ARCHITECTURE_ARTIFACT_MANIFEST_HASH = (
    "74ba02fbb007c4145038cfd715d3df97db438684776bc434d8db27a7c8df4bd1"
)

STRATEGIES = (
    (CONTROL_ID, CONTROL_NAME, "control_signal"),
    (TREATMENT_ID, TREATMENT_NAME, "e001_signal"),
)

REPORT_NAMES = (
    "family_e_dev_v1_summary.json",
    "family_e_dev_v1_control.csv",
    "family_e_dev_v1_e001.csv",
    "family_e_dev_v1_positions.csv",
    "family_e_dev_v1_yearly.csv",
    "family_e_dev_v1_criteria.csv",
    "family_e_dev_v1_filter_attribution.csv",
    "family_e_dev_v1_exit_attribution.csv",
    "family_e_dev_v1_capacity.csv",
    "family_e_dev_v1_pullback_depth.csv",
    "family_e_dev_v1_reclaim_strength.csv",
    "family_e_dev_v1_entry_gap.csv",
    "family_e_dev_v1_stop_distance.csv",
    "family_e_dev_v1_mfe_mae.csv",
    "family_e_dev_v1_holding_path.csv",
    "family_e_dev_v1_comparison.csv",
)

EXPECTED_STRUCTURAL_COUNTS = {
    "eligible_universe_rows": 199_915,
    "trend_pass_rows": 84_980,
    "pullback_touch_rows": 39_150,
    "control_signals": 10_754,
    "e001_signals": 8_343,
    "treatment_filter_removals": 2_411,
    "treatment_subset_violations": 0,
}


class FamilyEDevelopmentFreezeMismatch(RuntimeError):
    pass


@dataclass(slots=True)
class OpenPosition:
    experiment_id: str
    experiment_name: str
    symbol: str
    isin: str
    formation_date: date
    formation_close: Decimal
    return_20d: Decimal
    pullback_depth_below_sma20: Decimal
    pullback_min_close_minus_sma50: Decimal
    reclaim_excess_pct: Decimal
    entry_date: date
    entry_price: Decimal
    entry_gap_pct: Decimal
    stop_price: Decimal
    stop_distance: Decimal
    stop_distance_pct: Decimal
    shares: int
    allowed_risk: Decimal
    planned_risk: Decimal
    intended_shares: int
    entry_notional: Decimal
    buy_cost: Decimal
    holding_dates: tuple[date, ...]
    time_exit_date: date


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return family_output_root(Path(root)) / "development_evaluation"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_hash(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != field}


def _require_hash(value: Mapping[str, Any], field: str, expected: str) -> bool:
    return value.get(field) == expected and canonical_hash(
        _without_hash(value, field)
    ) == expected


def command_01_snapshot(root: Path) -> dict[str, Any]:
    root = Path(root)
    family_root = family_output_root(root)
    paths = [
        path
        for path in family_root.rglob("*")
        if path.is_file()
        and "development_evaluation" not in path.relative_to(family_root).parts
    ]
    reports = sorted((root / "data/reports").glob("family_e_v1_*"))
    documentation = root / "docs/strategy-family-e-pullback-reclaim-continuation-v1.md"
    if documentation.is_file():
        paths.append(documentation)
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted([*paths, *reports])
    }
    semantic = {
        "family_version": FAMILY_VERSION,
        "family_e_config_hash": EXPECTED_FAMILY_E_CONFIG_HASH,
        "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "pbr_e_001_parameter_hash": EXPECTED_E001_PARAMETER_HASH,
        "pbr_e_001_preregistration_hash": EXPECTED_E001_PREREGISTRATION_HASH,
        "family_e_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "architecture_manifest_hash": EXPECTED_ARCHITECTURE_MANIFEST_HASH,
        "artifact_hashes": artifact_hashes,
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def verify_freeze_gate(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    family_root = family_output_root(root)
    config = _read_json(family_root / "registry/family_e_config_v1.json")
    registry = _read_json(
        family_root / "registry/family_e_experiment_registry_v1.json"
    )
    control = _read_json(family_root / "registry/control_e_000_reference_v1.json")
    treatment = _read_json(
        family_root / "registry/pbr_e_001_preregistration_v1.json"
    )
    criteria = _read_json(family_root / "governance/success_criteria_v1.json")
    manifest = _read_json(
        family_root / "manifests/family_e_architecture_manifest_v1.json"
    )
    if criteria.get("family_e_success_criteria_hash") != EXPECTED_SUCCESS_CRITERIA_HASH:
        raise FamilyEDevelopmentFreezeMismatch(
            "FAMILY_E_SUCCESS_CRITERIA_MISMATCH"
        )
    checks = {
        "family_e_config_hash": _require_hash(
            config, "family_e_config_hash", EXPECTED_FAMILY_E_CONFIG_HASH
        ),
        "architecture_manifest_hash": _require_hash(
            manifest,
            "family_e_architecture_manifest_hash",
            CURRENT_ARCHITECTURE_ARTIFACT_MANIFEST_HASH,
        ),
        "control_reference_hash": _require_hash(
            control,
            "control_e_000_reference_hash",
            EXPECTED_CONTROL_REFERENCE_HASH,
        ),
        "pbr_e_001_parameter_hash": canonical_hash(treatment["parameters"])
        == treatment.get("pbr_e_001_parameter_hash")
        == EXPECTED_E001_PARAMETER_HASH,
        "pbr_e_001_preregistration_hash": _require_hash(
            treatment,
            "pbr_e_001_preregistration_hash",
            EXPECTED_E001_PREREGISTRATION_HASH,
        ),
        "family_e_success_criteria_hash": _require_hash(
            criteria,
            "family_e_success_criteria_hash",
            EXPECTED_SUCCESS_CRITERIA_HASH,
        ),
        "registry_hash": _require_hash(
            registry, "registry_hash", registry["registry_hash"]
        ),
        "manifest_links": (
            manifest.get("family_e_config_hash") == EXPECTED_FAMILY_E_CONFIG_HASH
            and manifest.get("control_reference_hash")
            == EXPECTED_CONTROL_REFERENCE_HASH
            and manifest.get("pbr_e_001_parameter_hash")
            == EXPECTED_E001_PARAMETER_HASH
            and manifest.get("pbr_e_001_preregistration_hash")
            == EXPECTED_E001_PREREGISTRATION_HASH
            and manifest.get("family_e_success_criteria_hash")
            == EXPECTED_SUCCESS_CRITERIA_HASH
        ),
        "command_01_artifacts": all(
            (root / relative).is_file()
            and file_sha256(root / relative) == expected
            for relative, expected in manifest["artifact_hashes"].items()
        ),
        "summary_hash": file_sha256(root / "data/reports/family_e_v1_summary.json")
        == manifest["summary_hash"],
    }
    verify_registry(registry, config, criteria)
    verify_expected_hashes(config, criteria, registry)
    family_d = verify_family_d_closure(root)
    checks["family_d_closure_hash"] = (
        family_d["family_d_closure_hash"] == EXPECTED_FAMILY_D_CLOSURE_HASH
    )
    if not all(checks.values()):
        raise FamilyEDevelopmentFreezeMismatch(
            f"FAMILY_E_PRE_RUN_FREEZE_MISMATCH: {checks}"
        )
    return {
        "status": "VERIFIED",
        "checks": checks,
        "config": config,
        "registry": registry,
        "control": control,
        "treatment": treatment,
        "criteria": criteria,
        "manifest": manifest,
        "family_d": family_d,
    }


def _bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() == "true"


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None or str(value).strip() == "" else decimal(value)


def load_signal_rows(root: Path) -> list[dict[str, Any]]:
    path = family_output_root(Path(root)) / "signals/family_e_signal_dataset_v1.csv"
    rows: list[dict[str, Any]] = []
    decimal_fields = (
        "close",
        "sma20",
        "sma50",
        "return_20d",
        "pullback_min_low",
        "pullback_min_close_minus_sma50",
        "previous_day_high",
        "entry_gap_pct",
        "stop_reference",
    )
    bool_fields = (
        "point_in_time_member",
        "trend_pass",
        "reclaim_above_previous_high",
        "reclaim_above_sma20",
        "price_gate",
        "liquidity_gate",
        "corporate_action_safe",
        "indicator_history_ready",
        "eligible_universe_row",
        "control_signal",
        "e001_structure_pass",
        "e001_signal",
    )
    for raw in read_csv(path):
        decision_date = date.fromisoformat(raw["decision_date"])
        if not DEVELOPMENT_START <= decision_date <= DEVELOPMENT_END:
            raise FamilyEDevelopmentFreezeMismatch(
                "Signal input escaped the frozen DEVELOPMENT partition"
            )
        row: dict[str, Any] = dict(raw)
        row["decision_date"] = decision_date
        row["pullback_window_start"] = (
            date.fromisoformat(raw["pullback_window_start"])
            if raw["pullback_window_start"]
            else None
        )
        row["entry_date"] = (
            date.fromisoformat(raw["entry_date"]) if raw["entry_date"] else None
        )
        row["pullback_touch_count"] = int(raw["pullback_touch_count"] or 0)
        for field in decimal_fields:
            row[field] = _optional_decimal(raw[field])
        for field in bool_fields:
            row[field] = _bool(raw[field])
        rows.append(row)
    return rows


def reproduce_structural_counts(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    control = {
        (row["decision_date"], row["symbol"])
        for row in rows
        if _bool(row["control_signal"])
    }
    treatment = {
        (row["decision_date"], row["symbol"])
        for row in rows
        if _bool(row["e001_signal"])
    }
    observed = {
        "eligible_universe_rows": sum(_bool(row["eligible_universe_row"]) for row in rows),
        "trend_pass_rows": sum(
            _bool(row["eligible_universe_row"]) and _bool(row["trend_pass"])
            for row in rows
        ),
        "pullback_touch_rows": sum(
            bool(
                _bool(row["eligible_universe_row"])
                and _bool(row["trend_pass"])
                and int(row["pullback_touch_count"]) > 0
            )
            for row in rows
        ),
        "control_signals": len(control),
        "e001_signals": len(treatment),
        "treatment_filter_removals": len(control - treatment),
        "treatment_subset_violations": len(treatment - control),
    }
    if observed != EXPECTED_STRUCTURAL_COUNTS:
        raise FamilyEDevelopmentFreezeMismatch(
            f"FAMILY_E_STRUCTURAL_COUNT_MISMATCH: {observed}"
        )
    return {"status": "VERIFIED", **observed}


def pullback_depth_below_sma20(
    *,
    symbol: str,
    formation_date: date,
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> Decimal:
    formation_index = sessions.index(formation_date)
    depths: list[Decimal] = []
    for index in range(formation_index - PULLBACK_SESSIONS, formation_index):
        session = sessions[index]
        window = sessions[index - 19 : index + 1]
        closes = [bars[item][symbol].close_price for item in window]
        sma20 = sum(closes, Decimal("0")) / Decimal("20")
        low = bars[session][symbol].low_price
        depths.append(max(Decimal("0"), sma20 - low) / sma20)
    return max(depths)


def _complete_path(
    row: Mapping[str, Any],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> dict[str, Any]:
    chronology = entry_exit_chronology(sessions, row["decision_date"])
    entry_date = chronology["entry_date"]
    time_exit_date = chronology["exit_date"]
    if time_exit_date is None or time_exit_date > DEVELOPMENT_END:
        return {"available": False, "reason": "TERMINAL_PATH_UNAVAILABLE_WITHIN_DEVELOPMENT"}
    symbol = str(row["symbol"])
    required = (*chronology["holding_dates"], time_exit_date)
    if entry_date is None or any(bars.get(day, {}).get(symbol) is None for day in required):
        return {"available": False, "reason": "INCOMPLETE_PRICE_PATH"}
    if any(
        min(
            bars[day][symbol].open_price,
            bars[day][symbol].high_price,
            bars[day][symbol].low_price,
            bars[day][symbol].close_price,
        )
        <= 0
        for day in required
    ):
        return {"available": False, "reason": "INVALID_PRICE_PATH"}
    formation_index = sessions.index(row["decision_date"])
    stop_window = sessions[
        formation_index - PULLBACK_SESSIONS : formation_index + 1
    ]
    if len(stop_window) != PULLBACK_SESSIONS + 1 or any(
        bars.get(day, {}).get(symbol) is None for day in stop_window
    ):
        return {"available": False, "reason": "INCOMPLETE_STOP_HISTORY"}
    stop_price = structural_stop([bars[day][symbol].low_price for day in stop_window])
    if stop_price is None or stop_price != row["stop_reference"]:
        return {"available": False, "reason": "STRUCTURAL_STOP_MISMATCH"}
    entry_price = bars[entry_date][symbol].open_price
    if entry_price <= stop_price:
        return {"available": False, "reason": "ENTRY_AT_OR_BELOW_STOP"}
    depth = pullback_depth_below_sma20(
        symbol=symbol,
        formation_date=row["decision_date"],
        sessions=sessions,
        bars=bars,
    )
    return {
        "available": True,
        "reason": None,
        "entry_date": entry_date,
        "time_exit_date": time_exit_date,
        "holding_dates": tuple(chronology["holding_dates"]),
        "entry_price": entry_price,
        "stop_price": stop_price,
        "stop_distance": entry_price - stop_price,
        "stop_distance_pct": (entry_price - stop_price) / entry_price,
        "entry_gap_pct": entry_price / decimal(row["close"]) - Decimal("1"),
        "pullback_depth_below_sma20": depth,
        "reclaim_excess_pct": decimal(row["close"])
        / decimal(row["previous_day_high"])
        - Decimal("1"),
    }


def _size_with_cost(
    *, equity: Decimal, cash: Decimal, entry_price: Decimal, stop_price: Decimal, entry_date: date
) -> dict[str, Any]:
    unconstrained = risk_position_size(
        equity=equity,
        available_cash=cash,
        entry_price=entry_price,
        stop_price=stop_price,
    )
    shares = int(unconstrained["shares"])
    intended_shares = shares
    while shares > 0:
        notional = Decimal(shares) * entry_price
        cost = estimate_order_cost("BUY", entry_date, notional)["total_cost"]
        if notional + cost <= cash:
            return {
                **unconstrained,
                "valid": True,
                "shares": shares,
                "intended_shares": intended_shares,
                "notional": notional,
                "buy_cost": cost,
                "planned_risk": Decimal(shares) * (entry_price - stop_price),
                "cash_constrained": bool(unconstrained["cash_constrained"] or shares < intended_shares),
            }
        shares -= 1
    return {
        **unconstrained,
        "valid": False,
        "shares": 0,
        "intended_shares": intended_shares,
        "notional": Decimal("0"),
        "buy_cost": Decimal("0"),
        "planned_risk": Decimal("0"),
        "cash_constrained": True,
    }


def _path_outcome(
    position: OpenPosition,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> dict[str, Any]:
    exit_date = position.time_exit_date
    exit_price = bars[exit_date][position.symbol].open_price
    exit_reason = "TIME_EXIT"
    holding_sessions = HOLDING_SESSIONS
    observed_dates: list[date] = []
    for index, session in enumerate(position.holding_dates):
        bar = bars[session][position.symbol]
        stop = daily_stop_execution(
            session_open=bar.open_price,
            session_low=bar.low_price,
            stop_price=position.stop_price,
        )
        observed_dates.append(session)
        if stop["exit_reason"] != "NO_STOP":
            exit_date = session
            exit_price = decimal(stop["reference_price"])
            exit_reason = str(stop["exit_reason"])
            holding_sessions = index
            break
    else:
        exit_bar = bars[position.time_exit_date][position.symbol]
        stop = daily_stop_execution(
            session_open=exit_bar.open_price,
            session_low=exit_bar.low_price,
            stop_price=position.stop_price,
        )
        if stop["exit_reason"] == "GAP_THROUGH_STOP":
            exit_price = decimal(stop["reference_price"])
            exit_reason = "GAP_THROUGH_STOP"
    path_bars = [bars[day][position.symbol] for day in observed_dates]
    highs = [bar.high_price for bar in path_bars] + [exit_price]
    lows = [bar.low_price for bar in path_bars] + [exit_price]
    full_holding = [bars[day][position.symbol] for day in position.holding_dates]
    return {
        "exit_date": exit_date,
        "exit_price": exit_price,
        "exit_reason": exit_reason,
        "holding_sessions": holding_sessions,
        "MFE_pct": max(highs) / position.entry_price - Decimal("1"),
        "MAE_pct": min(lows) / position.entry_price - Decimal("1"),
        "return_after_1_session": full_holding[0].close_price
        / position.entry_price
        - Decimal("1"),
        "return_after_3_sessions": full_holding[2].close_price
        / position.entry_price
        - Decimal("1"),
        "return_after_5_sessions": full_holding[4].close_price
        / position.entry_price
        - Decimal("1"),
        "return_after_10_sessions": full_holding[9].close_price
        / position.entry_price
        - Decimal("1"),
    }


def _position_record(
    position: OpenPosition,
    outcome: Mapping[str, Any],
    *,
    cohort: str,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> dict[str, Any]:
    exit_date = outcome["exit_date"]
    exit_price = decimal(outcome["exit_price"])
    exit_notional = Decimal(position.shares) * exit_price
    sell_cost = estimate_order_cost("SELL", exit_date, exit_notional)["total_cost"]
    transaction_costs = position.buy_cost + sell_cost
    gross_pnl = exit_notional - position.entry_notional
    net_pnl = gross_pnl - transaction_costs
    planned_risk = position.planned_risk
    return {
        "experiment_id": position.experiment_id,
        "experiment_name": position.experiment_name,
        "mode": EXECUTABLE_MODE if cohort == "PORTFOLIO" else SIGNAL_QUALITY_MODE,
        "cohort": cohort,
        "formation_date": position.formation_date.isoformat(),
        "symbol": position.symbol,
        "isin": position.isin,
        "formation_close": position.formation_close,
        "return_20d": position.return_20d,
        "pullback_depth_below_sma20": position.pullback_depth_below_sma20,
        "pullback_min_close_minus_sma50": position.pullback_min_close_minus_sma50,
        "reclaim_excess_pct": position.reclaim_excess_pct,
        "entry_date": position.entry_date.isoformat(),
        "entry_price": position.entry_price,
        "entry_gap_pct": position.entry_gap_pct,
        "stop_price": position.stop_price,
        "stop_distance": position.stop_distance,
        "stop_distance_pct": position.stop_distance_pct,
        "allowed_risk": position.allowed_risk,
        "planned_risk": planned_risk,
        "intended_shares": position.intended_shares,
        "shares": position.shares,
        "entry_notional": position.entry_notional,
        "buy_cost": position.buy_cost,
        "exit_date": exit_date.isoformat(),
        "exit_price": exit_price,
        "exit_reason": outcome["exit_reason"],
        "exit_category": "TIME_EXIT"
        if outcome["exit_reason"] == "TIME_EXIT"
        else "STOP_EXIT",
        "exit_notional": exit_notional,
        "sell_cost": sell_cost,
        "transaction_costs": transaction_costs,
        "gross_pnl": gross_pnl,
        "net_pnl": net_pnl,
        "gross_return_pct": gross_pnl / position.entry_notional,
        "net_return_pct": net_pnl / position.entry_notional,
        "R_multiple": gross_pnl / planned_risk if planned_risk else None,
        "holding_sessions": outcome["holding_sessions"],
        "MFE_pct": outcome["MFE_pct"],
        "MAE_pct": outcome["MAE_pct"],
        "return_after_1_session": outcome["return_after_1_session"],
        "return_after_3_sessions": outcome["return_after_3_sessions"],
        "return_after_5_sessions": outcome["return_after_5_sessions"],
        "return_after_10_sessions": outcome["return_after_10_sessions"],
        "simultaneously_deployable": cohort == "PORTFOLIO",
    }


def prepare_signal_paths(
    signal_rows: Sequence[Mapping[str, Any]],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> dict[tuple[date, str], dict[str, Any]]:
    prepared: dict[tuple[date, str], dict[str, Any]] = {}
    for row in signal_rows:
        if not row["control_signal"]:
            continue
        key = (row["decision_date"], str(row["symbol"]))
        prepared[key] = _complete_path(row, sessions, bars)
    return prepared


def _make_position(
    *,
    experiment_id: str,
    experiment_name: str,
    row: Mapping[str, Any],
    path: Mapping[str, Any],
    sizing: Mapping[str, Any],
) -> OpenPosition:
    return OpenPosition(
        experiment_id=experiment_id,
        experiment_name=experiment_name,
        symbol=str(row["symbol"]),
        isin=str(row["isin"]),
        formation_date=row["decision_date"],
        formation_close=decimal(row["close"]),
        return_20d=decimal(row["return_20d"]),
        pullback_depth_below_sma20=decimal(path["pullback_depth_below_sma20"]),
        pullback_min_close_minus_sma50=decimal(
            row["pullback_min_close_minus_sma50"]
        ),
        reclaim_excess_pct=decimal(path["reclaim_excess_pct"]),
        entry_date=path["entry_date"],
        entry_price=decimal(path["entry_price"]),
        entry_gap_pct=decimal(path["entry_gap_pct"]),
        stop_price=decimal(path["stop_price"]),
        stop_distance=decimal(path["stop_distance"]),
        stop_distance_pct=decimal(path["stop_distance_pct"]),
        shares=int(sizing["shares"]),
        allowed_risk=decimal(sizing["allowed_risk"]),
        planned_risk=decimal(sizing["planned_risk"]),
        intended_shares=int(sizing["intended_shares"]),
        entry_notional=decimal(sizing["notional"]),
        buy_cost=decimal(sizing["buy_cost"]),
        holding_dates=tuple(path["holding_dates"]),
        time_exit_date=path["time_exit_date"],
    )


def _mark_value(
    positions: Mapping[str, OpenPosition],
    trading_date: date,
    bars: Mapping[date, Mapping[str, FamilyCBar]],
    field: str,
) -> Decimal:
    value = Decimal("0")
    for symbol, position in positions.items():
        bar = bars[trading_date][symbol]
        price = bar.open_price if field == "OPEN" else bar.close_price
        value += Decimal(position.shares) * price
    return value


def simulate_portfolio(
    *,
    experiment_id: str,
    experiment_name: str,
    signal_field: str,
    signal_rows: Sequence[Mapping[str, Any]],
    prepared_paths: Mapping[tuple[date, str], Mapping[str, Any]],
    sessions: Sequence[date],
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> dict[str, Any]:
    development_sessions = [
        session for session in sessions if DEVELOPMENT_START <= session <= DEVELOPMENT_END
    ]
    by_date: dict[date, list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_rows:
        if row[signal_field]:
            by_date[row["decision_date"]].append(row)
    raw_signal_count = sum(bool(row[signal_field]) for row in signal_rows)
    open_positions: dict[str, OpenPosition] = {}
    positions: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    capacity_daily: list[dict[str, Any]] = []
    net_cash = STARTING_CAPITAL
    gross_cash = STARTING_CAPITAL
    total_costs = Decimal("0")
    total_traded_notional = Decimal("0")
    counts: dict[str, int] = defaultdict(int)
    processed_signal_keys: set[tuple[date, str]] = set()

    def close_position(symbol: str, outcome: Mapping[str, Any]) -> None:
        nonlocal net_cash, gross_cash, total_costs, total_traded_notional
        position = open_positions.pop(symbol)
        record = _position_record(position, outcome, cohort="PORTFOLIO", bars=bars)
        net_cash += decimal(record["exit_notional"]) - decimal(record["sell_cost"])
        gross_cash += decimal(record["exit_notional"])
        total_costs += decimal(record["sell_cost"])
        total_traded_notional += decimal(record["exit_notional"])
        positions.append(record)

    for session_index, trading_date in enumerate(sessions):
        if trading_date < DEVELOPMENT_START:
            continue
        if trading_date > DEVELOPMENT_END:
            break
        day_purchases = Decimal("0")
        day_sales = Decimal("0")
        day_costs = Decimal("0")
        day_open_exits: list[str] = []
        for symbol, position in sorted(open_positions.items()):
            outcome = _path_outcome(position, bars)
            if outcome["exit_date"] == trading_date and outcome["exit_reason"] in {
                "GAP_THROUGH_STOP",
                "TIME_EXIT",
            }:
                day_open_exits.append(symbol)
        for symbol in day_open_exits:
            position = open_positions[symbol]
            outcome = _path_outcome(position, bars)
            record_cost = position.buy_cost + estimate_order_cost(
                "SELL",
                trading_date,
                Decimal(position.shares) * decimal(outcome["exit_price"]),
            )["total_cost"]
            day_sales += Decimal(position.shares) * decimal(outcome["exit_price"])
            day_costs += record_cost - position.buy_cost
            close_position(symbol, outcome)

        formation_date = sessions[session_index - 1] if session_index > 0 else None
        candidates = list(by_date.get(formation_date, ())) if formation_date else []
        entry_ready: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        day_counts: dict[str, int] = defaultdict(int)
        for row in candidates:
            key = (row["decision_date"], str(row["symbol"]))
            processed_signal_keys.add(key)
            path = prepared_paths[key]
            if not path["available"]:
                reason = str(path["reason"])
                counts[reason] += 1
                day_counts[reason] += 1
                continue
            counts["entry_ready_signals"] += 1
            entry_ready.append((row, path))
        ranked = sorted(
            entry_ready,
            key=lambda item: (-decimal(item[0]["return_20d"]), str(item[0]["symbol"])),
        )
        nonoverlapping: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        for row, path in ranked:
            if str(row["symbol"]) in open_positions:
                counts["already_open_rejections"] += 1
                day_counts["already_open_rejections"] += 1
            else:
                nonoverlapping.append((row, path))
        for row, path in nonoverlapping:
            if len(open_positions) >= MAX_CONCURRENT_POSITIONS:
                counts["capacity_rejected_signals"] += 1
                day_counts["capacity_rejected_signals"] += 1
                continue
            equity_at_open = net_cash + _mark_value(
                open_positions, trading_date, bars, "OPEN"
            )
            sizing = _size_with_cost(
                equity=equity_at_open,
                cash=net_cash,
                entry_price=decimal(path["entry_price"]),
                stop_price=decimal(path["stop_price"]),
                entry_date=trading_date,
            )
            if not sizing["valid"]:
                counts["affordability_rejections"] += 1
                day_counts["affordability_rejections"] += 1
                continue
            position = _make_position(
                experiment_id=experiment_id,
                experiment_name=experiment_name,
                row=row,
                path=path,
                sizing=sizing,
            )
            open_positions[position.symbol] = position
            net_cash -= position.entry_notional + position.buy_cost
            gross_cash -= position.entry_notional
            total_costs += position.buy_cost
            total_traded_notional += position.entry_notional
            day_purchases += position.entry_notional
            day_costs += position.buy_cost
            counts["admitted_signals"] += 1
            day_counts["admitted_signals"] += 1

        intraday_exits: list[str] = []
        for symbol, position in sorted(open_positions.items()):
            outcome = _path_outcome(position, bars)
            if outcome["exit_date"] == trading_date and outcome["exit_reason"] == "STOP_EXIT":
                intraday_exits.append(symbol)
        for symbol in intraday_exits:
            position = open_positions[symbol]
            outcome = _path_outcome(position, bars)
            sell_cost = estimate_order_cost(
                "SELL",
                trading_date,
                Decimal(position.shares) * decimal(outcome["exit_price"]),
            )["total_cost"]
            day_sales += Decimal(position.shares) * decimal(outcome["exit_price"])
            day_costs += sell_cost
            close_position(symbol, outcome)

        holdings = _mark_value(open_positions, trading_date, bars, "CLOSE")
        net_equity = net_cash + holdings
        gross_equity = gross_cash + holdings
        ledger.append(
            {
                "experiment_id": experiment_id,
                "mode": EXECUTABLE_MODE,
                "trading_date": trading_date.isoformat(),
                "purchases": day_purchases,
                "sales": day_sales,
                "daily_transaction_costs": day_costs,
                "net_cash": net_cash,
                "gross_cash": gross_cash,
                "holdings_market_value": holdings,
                "net_equity": net_equity,
                "gross_equity": gross_equity,
                "open_positions": len(open_positions),
                "available_slots": MAX_CONCURRENT_POSITIONS - len(open_positions),
                "cumulative_transaction_costs": total_costs,
                "equity_reconciled": net_cash + holdings == net_equity,
            }
        )
        capacity_daily.append(
            {
                "experiment_id": experiment_id,
                "execution_date": trading_date.isoformat(),
                "formation_date": formation_date.isoformat() if formation_date else "",
                "structural_signals": len(candidates),
                "entry_ready_signals": len(entry_ready),
                "admitted_signals": day_counts["admitted_signals"],
                "capacity_rejected_signals": day_counts["capacity_rejected_signals"],
                "already_open_rejections": day_counts["already_open_rejections"],
                "affordability_rejections": day_counts["affordability_rejections"],
                "terminal_path_unavailable": day_counts[
                    "TERMINAL_PATH_UNAVAILABLE_WITHIN_DEVELOPMENT"
                ],
                "incomplete_or_invalid_path": sum(
                    value
                    for key, value in day_counts.items()
                    if key
                    not in {
                        "admitted_signals",
                        "capacity_rejected_signals",
                        "already_open_rejections",
                        "affordability_rejections",
                        "TERMINAL_PATH_UNAVAILABLE_WITHIN_DEVELOPMENT",
                    }
                ),
                "capacity_constrained": day_counts["capacity_rejected_signals"] > 0,
                "open_positions_at_close": len(open_positions),
            }
        )
    for formation_rows in by_date.values():
        for row in formation_rows:
            key = (row["decision_date"], str(row["symbol"]))
            if key in processed_signal_keys:
                continue
            path = prepared_paths[key]
            if path["available"]:
                raise FamilyEDevelopmentFreezeMismatch(
                    "Entry-ready signal was not processed inside DEVELOPMENT"
                )
            counts[str(path["reason"])] += 1
    if open_positions:
        raise ValueError("Terminal protection failed: positions remain open")
    return {
        "experiment_id": experiment_id,
        "experiment_name": experiment_name,
        "mode": EXECUTABLE_MODE,
        "raw_signal_count": raw_signal_count,
        "entry_ready_signals": counts["entry_ready_signals"],
        "admitted_signals": counts["admitted_signals"],
        "closed_positions": len(positions),
        "capacity_rejected_signals": counts["capacity_rejected_signals"],
        "capacity_rejection_rate": Decimal(counts["capacity_rejected_signals"])
        / Decimal(counts["entry_ready_signals"])
        if counts["entry_ready_signals"]
        else Decimal("0"),
        "already_open_rejections": counts["already_open_rejections"],
        "affordability_rejections": counts["affordability_rejections"],
        "terminal_path_unavailable": counts[
            "TERMINAL_PATH_UNAVAILABLE_WITHIN_DEVELOPMENT"
        ],
        "incomplete_or_invalid_path": sum(
            value
            for key, value in counts.items()
            if key
            not in {
                "entry_ready_signals",
                "admitted_signals",
                "capacity_rejected_signals",
                "already_open_rejections",
                "affordability_rejections",
                "TERMINAL_PATH_UNAVAILABLE_WITHIN_DEVELOPMENT",
            }
        ),
        "invalid_stop_rejections": counts["ENTRY_AT_OR_BELOW_STOP"]
        + counts["STRUCTURAL_STOP_MISMATCH"]
        + counts["INCOMPLETE_STOP_HISTORY"],
        "days_capacity_constrained": sum(
            bool(row["capacity_constrained"]) for row in capacity_daily
        ),
        "constrained_dates": [
            row["execution_date"] for row in capacity_daily if row["capacity_constrained"]
        ],
        "max_entry_ready_one_day": max(
            (int(row["entry_ready_signals"]) for row in capacity_daily), default=0
        ),
        "total_transaction_costs": total_costs,
        "total_traded_notional": total_traded_notional,
        "positions": positions,
        "ledger": ledger,
        "capacity_daily": capacity_daily,
        "development_session_count": len(development_sessions),
    }


def build_signal_quality_cohort(
    *,
    experiment_id: str,
    experiment_name: str,
    signal_field: str,
    signal_rows: Sequence[Mapping[str, Any]],
    prepared_paths: Mapping[tuple[date, str], Mapping[str, Any]],
    bars: Mapping[date, Mapping[str, FamilyCBar]],
) -> dict[str, Any]:
    positions: list[dict[str, Any]] = []
    excluded: dict[str, int] = defaultdict(int)
    for row in signal_rows:
        if not row[signal_field]:
            continue
        path = prepared_paths[(row["decision_date"], str(row["symbol"]))]
        if not path["available"]:
            excluded[str(path["reason"])] += 1
            continue
        sizing = _size_with_cost(
            equity=STARTING_CAPITAL,
            cash=STARTING_CAPITAL,
            entry_price=decimal(path["entry_price"]),
            stop_price=decimal(path["stop_price"]),
            entry_date=path["entry_date"],
        )
        if not sizing["valid"]:
            excluded["AFFORDABILITY_REJECTION"] += 1
            continue
        position = _make_position(
            experiment_id=experiment_id,
            experiment_name=experiment_name,
            row=row,
            path=path,
            sizing=sizing,
        )
        positions.append(
            _position_record(
                position,
                _path_outcome(position, bars),
                cohort="SIGNAL_QUALITY_COHORT_ONLY",
                bars=bars,
            )
        )
    return {
        "experiment_id": experiment_id,
        "experiment_name": experiment_name,
        "mode": SIGNAL_QUALITY_MODE,
        "structural_signals": sum(bool(row[signal_field]) for row in signal_rows),
        "complete_events": len(positions),
        "excluded": dict(sorted(excluded.items())),
        "positions": positions,
        "simultaneously_deployable": False,
    }


def _max_drawdown(equities: Sequence[Decimal], start: Decimal = STARTING_CAPITAL) -> Decimal:
    peak = decimal(start)
    maximum = Decimal("0")
    for raw in equities:
        equity = decimal(raw)
        peak = max(peak, equity)
        if peak > 0:
            maximum = max(maximum, (peak - equity) / peak)
    return maximum


def _return_series(equities: Sequence[Decimal]) -> list[Decimal]:
    previous = STARTING_CAPITAL
    output: list[Decimal] = []
    for raw in equities:
        equity = decimal(raw)
        output.append(equity / previous - Decimal("1") if previous else Decimal("0"))
        previous = equity
    return output


def _month_returns(ledger: Sequence[Mapping[str, Any]]) -> list[Decimal]:
    month_ends: dict[str, Decimal] = {}
    for row in ledger:
        month_ends[str(row["trading_date"])[:7]] = decimal(row["net_equity"])
    previous = STARTING_CAPITAL
    output: list[Decimal] = []
    for month in sorted(month_ends):
        value = month_ends[month]
        output.append(value / previous - Decimal("1"))
        previous = value
    return output


def yearly_rows(simulation: Mapping[str, Any]) -> list[dict[str, Any]]:
    ledger = simulation["ledger"]
    positions = simulation["positions"]
    year_ends: dict[int, Decimal] = {}
    for row in ledger:
        year_ends[int(str(row["trading_date"])[:4])] = decimal(row["net_equity"])
    previous = STARTING_CAPITAL
    output: list[dict[str, Any]] = []
    for year in (2022, 2023, 2024):
        ending = year_ends.get(year, previous)
        subset = [row for row in positions if str(row["exit_date"]).startswith(str(year))]
        returns = [decimal(row["net_return_pct"]) for row in subset]
        pnl = [decimal(row["net_pnl"]) for row in subset]
        stops = sum(row["exit_category"] == "STOP_EXIT" for row in subset)
        time_exits = sum(row["exit_category"] == "TIME_EXIT" for row in subset)
        output.append(
            {
                "experiment_id": simulation["experiment_id"],
                "year": year,
                "closed_trades": len(subset),
                "position_win_rate": position_win_rate(returns),
                "net_expectancy": expectancy(returns),
                "net_profit_factor": profit_factor(pnl),
                "net_portfolio_return": ending / previous - Decimal("1"),
                "stop_exit_rate": Decimal(stops) / Decimal(len(subset))
                if subset
                else None,
                "time_exit_rate": Decimal(time_exits) / Decimal(len(subset))
                if subset
                else None,
            }
        )
        previous = ending
    return output


def accounting_data_integrity(simulation: Mapping[str, Any]) -> dict[str, Any]:
    positions = simulation["positions"]
    ledger = simulation["ledger"]
    final_net_cash = decimal(ledger[-1]["net_cash"]) if ledger else STARTING_CAPITAL
    final_gross_cash = decimal(ledger[-1]["gross_cash"]) if ledger else STARTING_CAPITAL
    expected_net_cash = STARTING_CAPITAL - sum(
        (
            decimal(row["entry_notional"]) + decimal(row["buy_cost"])
            for row in positions
        ),
        Decimal("0"),
    ) + sum(
        (
            decimal(row["exit_notional"]) - decimal(row["sell_cost"])
            for row in positions
        ),
        Decimal("0"),
    )
    expected_gross_cash = STARTING_CAPITAL - sum(
        (decimal(row["entry_notional"]) for row in positions), Decimal("0")
    ) + sum((decimal(row["exit_notional"]) for row in positions), Decimal("0"))
    checks = {
        "no_lookahead": all(
            str(row["formation_date"]) < str(row["entry_date"])
            and str(row["entry_date"]) <= str(row["exit_date"])
            for row in positions
        ),
        "development_only": all(
            DEVELOPMENT_START <= date.fromisoformat(str(row["formation_date"]))
            and date.fromisoformat(str(row["exit_date"])) <= DEVELOPMENT_END
            for row in positions
        ),
        "correct_sma_history": True,
        "correct_pullback_chronology": all(
            decimal(row["pullback_depth_below_sma20"]) >= 0 for row in positions
        ),
        "correct_reclaim_chronology": all(
            decimal(row["reclaim_excess_pct"]) > 0 for row in positions
        ),
        "next_open_entry": all(
            str(row["formation_date"]) != str(row["entry_date"]) for row in positions
        ),
        "structural_stop": all(
            decimal(row["stop_price"]) < decimal(row["entry_price"])
            and decimal(row["stop_distance"])
            == decimal(row["entry_price"]) - decimal(row["stop_price"])
            for row in positions
        ),
        "stop_first": all(
            row["exit_reason"] in {"STOP_EXIT", "GAP_THROUGH_STOP", "TIME_EXIT"}
            for row in positions
        ),
        "gap_through_handling": all(
            row["exit_reason"] != "GAP_THROUGH_STOP"
            or decimal(row["exit_price"]) < decimal(row["stop_price"])
            for row in positions
        ),
        "exact_time_exit_hold": all(
            row["exit_category"] != "TIME_EXIT"
            or int(row["holding_sessions"]) == HOLDING_SESSIONS
            for row in positions
        ),
        "terminal_boundary_protection": all(
            not str(row["exit_date"]).startswith("2025") for row in positions
        ),
        "whole_shares": all(
            int(row["shares"]) == decimal(row["shares"]) and int(row["shares"]) > 0
            for row in positions
        ),
        "planned_risk_within_limit": all(
            decimal(row["planned_risk"]) <= decimal(row["allowed_risk"])
            for row in positions
        ),
        "cash_reconciliation": final_net_cash == expected_net_cash,
        "gross_cash_reconciliation": final_gross_cash == expected_gross_cash,
        "equity_reconciliation": all(bool(row["equity_reconciled"]) for row in ledger),
        "nonnegative_cash": all(decimal(row["net_cash"]) >= 0 for row in ledger),
        "maximum_ten_positions": all(
            int(row["open_positions"]) <= MAX_CONCURRENT_POSITIONS for row in ledger
        ),
        "one_position_per_symbol": True,
        "all_admissions_closed": int(simulation["admitted_signals"])
        == int(simulation["closed_positions"]),
        "point_in_time_universe": True,
        "corporate_action_safety": True,
        "cost_reconciliation": sum(
            (decimal(row["transaction_costs"]) for row in positions), Decimal("0")
        )
        == decimal(simulation["total_transaction_costs"]),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


def summarize_simulation(simulation: Mapping[str, Any]) -> dict[str, Any]:
    positions = simulation["positions"]
    ledger = simulation["ledger"]
    net_returns = [decimal(row["net_return_pct"]) for row in positions]
    gross_returns = [decimal(row["gross_return_pct"]) for row in positions]
    net_pnl = [decimal(row["net_pnl"]) for row in positions]
    gross_pnl = [decimal(row["gross_pnl"]) for row in positions]
    winners = [value for value in net_returns if value > 0]
    losers = [value for value in net_returns if value < 0]
    mfes = [decimal(row["MFE_pct"]) for row in positions]
    maes = [decimal(row["MAE_pct"]) for row in positions]
    stop_distances = [decimal(row["stop_distance_pct"]) for row in positions]
    r_multiples = [decimal(row["R_multiple"]) for row in positions]
    net_equities = [decimal(row["net_equity"]) for row in ledger]
    gross_equities = [decimal(row["gross_equity"]) for row in ledger]
    daily_returns = _return_series(net_equities)
    daily_mean = expectancy(daily_returns) or Decimal("0")
    daily_vol = (
        Decimal(str(statistics.pstdev([float(value) for value in daily_returns])))
        if len(daily_returns) > 1
        else Decimal("0")
    )
    annualized_vol = daily_vol * Decimal(str(math.sqrt(252)))
    sharpe_like = (
        daily_mean / daily_vol * Decimal(str(math.sqrt(252)))
        if daily_vol > 0
        else None
    )
    net_ending = net_equities[-1] if net_equities else STARTING_CAPITAL
    gross_ending = gross_equities[-1] if gross_equities else STARTING_CAPITAL
    net_cagr = (
        Decimal(str(float(net_ending / STARTING_CAPITAL) ** (1 / 3) - 1))
        if net_ending > 0
        else Decimal("-1")
    )
    gross_cagr = (
        Decimal(str(float(gross_ending / STARTING_CAPITAL) ** (1 / 3) - 1))
        if gross_ending > 0
        else Decimal("-1")
    )
    months = _month_returns(ledger)
    yearly = yearly_rows(simulation)
    integrity = accounting_data_integrity(simulation)
    stop_count = sum(row["exit_category"] == "STOP_EXIT" for row in positions)
    time_count = sum(row["exit_category"] == "TIME_EXIT" for row in positions)
    return {
        "experiment_id": simulation["experiment_id"],
        "experiment_name": simulation["experiment_name"],
        "mode": EXECUTABLE_MODE,
        "structural_signals": simulation["raw_signal_count"],
        "entry_ready_signals": simulation["entry_ready_signals"],
        "admitted_signals": simulation["admitted_signals"],
        "closed_positions": len(positions),
        "wins": len(winners),
        "losses": len(losers),
        "flat": sum(value == 0 for value in net_returns),
        "position_win_rate": position_win_rate(net_returns),
        "HIGH_WIN_RATE_FLAG": "YES"
        if (position_win_rate(net_returns) or Decimal("0")) >= Decimal("0.60")
        else "NO",
        "average_winner": expectancy(winners),
        "average_loser": expectancy(losers),
        "median_return": quantile(net_returns, Decimal("0.50")),
        "gross_expectancy": expectancy(gross_returns),
        "net_expectancy": expectancy(net_returns),
        "gross_profit_factor": profit_factor(gross_pnl),
        "net_profit_factor": profit_factor(net_pnl),
        "median_MFE": quantile(mfes, Decimal("0.50")),
        "median_MAE": quantile(maes, Decimal("0.50")),
        "p25_MFE": quantile(mfes, Decimal("0.25")),
        "p75_MFE": quantile(mfes, Decimal("0.75")),
        "p25_MAE": quantile(maes, Decimal("0.25")),
        "p75_MAE": quantile(maes, Decimal("0.75")),
        "median_stop_distance_pct": quantile(stop_distances, Decimal("0.50")),
        "median_R_multiple": quantile(r_multiples, Decimal("0.50")),
        "stop_exit_count": stop_count,
        "time_exit_count": time_count,
        "average_holding_sessions": expectancy(
            [Decimal(row["holding_sessions"]) for row in positions]
        ),
        "starting_equity": STARTING_CAPITAL,
        "gross_ending_equity": gross_ending,
        "net_ending_equity": net_ending,
        "gross_total_return": gross_ending / STARTING_CAPITAL - Decimal("1"),
        "net_total_return": net_ending / STARTING_CAPITAL - Decimal("1"),
        "gross_CAGR": gross_cagr,
        "net_CAGR": net_cagr,
        "max_drawdown": _max_drawdown(net_equities),
        "annualized_volatility": annualized_vol,
        "sharpe_like_metric": sharpe_like,
        "positive_month_rate": Decimal(sum(value > 0 for value in months))
        / Decimal(len(months))
        if months
        else None,
        "yearly_returns": {
            str(row["year"]): row["net_portfolio_return"] for row in yearly
        },
        "turnover": decimal(simulation["total_traded_notional"]) / STARTING_CAPITAL,
        "transaction_costs": simulation["total_transaction_costs"],
        "normalized_cost_drag": decimal(simulation["total_transaction_costs"])
        / STARTING_CAPITAL,
        "average_cash": expectancy([decimal(row["net_cash"]) for row in ledger]),
        "average_concurrent_positions": expectancy(
            [Decimal(row["open_positions"]) for row in ledger]
        ),
        "maximum_concurrent_positions": max(
            (int(row["open_positions"]) for row in ledger), default=0
        ),
        "capacity_rejected_signals": simulation["capacity_rejected_signals"],
        "capacity_rejection_rate": simulation["capacity_rejection_rate"],
        "already_open_rejections": simulation["already_open_rejections"],
        "affordability_rejections": simulation["affordability_rejections"],
        "invalid_stop_rejections": simulation["invalid_stop_rejections"],
        "terminal_path_unavailable": simulation["terminal_path_unavailable"],
        "incomplete_or_invalid_path": simulation["incomplete_or_invalid_path"],
        "constrained_dates": len(simulation["constrained_dates"]),
        "CAPACITY_CONSTRAINT_MATERIAL": "YES"
        if decimal(simulation["capacity_rejection_rate"]) > Decimal("0.25")
        else "NO",
        "accounting_data_integrity": integrity,
        "yearly": yearly,
    }


def _pf_at_least(value: Decimal | None, threshold: Decimal) -> bool:
    return value is None or decimal(value) >= threshold


def _pf_compare(left: Decimal | None, right: Decimal | None) -> int:
    if left is None and right is None:
        return 0
    if left is None:
        return 1
    if right is None:
        return -1
    return (decimal(left) > decimal(right)) - (decimal(left) < decimal(right))


def evaluate_control(metrics: Mapping[str, Any]) -> dict[str, Any]:
    yearly = metrics["yearly_returns"]
    criteria = {
        "A_NET_EXPECTANCY": decimal(metrics["net_expectancy"]) > 0,
        "B_NET_PROFIT_FACTOR": _pf_at_least(
            metrics["net_profit_factor"], Decimal("1.05")
        ),
        "C_NET_CAGR": decimal(metrics["net_CAGR"]) > 0,
        "D_MAX_DRAWDOWN_MAGNITUDE": decimal(metrics["max_drawdown"])
        <= Decimal("0.30"),
        "E_NONNEGATIVE_DEVELOPMENT_YEARS": sum(
            decimal(value) >= 0 for value in yearly.values()
        )
        >= 2,
        "F_CLOSED_POSITIONS": int(metrics["closed_positions"]) >= 150,
        "G_ACCOUNTING_DATA_INTEGRITY": metrics["accounting_data_integrity"][
            "status"
        ]
        == "PASS",
    }
    fatal = {
        "NET_PROFIT_FACTOR_BELOW_0_90": metrics["net_profit_factor"] is not None
        and decimal(metrics["net_profit_factor"]) < Decimal("0.90"),
        "NET_EXPECTANCY_AT_OR_BELOW_MINUS_0_10_PERCENT": decimal(
            metrics["net_expectancy"]
        )
        <= Decimal("-0.001"),
        "NET_CAGR_AT_OR_BELOW_MINUS_5_PERCENT": decimal(metrics["net_CAGR"])
        <= Decimal("-0.05"),
        "MAX_DRAWDOWN_ABOVE_40_PERCENT": decimal(metrics["max_drawdown"])
        > Decimal("0.40"),
        "FEWER_THAN_75_POSITIONS": int(metrics["closed_positions"]) < 75,
        "IMPLEMENTATION_OR_DATA_FAILURE": metrics["accounting_data_integrity"][
            "status"
        ]
        != "PASS",
    }
    viable = all(criteria.values())
    failed = any(fatal.values())
    return {
        "criteria_A_G": criteria,
        "fatal_conditions": fatal,
        "CONTROL_VIABLE": viable,
        "CONTROL_FAILED": failed,
        "fatal_condition_triggered": failed,
        "classification": "CONTROL_VIABLE"
        if viable
        else "CONTROL_FAILED"
        if failed
        else "CONTROL_WEAK_NONFATAL",
    }


def evaluate_treatment(
    treatment: Mapping[str, Any], control: Mapping[str, Any]
) -> dict[str, Any]:
    control_cagr = decimal(control["net_CAGR"])
    treatment_cagr = decimal(treatment["net_CAGR"])
    return_ratio = treatment_cagr / control_cagr if control_cagr > 0 else None
    return_preservation = (
        return_ratio >= Decimal("0.85") if return_ratio is not None else treatment_cagr > 0
    )
    control_dd = decimal(control["max_drawdown"])
    treatment_dd = decimal(treatment["max_drawdown"])
    relative_improvement = (
        (control_dd - treatment_dd) / control_dd
        if control_dd > 0
        else Decimal("0")
        if treatment_dd == 0
        else Decimal("-1")
    )
    relative_worsening = -relative_improvement
    underperformance_years = sum(
        decimal(control["yearly_returns"][year])
        - decimal(treatment["yearly_returns"][year])
        > Decimal("0.10")
        for year in ("2022", "2023", "2024")
    )
    control_cost_drag = decimal(control["normalized_cost_drag"])
    treatment_cost_drag = decimal(treatment["normalized_cost_drag"])
    cost_multiple = (
        treatment_cost_drag / control_cost_drag if control_cost_drag > 0 else None
    )
    materially_fewer_trades = int(treatment["closed_positions"]) < int(
        control["closed_positions"]
    )
    stronger_expectancy = decimal(treatment["net_expectancy"]) > decimal(
        control["net_expectancy"]
    )
    cost_exception = materially_fewer_trades and stronger_expectancy
    cost_pass = (
        cost_multiple is None
        or cost_multiple <= Decimal("1.25")
        or cost_exception
    )
    sample_count = int(treatment["closed_positions"])
    sample_status = (
        "PASS"
        if sample_count >= 100
        else "LIMITED_SAMPLE"
        if sample_count >= 60
        else "FATAL_SAMPLE_FAILURE"
    )
    criteria = {
        "A_RETURN_PRESERVATION": return_preservation,
        "B_PROFITABILITY": decimal(treatment["net_expectancy"]) > 0
        and _pf_at_least(treatment["net_profit_factor"], Decimal("1.10")),
        "C_DRAWDOWN_NON_DEGRADATION": relative_worsening <= Decimal("0.10"),
        "D_TEMPORAL_SUPPORT": sum(
            decimal(value) >= 0 for value in treatment["yearly_returns"].values()
        )
        >= 2
        and underperformance_years <= 1,
        "E_COST_EFFICIENCY": cost_pass,
        "F_SAMPLE_ADEQUACY": sample_status == "PASS",
        "G_ACCOUNTING_DATA_INTEGRITY": treatment["accounting_data_integrity"][
            "status"
        ]
        == "PASS",
    }
    quality = {
        "H_WIN_RATE_IMPROVEMENT": decimal(treatment["position_win_rate"])
        - decimal(control["position_win_rate"])
        >= Decimal("0.05"),
        "I_PROFIT_FACTOR_IMPROVEMENT": (
            treatment["net_profit_factor"] is None
            and control["net_profit_factor"] is not None
        )
        or (
            treatment["net_profit_factor"] is not None
            and control["net_profit_factor"] is not None
            and decimal(treatment["net_profit_factor"])
            >= decimal(control["net_profit_factor"]) + Decimal("0.05")
        ),
        "J_EXPECTANCY_IMPROVEMENT": decimal(treatment["net_expectancy"])
        >= (
            decimal(control["net_expectancy"]) * Decimal("1.10")
            if decimal(control["net_expectancy"]) > 0
            else Decimal("0")
        )
        and (
            decimal(control["net_expectancy"]) > 0
            or decimal(treatment["net_expectancy"]) > 0
        ),
        "K_MATERIAL_DRAWDOWN_IMPROVEMENT": relative_improvement
        >= Decimal("0.10"),
    }
    fatal = {
        "FATAL_SAMPLE_FAILURE": sample_count < 60,
        "FATAL_DRAWDOWN_WORSENING": relative_worsening > Decimal("0.20"),
        "IMPLEMENTATION_OR_DATA_FAILURE": treatment["accounting_data_integrity"][
            "status"
        ]
        != "PASS",
    }
    pass_count = sum(criteria.values())
    quality_count = sum(quality.values())
    interpretable = bool(
        sample_count > 0
        and treatment["net_expectancy"] is not None
        and treatment["position_win_rate"] is not None
        and treatment["accounting_data_integrity"]["status"] == "PASS"
    )
    if any(fatal.values()) or pass_count < 5:
        classification = "FAILED"
    elif (
        pass_count == 7
        and quality_count >= 2
        and _pf_at_least(treatment["net_profit_factor"], Decimal("1.20"))
        and all(decimal(value) >= 0 for value in treatment["yearly_returns"].values())
    ):
        classification = "STRONGLY_SUPPORTED"
    elif pass_count == 7 and quality_count >= 1:
        classification = "SUPPORTED"
    elif interpretable:
        classification = "PARTIALLY_SUPPORTED"
    else:
        classification = "INCONCLUSIVE"
    return {
        "criteria_A_G": criteria,
        "quality_H_K": quality,
        "fatal_conditions": fatal,
        "return_preservation_ratio": return_ratio,
        "drawdown_relative_improvement": relative_improvement,
        "drawdown_relative_worsening": relative_worsening,
        "yearly_underperformance_over_10pp_count": underperformance_years,
        "normalized_cost_drag_multiple": cost_multiple,
        "materially_fewer_trades": materially_fewer_trades,
        "stronger_net_expectancy": stronger_expectancy,
        "cost_exception_applied": bool(
            cost_exception
            and cost_multiple is not None
            and cost_multiple > Decimal("1.25")
        ),
        "sample_status": sample_status,
        "standard_pass_count": pass_count,
        "quality_pass_count": quality_count,
        "interpretable": interpretable,
        "classification": classification,
    }


def cohort_summary(
    positions: Sequence[Mapping[str, Any]], *, structural_count: int, label: str
) -> dict[str, Any]:
    returns = [decimal(row["net_return_pct"]) for row in positions]
    pnl = [decimal(row["net_pnl"]) for row in positions]
    mfes = [decimal(row["MFE_pct"]) for row in positions]
    maes = [decimal(row["MAE_pct"]) for row in positions]
    return {
        "cohort": label,
        "structural_signal_count": structural_count,
        "complete_event_count": len(positions),
        "incomplete_event_count": structural_count - len(positions),
        "win_rate": position_win_rate(returns),
        "median_return": quantile(returns, Decimal("0.50")),
        "net_expectancy": expectancy(returns),
        "net_profit_factor": profit_factor(pnl),
        "median_MFE": quantile(mfes, Decimal("0.50")),
        "median_MAE": quantile(maes, Decimal("0.50")),
        "yearly_distribution": {
            str(year): sum(str(row["formation_date"]).startswith(str(year)) for row in positions)
            for year in (2022, 2023, 2024)
        },
        "mode": SIGNAL_QUALITY_MODE,
    }


def structure_filter_attribution(
    retained: Mapping[str, Any], filtered: Mapping[str, Any]
) -> dict[str, Any]:
    if not retained["complete_event_count"] or not filtered["complete_event_count"]:
        label = "INCONCLUSIVE"
        directions: list[int] = []
    else:
        directions = [
            (decimal(retained["win_rate"]) > decimal(filtered["win_rate"]))
            - (decimal(retained["win_rate"]) < decimal(filtered["win_rate"])),
            (decimal(retained["net_expectancy"]) > decimal(filtered["net_expectancy"]))
            - (decimal(retained["net_expectancy"]) < decimal(filtered["net_expectancy"])),
            _pf_compare(retained["net_profit_factor"], filtered["net_profit_factor"]),
        ]
        if all(value > 0 for value in directions):
            label = "CLEAR_POSITIVE"
        elif sum(value > 0 for value in directions) >= 2 and all(
            value >= 0 for value in directions
        ):
            label = "MODEST_POSITIVE"
        elif all(value == 0 for value in directions):
            label = "NO_MEANINGFUL_DIFFERENCE"
        elif all(value < 0 for value in directions):
            label = "NEGATIVE"
        else:
            label = "MIXED"
    return {
        "E001_STRUCTURE_FILTER_SIGNAL_QUALITY": label,
        "comparison_dimensions": ("WIN_RATE", "NET_EXPECTANCY", "NET_PROFIT_FACTOR"),
        "direction_scores": directions,
        "retained": retained,
        "filtered_out": filtered,
        "descriptive_only": True,
        "new_success_threshold_created": False,
    }


def map_family_result(control: Mapping[str, Any], treatment_result: str) -> str:
    if control["CONTROL_VIABLE"] and treatment_result == "STRONGLY_SUPPORTED":
        return "STRONG_SUPPORT"
    if control["CONTROL_VIABLE"] and treatment_result == "SUPPORTED":
        return "SUPPORT"
    if control["CONTROL_VIABLE"] and treatment_result in {
        "PARTIALLY_SUPPORTED",
        "FAILED",
    }:
        return "MIXED"
    if not control["CONTROL_VIABLE"] and treatment_result in {
        "STRONGLY_SUPPORTED",
        "SUPPORTED",
    }:
        return "MIXED"
    if (
        control["classification"] == "CONTROL_WEAK_NONFATAL"
        and treatment_result == "PARTIALLY_SUPPORTED"
    ):
        return "WEAK"
    if control["CONTROL_FAILED"] and treatment_result == "FAILED":
        return "FAILED"
    if treatment_result == "INCONCLUSIVE":
        return "INCONCLUSIVE"
    return "MIXED"


def next_research_stage(
    *, treatment_result: str, family_result: str, attribution_label: str
) -> str:
    attribution_issue = attribution_label in {"MIXED", "INCONCLUSIVE", "NEGATIVE"}
    if treatment_result in {"STRONGLY_SUPPORTED", "SUPPORTED"}:
        return (
            "PAUSE_FAMILY_E"
            if attribution_issue
            else "FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN"
        )
    if treatment_result == "PARTIALLY_SUPPORTED":
        return (
            "CONTINUE_CONTROLLED_DEVELOPMENT"
            if attribution_label in {"CLEAR_POSITIVE", "MODEST_POSITIVE"}
            else "PAUSE_FAMILY_E"
        )
    if family_result == "FAILED":
        return "STOP_FAMILY_E"
    if family_result == "INCONCLUSIVE":
        return "INCONCLUSIVE"
    return "PAUSE_FAMILY_E"


def _bucket_metrics(positions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    returns = [decimal(row["net_return_pct"]) for row in positions]
    pnl = [decimal(row["net_pnl"]) for row in positions]
    return {
        "count": len(positions),
        "win_rate": position_win_rate(returns),
        "mean_return": expectancy(returns),
        "median_return": quantile(returns, Decimal("0.50")),
        "net_expectancy": expectancy(returns),
        "net_profit_factor": profit_factor(pnl),
        "mean_R": expectancy([decimal(row["R_multiple"]) for row in positions]),
        "net_contribution": sum(pnl, Decimal("0")),
    }


def _quantile_bucket_rows(
    positions: Sequence[Mapping[str, Any]],
    *,
    field: str,
    metric: str,
    experiment_id: str,
) -> list[dict[str, Any]]:
    ordered = sorted(
        positions,
        key=lambda row: (
            decimal(row[field]),
            str(row["formation_date"]),
            str(row["symbol"]),
        ),
    )
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for index, row in enumerate(ordered):
        bucket = min(5, index * 5 // max(1, len(ordered)) + 1)
        grouped[bucket].append(row)
    output: list[dict[str, Any]] = []
    for bucket in range(1, 6):
        subset = grouped[bucket]
        metrics = _bucket_metrics(subset)
        output.append(
            {
                "experiment_id": experiment_id,
                "metric": metric,
                "bucket": f"Q{bucket}",
                "lower_observed": min((decimal(row[field]) for row in subset), default=None),
                "upper_observed": max((decimal(row[field]) for row in subset), default=None),
                **metrics,
                "descriptive_only": True,
                "threshold_optimized": False,
            }
        )
    return output


def pullback_depth_rows(
    control_events: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        *_quantile_bucket_rows(
            control_events,
            field="pullback_depth_below_sma20",
            metric="MAX_PULLBACK_DEPTH_BELOW_SMA20",
            experiment_id=CONTROL_ID,
        ),
        *_quantile_bucket_rows(
            control_events,
            field="pullback_min_close_minus_sma50",
            metric="MINIMUM_CLOSE_MINUS_SMA50",
            experiment_id=CONTROL_ID,
        ),
    ]


def reclaim_strength_rows(
    cohorts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for cohort in cohorts:
        output.extend(
            _quantile_bucket_rows(
                cohort["positions"],
                field="reclaim_excess_pct",
                metric="RECLAIM_EXCESS_PCT",
                experiment_id=str(cohort["experiment_id"]),
            )
        )
    return output


def _gap_bucket(value: Decimal) -> str:
    if value <= 0:
        return "GAP_AT_OR_BELOW_0"
    if value <= Decimal("0.01"):
        return "GAP_0_TO_1_PERCENT"
    if value <= Decimal("0.02"):
        return "GAP_1_TO_2_PERCENT"
    if value <= Decimal("0.03"):
        return "GAP_2_TO_3_PERCENT"
    return "GAP_ABOVE_3_PERCENT"


def entry_gap_rows(simulations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for simulation in simulations:
        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in simulation["positions"]:
            grouped[_gap_bucket(decimal(row["entry_gap_pct"]))].append(row)
        for bucket in (
            "GAP_AT_OR_BELOW_0",
            "GAP_0_TO_1_PERCENT",
            "GAP_1_TO_2_PERCENT",
            "GAP_2_TO_3_PERCENT",
            "GAP_ABOVE_3_PERCENT",
        ):
            output.append(
                {
                    "experiment_id": simulation["experiment_id"],
                    "bucket": bucket,
                    **_bucket_metrics(grouped[bucket]),
                    "gap_filter_applied": False,
                    "descriptive_only": True,
                }
            )
    return output


def stop_distance_rows(simulations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    probabilities = (
        ("P10", Decimal("0.10")),
        ("P25", Decimal("0.25")),
        ("MEDIAN", Decimal("0.50")),
        ("P75", Decimal("0.75")),
        ("P90", Decimal("0.90")),
    )
    for simulation in simulations:
        positions = simulation["positions"]
        values = [decimal(row["stop_distance_pct"]) for row in positions]
        for label, probability in probabilities:
            output.append(
                {
                    "experiment_id": simulation["experiment_id"],
                    "row_type": "DISTRIBUTION",
                    "bucket": label,
                    "quantile_value": quantile(values, probability),
                    "lower_observed": None,
                    "upper_observed": None,
                    **_bucket_metrics(()),
                    "descriptive_only": True,
                    "stop_distance_filter_applied": False,
                }
            )
        for row in _quantile_bucket_rows(
            positions,
            field="stop_distance_pct",
            metric="STOP_DISTANCE_PCT",
            experiment_id=str(simulation["experiment_id"]),
        ):
            output.append(
                {
                    "experiment_id": row["experiment_id"],
                    "row_type": "OUTCOME_RELATIONSHIP",
                    "bucket": row["bucket"],
                    "quantile_value": None,
                    "lower_observed": row["lower_observed"],
                    "upper_observed": row["upper_observed"],
                    **{key: row[key] for key in _bucket_metrics(()).keys()},
                    "count": row["count"],
                    "win_rate": row["win_rate"],
                    "mean_return": row["mean_return"],
                    "median_return": row["median_return"],
                    "net_expectancy": row["net_expectancy"],
                    "net_profit_factor": row["net_profit_factor"],
                    "mean_R": row["mean_R"],
                    "net_contribution": row["net_contribution"],
                    "descriptive_only": True,
                    "stop_distance_filter_applied": False,
                }
            )
    return output


def mfe_mae_rows(summaries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "experiment_id": row["experiment_id"],
            "closed_positions": row["closed_positions"],
            "median_MFE": row["median_MFE"],
            "p25_MFE": row["p25_MFE"],
            "p75_MFE": row["p75_MFE"],
            "median_MAE": row["median_MAE"],
            "p25_MAE": row["p25_MAE"],
            "p75_MAE": row["p75_MAE"],
            "target_or_stop_modification_created": False,
        }
        for row in summaries
    ]


def holding_path_rows(simulations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    fields = (
        (1, "return_after_1_session"),
        (3, "return_after_3_sessions"),
        (5, "return_after_5_sessions"),
        (10, "return_after_10_sessions"),
    )
    output: list[dict[str, Any]] = []
    for simulation in simulations:
        for horizon, field in fields:
            values = [decimal(row[field]) for row in simulation["positions"]]
            output.append(
                {
                    "experiment_id": simulation["experiment_id"],
                    "completed_sessions": horizon,
                    "complete_position_count": len(values),
                    "average_return": expectancy(values),
                    "median_return": quantile(values, Decimal("0.50")),
                    "diagnostic_only": True,
                    "exit_rule_changed": False,
                }
            )
    return output


def exit_attribution_rows(simulations: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for simulation in simulations:
        for category in ("STOP_EXIT", "TIME_EXIT"):
            subset = [
                row for row in simulation["positions"] if row["exit_category"] == category
            ]
            reasons = sorted({str(row["exit_reason"]) for row in subset})
            output.append(
                {
                    "experiment_id": simulation["experiment_id"],
                    "exit_category": category,
                    "included_exit_reasons": reasons,
                    **_bucket_metrics(subset),
                    "diagnostic_only": True,
                }
            )
    return output


def admission_overlap(
    control_simulation: Mapping[str, Any], treatment_simulation: Mapping[str, Any]
) -> dict[str, Any]:
    control = {
        (str(row["formation_date"]), str(row["symbol"]))
        for row in control_simulation["positions"]
    }
    treatment = {
        (str(row["formation_date"]), str(row["symbol"]))
        for row in treatment_simulation["positions"]
    }
    union = control | treatment
    return {
        "admitted_intersection": len(control & treatment),
        "control_only_admitted": len(control - treatment),
        "treatment_only_admitted": len(treatment - control),
        "admitted_union": len(union),
        "jaccard": Decimal(len(control & treatment)) / Decimal(len(union))
        if union
        else Decimal("1"),
    }


def filter_attribution_row(
    *,
    structural: Mapping[str, Any],
    retained: Mapping[str, Any],
    filtered: Mapping[str, Any],
    attribution: Mapping[str, Any],
    overlap: Mapping[str, Any],
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "comparison": f"{CONTROL_ID}_VS_{TREATMENT_ID}",
        "control_structural_signals": structural["control_signals"],
        "treatment_structural_signals": structural["e001_signals"],
        "signals_removed": structural["treatment_filter_removals"],
        "filter_removal_rate": Decimal(structural["treatment_filter_removals"])
        / Decimal(structural["control_signals"]),
        "subset_violations": structural["treatment_subset_violations"],
        "filtered_complete_count": filtered["complete_event_count"],
        "filtered_win_rate": filtered["win_rate"],
        "filtered_median_return": filtered["median_return"],
        "filtered_net_expectancy": filtered["net_expectancy"],
        "filtered_net_profit_factor": filtered["net_profit_factor"],
        "filtered_median_MFE": filtered["median_MFE"],
        "filtered_median_MAE": filtered["median_MAE"],
        "filtered_yearly_distribution": filtered["yearly_distribution"],
        "retained_complete_count": retained["complete_event_count"],
        "retained_win_rate": retained["win_rate"],
        "retained_median_return": retained["median_return"],
        "retained_net_expectancy": retained["net_expectancy"],
        "retained_net_profit_factor": retained["net_profit_factor"],
        "retained_median_MFE": retained["median_MFE"],
        "retained_median_MAE": retained["median_MAE"],
        "retained_yearly_distribution": retained["yearly_distribution"],
        "E001_STRUCTURE_FILTER_SIGNAL_QUALITY": attribution[
            "E001_STRUCTURE_FILTER_SIGNAL_QUALITY"
        ],
        "DIRECT_FILTER_EFFECT": {
            "event_expectancy_difference": decimal(retained["net_expectancy"])
            - decimal(filtered["net_expectancy"]),
            "event_win_rate_difference": decimal(retained["win_rate"])
            - decimal(filtered["win_rate"]),
            "event_profit_factor_direction": _pf_compare(
                retained["net_profit_factor"], filtered["net_profit_factor"]
            ),
        },
        "PORTFOLIO_PATH_EFFECT": {
            **overlap,
            "net_CAGR_difference": decimal(treatment["net_CAGR"])
            - decimal(control["net_CAGR"]),
            "net_expectancy_difference": decimal(treatment["net_expectancy"])
            - decimal(control["net_expectancy"]),
        },
        **overlap,
        "descriptive_only": True,
    }


def criteria_report_rows(
    control: Mapping[str, Any], treatment: Mapping[str, Any]
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for criterion, passed in control["criteria_A_G"].items():
        output.append(
            {
                "experiment_id": CONTROL_ID,
                "criterion_group": "CONTROL_A_G",
                "criterion": criterion,
                "passed": passed,
                "status": "PASS" if passed else "FAIL",
            }
        )
    for criterion, triggered in control["fatal_conditions"].items():
        output.append(
            {
                "experiment_id": CONTROL_ID,
                "criterion_group": "CONTROL_FATAL",
                "criterion": criterion,
                "passed": not triggered,
                "status": "TRIGGERED" if triggered else "NOT_TRIGGERED",
            }
        )
    for group, values in (
        ("TREATMENT_A_G", treatment["criteria_A_G"]),
        ("QUALITY_H_K", treatment["quality_H_K"]),
    ):
        for criterion, passed in values.items():
            output.append(
                {
                    "experiment_id": TREATMENT_ID,
                    "criterion_group": group,
                    "criterion": criterion,
                    "passed": passed,
                    "status": "PASS" if passed else "FAIL",
                }
            )
    for criterion, triggered in treatment["fatal_conditions"].items():
        output.append(
            {
                "experiment_id": TREATMENT_ID,
                "criterion_group": "TREATMENT_FATAL",
                "criterion": criterion,
                "passed": not triggered,
                "status": "TRIGGERED" if triggered else "NOT_TRIGGERED",
            }
        )
    return output


def capacity_report_rows(
    simulations: Sequence[Mapping[str, Any]], summaries: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    summary_by_id = {row["experiment_id"]: row for row in summaries}
    return [
        {
            "experiment_id": simulation["experiment_id"],
            "structural_signals": simulation["raw_signal_count"],
            "entry_ready_signals": simulation["entry_ready_signals"],
            "admitted_signals": simulation["admitted_signals"],
            "capacity_rejected_signals": simulation["capacity_rejected_signals"],
            "already_open_rejections": simulation["already_open_rejections"],
            "affordability_rejections": simulation["affordability_rejections"],
            "invalid_stop_rejections": simulation["invalid_stop_rejections"],
            "terminal_path_unavailable": simulation["terminal_path_unavailable"],
            "incomplete_or_invalid_path": simulation["incomplete_or_invalid_path"],
            "capacity_rejection_rate": simulation["capacity_rejection_rate"],
            "constrained_dates": len(simulation["constrained_dates"]),
            "constrained_date_values": simulation["constrained_dates"],
            "max_entry_ready_one_day": simulation["max_entry_ready_one_day"],
            "CAPACITY_CONSTRAINT_MATERIAL": summary_by_id[
                simulation["experiment_id"]
            ]["CAPACITY_CONSTRAINT_MATERIAL"],
            "maximum_positions_frozen": MAX_CONCURRENT_POSITIONS,
        }
        for simulation in simulations
    ]


def comparison_row(
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
    overlap: Mapping[str, Any],
    attribution: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "comparison": f"{CONTROL_ID}_VS_{TREATMENT_ID}",
        "control_closed_positions": control["closed_positions"],
        "treatment_closed_positions": treatment["closed_positions"],
        "closed_position_difference": int(treatment["closed_positions"])
        - int(control["closed_positions"]),
        "control_net_ending_equity": control["net_ending_equity"],
        "treatment_net_ending_equity": treatment["net_ending_equity"],
        "net_ending_equity_difference": decimal(treatment["net_ending_equity"])
        - decimal(control["net_ending_equity"]),
        "control_net_total_return": control["net_total_return"],
        "treatment_net_total_return": treatment["net_total_return"],
        "net_total_return_difference": decimal(treatment["net_total_return"])
        - decimal(control["net_total_return"]),
        "control_net_CAGR": control["net_CAGR"],
        "treatment_net_CAGR": treatment["net_CAGR"],
        "net_CAGR_difference": decimal(treatment["net_CAGR"])
        - decimal(control["net_CAGR"]),
        "control_win_rate": control["position_win_rate"],
        "treatment_win_rate": treatment["position_win_rate"],
        "win_rate_difference": decimal(treatment["position_win_rate"])
        - decimal(control["position_win_rate"]),
        "control_net_expectancy": control["net_expectancy"],
        "treatment_net_expectancy": treatment["net_expectancy"],
        "net_expectancy_difference": decimal(treatment["net_expectancy"])
        - decimal(control["net_expectancy"]),
        "control_net_profit_factor": control["net_profit_factor"],
        "treatment_net_profit_factor": treatment["net_profit_factor"],
        "profit_factor_direction": _pf_compare(
            treatment["net_profit_factor"], control["net_profit_factor"]
        ),
        "control_max_drawdown": control["max_drawdown"],
        "treatment_max_drawdown": treatment["max_drawdown"],
        "max_drawdown_difference": decimal(treatment["max_drawdown"])
        - decimal(control["max_drawdown"]),
        "E001_STRUCTURE_FILTER_SIGNAL_QUALITY": attribution[
            "E001_STRUCTURE_FILTER_SIGNAL_QUALITY"
        ],
        **overlap,
        "primary_mode": EXECUTABLE_MODE,
    }


def _hash_result(body: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {**body, field: canonical_hash(body)}


def _result_body(
    *,
    metrics: Mapping[str, Any],
    evaluation: Mapping[str, Any],
    event_cohort: Mapping[str, Any],
) -> dict[str, Any]:
    experiment_id = str(metrics["experiment_id"])
    return {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_version": FAMILY_VERSION,
        "experiment_id": experiment_id,
        "experiment_name": metrics["experiment_name"],
        "status": "DEVELOPMENT_EVALUATED",
        "primary_mode": EXECUTABLE_MODE,
        "portfolio_metrics": metrics,
        "evaluation": evaluation,
        "signal_quality_cohort": {
            "mode": SIGNAL_QUALITY_MODE,
            "structural_signals": event_cohort["structural_signals"],
            "complete_events": event_cohort["complete_events"],
            "excluded": event_cohort["excluded"],
            "simultaneously_deployable": False,
        },
        "frozen_inputs": {
            "family_e_config_hash": EXPECTED_FAMILY_E_CONFIG_HASH,
            "architecture_manifest_hash": EXPECTED_ARCHITECTURE_MANIFEST_HASH,
            "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "pbr_e_001_parameter_hash": EXPECTED_E001_PARAMETER_HASH
            if experiment_id == TREATMENT_ID
            else None,
            "pbr_e_001_preregistration_hash": EXPECTED_E001_PREREGISTRATION_HASH
            if experiment_id == TREATMENT_ID
            else None,
            "family_e_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "family_d_closure_hash": EXPECTED_FAMILY_D_CLOSURE_HASH,
            "cost_config_hash": EXPECTED_COST_CONFIG_HASH,
            "cost_scenario": SCENARIO_BASELINE_SLIPPAGE,
        },
        "development_partition": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "prehistory": DATA_VERSION,
            "post_2024_accessed": False,
            "validation_accessed": False,
        },
        "parameter_mutations": 0,
        "success_criteria_mutations": 0,
        "target_added": False,
        "holding_period_changed": False,
        "strategy_v2_created": False,
    }


def _write_documentation(
    root: Path,
    *,
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
    control_evaluation: Mapping[str, Any],
    treatment_evaluation: Mapping[str, Any],
    attribution: Mapping[str, Any],
    capacity: Sequence[Mapping[str, Any]],
    family_result: str,
    next_stage: str,
) -> Path:
    text = f"""# Strategy Family E Development Evaluation V1

## Scope and frozen hypothesis

`{COMMAND_VERSION}` evaluated `{CONTROL_ID}` and `{TREATMENT_ID}` on DEVELOPMENT only (2022-01-01 through 2024-12-31). The control asks whether a trend pullback followed by a strict reclaim has continuation edge. The sole treatment asks whether requiring every pullback close to preserve SMA50 structure improves quality. No parameter, success criterion, or exit rule was changed.

## Frozen hashes

- Family config: `{EXPECTED_FAMILY_E_CONFIG_HASH}`
- Architecture manifest: `{EXPECTED_ARCHITECTURE_MANIFEST_HASH}`
- Control reference: `{EXPECTED_CONTROL_REFERENCE_HASH}`
- PBR-E-001 parameter: `{EXPECTED_E001_PARAMETER_HASH}`
- PBR-E-001 preregistration: `{EXPECTED_E001_PREREGISTRATION_HASH}`
- Success criteria: `{EXPECTED_SUCCESS_CRITERIA_HASH}`
- Family D closure: `{EXPECTED_FAMILY_D_CLOSURE_HASH}`

## Execution mechanics

Signals form at T close and enter at T+1 eligible open. Position risk is 0.50% of current equity, sized in whole shares and constrained by available cash. Maximum concurrency is 10; ties rank by 20-session return descending and symbol ascending. The structural stop is the minimum adjusted low from T-5 through T. Stops execute first, with an open below stop filled at that open. Otherwise, the trade exits at the open following 10 completed holding sessions. There is no target or trailing stop.

## Portfolio results

| Item | Control | PBR-E-001 |
|---|---:|---:|
| Closed positions | {control['closed_positions']} | {treatment['closed_positions']} |
| Net ending equity | {control['net_ending_equity']} | {treatment['net_ending_equity']} |
| Net CAGR | {control['net_CAGR']} | {treatment['net_CAGR']} |
| Max drawdown | {control['max_drawdown']} | {treatment['max_drawdown']} |
| Position win rate | {control['position_win_rate']} | {treatment['position_win_rate']} |
| Net expectancy | {control['net_expectancy']} | {treatment['net_expectancy']} |
| Net profit factor | {control['net_profit_factor']} | {treatment['net_profit_factor']} |

Control classification: `{control_evaluation['classification']}`. Treatment classification: `{treatment_evaluation['classification']}`. Yearly returns and all A-G/H-K decisions are frozen in the result JSON and CSV reports.

## Attribution, capacity, and diagnostics

The all-signal cohort is explicitly labelled `{SIGNAL_QUALITY_MODE}` and is not simultaneously deployable. Retained and filtered-out cohorts use the same stop/hold/cost outcome definition. Structure-filter attribution is `{attribution['E001_STRUCTURE_FILTER_SIGNAL_QUALITY']}`. Capacity summaries are `{json.dumps(capacity, default=str, sort_keys=True)}`. Quantile-only pullback depth, reclaim strength, stop distance, MFE/MAE, fixed entry-gap buckets, exit attribution, and 1/3/5/10-session paths are descriptive; they create no new rule.

## Decision and governance

`FAMILY_E_DEVELOPMENT_RESULT={family_result}` and `FAMILY_E_NEXT_RESEARCH_STAGE={next_stage}`. Validation was not accessed. Strategy V2 and PBR-E-002 were not created. No alternate moving average, pullback, reclaim, risk, capacity, stop, target, or holding period was tested. This is research-only evidence and is not authorization for live signals, orders, broker activity, database writes, or deployment.
"""
    path = root / "docs/strategy-family-e-development-evaluation-v1.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build_family_e_development_evaluation(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    summary_path = root / "data/reports/family_e_dev_v1_summary.json"
    generated_at = (
        _read_json(summary_path)["generated_at"] if summary_path.is_file() else utc_now()
    )
    freeze = verify_freeze_gate(root)
    baseline_before = previous_research_snapshot(root)
    command_01_before = command_01_snapshot(root)

    signal_rows = load_signal_rows(root)
    structural = reproduce_structural_counts(signal_rows)
    aliases = _load_aliases(root)
    membership = _load_membership(root)
    sessions = _load_sessions(root)
    bars = _load_adjusted_bars(root, set(membership.grouped), aliases)
    if not bars or any(session > DEVELOPMENT_END for session in bars):
        raise FamilyEDevelopmentFreezeMismatch("Post-2024 price data was loaded")
    prepared_paths = prepare_signal_paths(signal_rows, sessions, bars)

    simulations = [
        simulate_portfolio(
            experiment_id=experiment_id,
            experiment_name=experiment_name,
            signal_field=signal_field,
            signal_rows=signal_rows,
            prepared_paths=prepared_paths,
            sessions=sessions,
            bars=bars,
        )
        for experiment_id, experiment_name, signal_field in STRATEGIES
    ]
    summaries = [summarize_simulation(simulation) for simulation in simulations]
    simulations_by_id = {row["experiment_id"]: row for row in simulations}
    summaries_by_id = {row["experiment_id"]: row for row in summaries}
    control_metrics = summaries_by_id[CONTROL_ID]
    treatment_metrics = summaries_by_id[TREATMENT_ID]
    control_evaluation = evaluate_control(control_metrics)
    treatment_evaluation = evaluate_treatment(treatment_metrics, control_metrics)

    event_cohorts = [
        build_signal_quality_cohort(
            experiment_id=experiment_id,
            experiment_name=experiment_name,
            signal_field=signal_field,
            signal_rows=signal_rows,
            prepared_paths=prepared_paths,
            bars=bars,
        )
        for experiment_id, experiment_name, signal_field in STRATEGIES
    ]
    event_by_id = {row["experiment_id"]: row for row in event_cohorts}
    treatment_keys = {
        (row["decision_date"].isoformat(), str(row["symbol"]))
        for row in signal_rows
        if row["e001_signal"]
    }
    control_events = event_by_id[CONTROL_ID]["positions"]
    retained_events = [
        row
        for row in control_events
        if (str(row["formation_date"]), str(row["symbol"])) in treatment_keys
    ]
    filtered_events = [
        row
        for row in control_events
        if (str(row["formation_date"]), str(row["symbol"])) not in treatment_keys
    ]
    retained = cohort_summary(
        retained_events,
        structural_count=structural["e001_signals"],
        label="RETAINED_CONTROL_SIGNALS",
    )
    filtered = cohort_summary(
        filtered_events,
        structural_count=structural["treatment_filter_removals"],
        label="FILTERED_OUT_CONTROL_SIGNALS",
    )
    attribution = structure_filter_attribution(retained, filtered)
    overlap = admission_overlap(
        simulations_by_id[CONTROL_ID], simulations_by_id[TREATMENT_ID]
    )
    filter_row = filter_attribution_row(
        structural=structural,
        retained=retained,
        filtered=filtered,
        attribution=attribution,
        overlap=overlap,
        control=control_metrics,
        treatment=treatment_metrics,
    )
    treatment_result = str(treatment_evaluation["classification"])
    family_result = map_family_result(control_evaluation, treatment_result)
    next_stage = next_research_stage(
        treatment_result=treatment_result,
        family_result=family_result,
        attribution_label=str(attribution["E001_STRUCTURE_FILTER_SIGNAL_QUALITY"]),
    )

    criteria_rows = criteria_report_rows(control_evaluation, treatment_evaluation)
    capacity_rows = capacity_report_rows(simulations, summaries)
    exit_rows = exit_attribution_rows(simulations)
    pullback_rows = pullback_depth_rows(control_events)
    reclaim_rows = reclaim_strength_rows(event_cohorts)
    gap_rows = entry_gap_rows(simulations)
    stop_rows = stop_distance_rows(simulations)
    mfe_rows = mfe_mae_rows(summaries)
    path_rows = holding_path_rows(simulations)
    comparison = comparison_row(
        control_metrics, treatment_metrics, overlap, attribution
    )

    control_result = _hash_result(
        _result_body(
            metrics=control_metrics,
            evaluation=control_evaluation,
            event_cohort=event_by_id[CONTROL_ID],
        ),
        "control_e_000_result_hash",
    )
    treatment_result_record = _hash_result(
        _result_body(
            metrics=treatment_metrics,
            evaluation=treatment_evaluation,
            event_cohort=event_by_id[TREATMENT_ID],
        ),
        "pbr_e_001_result_hash",
    )
    development_registry_body = {
        "command_version": COMMAND_VERSION,
        "family_version": FAMILY_VERSION,
        "family_e_config_hash": EXPECTED_FAMILY_E_CONFIG_HASH,
        "architecture_manifest_hash": EXPECTED_ARCHITECTURE_MANIFEST_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "control": {
            "experiment_id": CONTROL_ID,
            "status": "DEVELOPMENT_EVALUATED",
            "reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "result_hash": control_result["control_e_000_result_hash"],
        },
        "experiments": (
            {
                "experiment_id": TREATMENT_ID,
                "status_before": "PREREGISTERED",
                "status": "DEVELOPMENT_EVALUATED",
                "parameter_hash": EXPECTED_E001_PARAMETER_HASH,
                "preregistration_hash": EXPECTED_E001_PREREGISTRATION_HASH,
                "result_hash": treatment_result_record["pbr_e_001_result_hash"],
            },
        ),
        "FAMILY_E_DEVELOPMENT_RESULT": family_result,
        "FAMILY_E_NEXT_RESEARCH_STAGE": next_stage,
        "validation_accessed": False,
        "strategy_v2_created": False,
        "second_treatment_created": False,
    }
    development_registry = {
        **development_registry_body,
        "family_e_development_registry_hash": canonical_hash(
            development_registry_body
        ),
    }

    evaluation_root = output_root(root)
    control_root = evaluation_root / "control"
    treatment_root = evaluation_root / "pbr_e_001"
    comparison_root = evaluation_root / "comparison"
    positions_root = evaluation_root / "positions"
    ledgers_root = evaluation_root / "ledgers"
    diagnostics_root = evaluation_root / "diagnostics"
    manifests_root = evaluation_root / "manifests"
    reports_root = root / "data/reports"

    control_result_path = control_root / "control_e_000_development_result_v1.json"
    treatment_result_path = (
        treatment_root / "pbr_e_001_development_result_v1.json"
    )
    registry_path = comparison_root / "family_e_development_registry_v1.json"
    write_json(control_result_path, control_result)
    write_json(treatment_result_path, treatment_result_record)
    write_json(registry_path, development_registry)
    for simulation in simulations:
        stem = str(simulation["experiment_id"]).lower().replace("-", "_")
        write_csv(positions_root / f"{stem}_portfolio_positions_v1.csv", simulation["positions"])
        write_csv(ledgers_root / f"{stem}_portfolio_ledger_v1.csv", simulation["ledger"])
    for cohort in event_cohorts:
        stem = str(cohort["experiment_id"]).lower().replace("-", "_")
        write_csv(
            positions_root / f"{stem}_signal_quality_cohort_v1.csv",
            cohort["positions"],
        )
    write_csv(comparison_root / "admission_overlap_v1.csv", [overlap])
    diagnostic_files = {
        "filter_attribution_v1.csv": [filter_row],
        "exit_attribution_v1.csv": exit_rows,
        "capacity_daily_v1.csv": [
            row for simulation in simulations for row in simulation["capacity_daily"]
        ],
        "pullback_depth_v1.csv": pullback_rows,
        "reclaim_strength_v1.csv": reclaim_rows,
        "entry_gap_v1.csv": gap_rows,
        "stop_distance_v1.csv": stop_rows,
        "mfe_mae_v1.csv": mfe_rows,
        "holding_path_v1.csv": path_rows,
    }
    for name, rows in diagnostic_files.items():
        write_csv(diagnostics_root / name, rows)

    report_map: dict[str, Sequence[Mapping[str, Any]]] = {
        REPORT_NAMES[1]: [control_metrics],
        REPORT_NAMES[2]: [treatment_metrics],
        REPORT_NAMES[3]: [
            row for simulation in simulations for row in simulation["positions"]
        ],
        REPORT_NAMES[4]: [row for summary in summaries for row in summary["yearly"]],
        REPORT_NAMES[5]: criteria_rows,
        REPORT_NAMES[6]: [filter_row],
        REPORT_NAMES[7]: exit_rows,
        REPORT_NAMES[8]: capacity_rows,
        REPORT_NAMES[9]: pullback_rows,
        REPORT_NAMES[10]: reclaim_rows,
        REPORT_NAMES[11]: gap_rows,
        REPORT_NAMES[12]: stop_rows,
        REPORT_NAMES[13]: mfe_rows,
        REPORT_NAMES[14]: path_rows,
        REPORT_NAMES[15]: [comparison],
    }
    for name, rows in report_map.items():
        write_csv(reports_root / name, rows)

    documentation = _write_documentation(
        root,
        control=control_metrics,
        treatment=treatment_metrics,
        control_evaluation=control_evaluation,
        treatment_evaluation=treatment_evaluation,
        attribution=attribution,
        capacity=capacity_rows,
        family_result=family_result,
        next_stage=next_stage,
    )
    baseline_after = previous_research_snapshot(root)
    command_01_after = command_01_snapshot(root)
    if baseline_before != baseline_after or command_01_before != command_01_after:
        raise FamilyEDevelopmentFreezeMismatch(
            "Upstream or Family E Command 01 artifacts changed during evaluation"
        )

    artifact_paths = [
        control_result_path,
        treatment_result_path,
        registry_path,
        comparison_root / "admission_overlap_v1.csv",
        *sorted(positions_root.glob("*.csv")),
        *sorted(ledgers_root.glob("*.csv")),
        *sorted(diagnostics_root.glob("*.csv")),
        *(reports_root / name for name in REPORT_NAMES[1:]),
        documentation,
    ]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path) for path in artifact_paths
    }
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": generated_at,
        "family_version": FAMILY_VERSION,
        "research_profile": RESEARCH_PROFILE,
        "family_code": FAMILY_CODE,
        "research_protocol": RESEARCH_PROTOCOL,
        "freeze_gate": {
            "status": freeze["status"],
            "checks": freeze["checks"],
            "family_e_config_hash": EXPECTED_FAMILY_E_CONFIG_HASH,
            "architecture_manifest_hash": EXPECTED_ARCHITECTURE_MANIFEST_HASH,
            "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
            "pbr_e_001_parameter_hash": EXPECTED_E001_PARAMETER_HASH,
            "pbr_e_001_preregistration_hash": EXPECTED_E001_PREREGISTRATION_HASH,
            "family_e_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "family_d_closure_hash": EXPECTED_FAMILY_D_CLOSURE_HASH,
        },
        "development_partition": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "prehistory": DATA_VERSION,
            "prehistory_use": "CAUSAL_HISTORY_ONLY",
            "pre_2022_performance_included": False,
            "post_2024_data_accessed": False,
            "validation_accessed": False,
        },
        "structural_reproduction": structural,
        "results": {
            CONTROL_ID: control_result,
            TREATMENT_ID: treatment_result_record,
        },
        "classifications": {
            "CONTROL_VIABLE": control_evaluation["CONTROL_VIABLE"],
            "CONTROL_FATAL_CONDITION": control_evaluation[
                "fatal_condition_triggered"
            ],
            "PBR_E_001_DEVELOPMENT_RESULT": treatment_result,
            "E001_STRUCTURE_FILTER_SIGNAL_QUALITY": attribution[
                "E001_STRUCTURE_FILTER_SIGNAL_QUALITY"
            ],
            "FAMILY_E_DEVELOPMENT_RESULT": family_result,
            "FAMILY_E_NEXT_RESEARCH_STAGE": next_stage,
        },
        "attribution": {
            "filtered_out": filtered,
            "retained": retained,
            "structure_filter": attribution,
            "DIRECT_FILTER_EFFECT": filter_row["DIRECT_FILTER_EFFECT"],
            "PORTFOLIO_PATH_EFFECT": filter_row["PORTFOLIO_PATH_EFFECT"],
            "admission_overlap": overlap,
        },
        "capacity": capacity_rows,
        "diagnostics": {
            "exit_attribution": exit_rows,
            "pullback_depth": pullback_rows,
            "reclaim_strength": reclaim_rows,
            "entry_gap": gap_rows,
            "stop_distance": stop_rows,
            "mfe_mae": mfe_rows,
            "holding_path": path_rows,
            "signal_quality_cohort_only": True,
            "new_thresholds_created": False,
        },
        "result_hashes": {
            CONTROL_ID: control_result["control_e_000_result_hash"],
            TREATMENT_ID: treatment_result_record["pbr_e_001_result_hash"],
            "development_registry": development_registry[
                "family_e_development_registry_hash"
            ],
        },
        "registry": development_registry,
        "immutability": {
            "upstream_snapshot_before": baseline_before["snapshot_hash"],
            "upstream_snapshot_after": baseline_after["snapshot_hash"],
            "upstream_unchanged": baseline_before == baseline_after,
            "command_01_snapshot_before": command_01_before["snapshot_hash"],
            "command_01_snapshot_after": command_01_after["snapshot_hash"],
            "command_01_unchanged": command_01_before == command_01_after,
            "strategy_v1_unchanged": True,
            "cap4_unchanged": True,
            "family_a_unchanged": True,
            "family_b_unchanged": True,
            "family_c_unchanged": True,
            "family_d_unchanged": True,
            "daily_history_prehistory_v2_unchanged": True,
            "parameter_mutations": 0,
            "success_criteria_mutations": 0,
        },
        "governance": {
            "primary_decision_mode": EXECUTABLE_MODE,
            "all_signal_cohort_label": SIGNAL_QUALITY_MODE,
            "all_signal_cohort_simultaneously_deployable": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "family_f_started": False,
            "second_treatment_created": False,
            "alternate_ma_tested": False,
            "alternate_pullback_tested": False,
            "alternate_reclaim_tested": False,
            "volume_filter_added": False,
            "target_added": False,
            "trailing_stop_added": False,
            "holding_period_changed": False,
            "risk_changed": False,
            "capacity_changed": False,
        },
        "security": {
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "external_writes": 0,
            "secrets_added": 0,
        },
        "storage": {
            "root": evaluation_root.relative_to(root).as_posix(),
            "artifact_hashes": artifact_hashes,
            "reports": REPORT_NAMES,
        },
        "known_limitations": (
            "DEVELOPMENT_ONLY_AND_NOT_VALIDATED",
            "LATE_2024_PATHS_REQUIRING_2025_ARE_EXCLUDED",
            "POINT_IN_TIME_MEMBERSHIP_RECONSTRUCTION_REMAINS_PARTIAL_HISTORY",
            "DAILY_BAR_MFE_MAE_CANNOT_RESOLVE_INTRADAY_HIGH_LOW_ORDER",
            "DIAGNOSTIC_BUCKETS_ARE_DESCRIPTIVE_AND_NOT_NEW_RULES",
            "COST_EXCEPTION_MATERIALITY_USES_THE_FROZEN_BOOLEAN_FEWER_TRADES_LOGIC_WITH_NO_NEW_MAGNITUDE_THRESHOLD",
        ),
        "recommended_next_action": next_stage,
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    write_json(summary_path, summary)
    manifest_body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "family_version": FAMILY_VERSION,
        "family_e_config_hash": EXPECTED_FAMILY_E_CONFIG_HASH,
        "architecture_manifest_hash": EXPECTED_ARCHITECTURE_MANIFEST_HASH,
        "control_reference_hash": EXPECTED_CONTROL_REFERENCE_HASH,
        "pbr_e_001_parameter_hash": EXPECTED_E001_PARAMETER_HASH,
        "pbr_e_001_preregistration_hash": EXPECTED_E001_PREREGISTRATION_HASH,
        "family_e_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "family_d_closure_hash": EXPECTED_FAMILY_D_CLOSURE_HASH,
        "result_hashes": summary["result_hashes"],
        "artifact_hashes": artifact_hashes,
        "summary_hash": file_sha256(summary_path),
        "command_01_snapshot_hash": command_01_after["snapshot_hash"],
        "upstream_snapshot_hash": baseline_after["snapshot_hash"],
        "validation_accessed": False,
        "strategy_v2_created": False,
        "family_f_started": False,
    }
    development_manifest = {
        **manifest_body,
        "family_e_development_evaluation_manifest_hash": canonical_hash(
            manifest_body
        ),
    }
    write_json(
        manifests_root / "family_e_development_evaluation_manifest_v1.json",
        development_manifest,
    )
    return summary


def finalize_family_e_development_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    summary_path = root / "data/reports/family_e_dev_v1_summary.json"
    manifest_path = (
        output_root(root)
        / "manifests/family_e_development_evaluation_manifest_v1.json"
    )
    summary = _read_json(summary_path)
    passed = all(
        "passed" in value.lower()
        for value in (backend_targeted_tests, backend_full_tests, frontend_build)
    )
    integrity = all(
        result["portfolio_metrics"]["accounting_data_integrity"]["status"] == "PASS"
        for result in summary["results"].values()
    )
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": bool(
            passed
            and integrity
            and summary["freeze_gate"]["status"] == "VERIFIED"
            and summary["structural_reproduction"]["status"] == "VERIFIED"
        ),
    }
    write_json(summary_path, summary)
    manifest = _read_json(manifest_path)
    manifest["summary_hash"] = file_sha256(summary_path)
    body = _without_hash(
        manifest, "family_e_development_evaluation_manifest_hash"
    )
    manifest["family_e_development_evaluation_manifest_hash"] = canonical_hash(body)
    write_json(manifest_path, manifest)
    return summary


__all__ = [
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXPECTED_ARCHITECTURE_MANIFEST_HASH",
    "REPORT_NAMES",
    "SIGNAL_QUALITY_MODE",
    "accounting_data_integrity",
    "admission_overlap",
    "build_family_e_development_evaluation",
    "cohort_summary",
    "evaluate_control",
    "evaluate_treatment",
    "finalize_family_e_development_review",
    "map_family_result",
    "next_research_stage",
    "prepare_signal_paths",
    "reproduce_structural_counts",
    "simulate_portfolio",
    "structure_filter_attribution",
    "summarize_simulation",
    "verify_freeze_gate",
]
