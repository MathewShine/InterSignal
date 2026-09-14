from __future__ import annotations

import json
import math
import statistics
import time
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from app.backtesting.costs.cost_models import canonical_hash, json_ready
from app.research.strategy.family_a_momentum import (
    decimal,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_b_development_evaluation import (
    EXPECTED_DEVELOPMENT_REGISTRY_HASH,
    EXPECTED_RESULT_HASHES,
    verify_command_01_freeze,
)
from app.research.strategy.family_b_relative_absolute_momentum import (
    CAPITAL_INR,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_FAMILY_B_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    FAMILY_VERSION,
)


COMMAND = "Step 03.02 / Command 03"
COMMAND_VERSION = "FAMILY_B_ATTRIBUTION_AUDIT_V1"
COMMAND_PROFILE = "RELATIVE_ABSOLUTE_MOMENTUM_ATTRIBUTION_V1"
REPLAY_LABEL = "ATTRIBUTION_REPLAY_NOT_STRATEGY_EXPERIMENT"
REPLAY_STATUS = "ATTRIBUTION_REPLAY_NOT_IDENTIFIABLE"
MATURE_HISTORY_COVERAGE_FRACTION = Decimal("0.90")

EXPECTED_ATTRIBUTION_AUDIT_HASH = "cdcef2b88766f501f6b7d21a2c1dd1cc93f79287f79c09d02dfef7f84142a0f1"

REPORT_NAMES = (
    "family_b_attribution_v1_summary.json",
    "family_b_attribution_v1_b001_equivalence.csv",
    "family_b_attribution_v1_b001_rebalance_diff.csv",
    "family_b_attribution_v1_b002_removals.csv",
    "family_b_attribution_v1_b002_intervals.csv",
    "family_b_attribution_v1_b002_cash.csv",
    "family_b_attribution_v1_year_attribution.csv",
    "family_b_attribution_v1_mature_history.csv",
    "family_b_attribution_v1_timeline.csv",
)

ATTRIBUTION_CATEGORIES = (
    "ABSOLUTE_FILTER_EFFECT",
    "UNIVERSE_CONSTRUCTION_DIFFERENCE",
    "SIGNAL_AVAILABILITY_DIFFERENCE",
    "MINIMUM_BREADTH_EFFECT",
    "INTEGER_SHARE_ALLOCATION_EFFECT",
    "PORTFOLIO_STATE_PATH_DEPENDENCE",
    "COST_EFFECT",
    "IMPLEMENTATION_DEFECT",
    "OTHER_EXPLAINED",
    "UNEXPLAINED",
)

REMOVAL_CATEGORIES = (
    "BELOW_SMA200",
    "SMA200_UNAVAILABLE_INSUFFICIENT_HISTORY",
    "OTHER_DATA_UNAVAILABLE",
    "INFRASTRUCTURE_FILTER",
    "OTHER",
)


class FamilyBAttributionInputMismatch(RuntimeError):
    pass


class FamilyBAttributionImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _recompute_hash(document: Mapping[str, Any], hash_field: str) -> str:
    return canonical_hash({key: value for key, value in document.items() if key != hash_field})


def _fail_input(reason: str, error: Exception | None = None) -> None:
    message = f"FAMILY_B_ATTRIBUTION_INPUT_MISMATCH: {reason}"
    if error is None:
        raise FamilyBAttributionInputMismatch(message)
    raise FamilyBAttributionInputMismatch(message) from error


def verify_frozen_inputs(root: Path) -> dict[str, Any]:
    """Verify all Command 01/02 inputs before performing attribution arithmetic."""
    try:
        command_01 = verify_command_01_freeze(root)
        evaluation_root = (
            root / "data/research/strategy_families/family_b/v1/development_evaluation"
        )
        summary = _read_json(root / "data/reports/family_b_dev_v1_summary.json")
        manifest = _read_json(evaluation_root / "comparison/run_manifest_v1.json")
        registry = _read_json(evaluation_root / "comparison/development_registry_v1.json")
        result_paths = {
            "CONTROL-B-000": evaluation_root / "control/development_result_v1.json",
            "MOM-B-001": evaluation_root / "mom_b_001/development_result_v1.json",
            "MOM-B-002": evaluation_root / "mom_b_002/development_result_v1.json",
        }
        results = {record_id: _read_json(path) for record_id, path in result_paths.items()}
    except FamilyBAttributionInputMismatch:
        raise
    except Exception as error:  # noqa: BLE001 - normalized command-level gate
        _fail_input("required frozen artifact missing or unreadable", error)

    checks: dict[str, bool] = {
        "family_version": summary.get("family_version") == FAMILY_VERSION,
        "family_config_hash": summary.get("hash_gate", {}).get("family_b_config_hash")
        == EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": summary.get("hash_gate", {}).get("success_criteria_hash")
        == EXPECTED_SUCCESS_CRITERIA_HASH,
        "command_02_version": summary.get("command_version")
        == "FAMILY_B_DEVELOPMENT_EVALUATION_V1",
        "development_only": summary.get("development_window", {}).get("start")
        == DEVELOPMENT_START.isoformat()
        and summary.get("development_window", {}).get("end") == DEVELOPMENT_END.isoformat()
        and summary.get("development_window", {}).get("latest_loaded_date")
        == DEVELOPMENT_END.isoformat(),
        "validation_not_accessed": summary.get("governance", {}).get("validation_accessed")
        is False,
        "family_result": summary.get("classifications", {}).get("FAMILY_B_DEVELOPMENT_RESULT")
        == "SUPPORT",
        "next_stage_not_executed": summary.get("classifications", {}).get(
            "FAMILY_B_NEXT_RESEARCH_STAGE"
        )
        == "FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN",
        "result_hash_mapping": summary.get("result_hashes") == EXPECTED_RESULT_HASHES
        and manifest.get("result_hashes") == EXPECTED_RESULT_HASHES,
        "development_registry_hash_mapping": summary.get("development_registry_hash")
        == EXPECTED_DEVELOPMENT_REGISTRY_HASH
        and manifest.get("development_registry_hash") == EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        "manifest_validation_not_accessed": manifest.get("validation_accessed") is False,
        "command_01_gate": command_01.get("status") == "VERIFIED",
    }
    for record_id, expected_hash in EXPECTED_RESULT_HASHES.items():
        result = results[record_id]
        checks[f"{record_id}_result_hash"] = (
            result.get("development_result_hash") == expected_hash
            and _recompute_hash(result, "development_result_hash") == expected_hash
            and result.get("validation_accessed") is False
        )
    checks["development_registry_hash"] = (
        registry.get("development_registry_hash") == EXPECTED_DEVELOPMENT_REGISTRY_HASH
        and _recompute_hash(registry, "development_registry_hash")
        == EXPECTED_DEVELOPMENT_REGISTRY_HASH
    )
    artifact_mismatches = [
        relative_path
        for relative_path, expected_hash in manifest.get("artifact_hashes", {}).items()
        if not (root / relative_path).exists()
        or file_sha256(root / relative_path) != expected_hash
    ]
    checks["command_02_artifacts"] = not artifact_mismatches
    if not all(checks.values()):
        _fail_input(str({key: value for key, value in checks.items() if not value}))

    semantic = {
        "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "result_hashes": EXPECTED_RESULT_HASHES,
        "development_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        "command_02_artifact_hashes": manifest["artifact_hashes"],
        "command_01_snapshot_hash": command_01["snapshot"]["snapshot_hash"],
        "family_a_snapshot_hash": command_01["snapshot"]["family_a_snapshot_hash"],
        "family_a_closure_hash": command_01["snapshot"]["family_a_closure_hash"],
        "development_end": DEVELOPMENT_END.isoformat(),
        "validation_accessed": False,
    }
    return {
        "status": "VERIFIED",
        "checks": checks,
        "snapshot": {**semantic, "snapshot_hash": canonical_hash(semantic)},
        "summary": summary,
        "results": results,
        "registry": registry,
    }


def _group_rows(rows: Iterable[Mapping[str, str]], key: str) -> dict[str, list[Mapping[str, str]]]:
    result: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in rows:
        result[str(row[key])].append(row)
    return dict(result)


def _control_candidates(root: Path) -> dict[str, dict[str, Any]]:
    rows = [
        row
        for row in read_csv(
            root
            / "data/research/strategy_families/family_a/v1/signals/family_a_signal_inputs_v1.csv"
        )
        if row["experiment_id"] == "MOM-A-002"
    ]
    result: dict[str, dict[str, Any]] = {}
    for formation_date, date_rows in sorted(_group_rows(rows, "decision_date").items()):
        eligible = [row for row in date_rows if row["eligible"] == "True"]
        count = math.ceil(len(eligible) * 0.10)
        candidates = sorted(
            (
                row
                for row in eligible
                if row["signal_rank"] and int(row["signal_rank"]) <= count
            ),
            key=lambda row: (int(row["signal_rank"]), row["symbol"]),
        )
        result[formation_date] = {
            "execution_date": date_rows[0]["execution_date"],
            "eligible_count": len(eligible),
            "candidate_count": count,
            "symbols": tuple(row["symbol"] for row in candidates),
        }
    return result


def _family_b_candidates(root: Path) -> dict[str, dict[str, Any]]:
    rows = read_csv(
        root / "data/research/strategy_families/family_b/v1/signals/family_b_signal_inputs_v1.csv"
    )
    calendar = {
        row["decision_date"]: row
        for row in read_csv(
            root
            / "data/research/strategy_families/family_b/v1/rebalance_calendar/family_b_rebalance_calendar_v1.csv"
        )
    }
    result: dict[str, dict[str, Any]] = {}
    for formation_date, date_rows in sorted(_group_rows(rows, "decision_date").items()):
        schedule = calendar[formation_date]
        candidate_count = int(schedule["top_decile_size"])
        candidates = sorted(
            (
                row
                for row in date_rows
                if row["relative_rank"] and int(row["relative_rank"]) <= candidate_count
            ),
            key=lambda row: (int(row["relative_rank"]), row["symbol"]),
        )
        result[formation_date] = {
            "execution_date": schedule["execution_date"],
            "eligible_count": int(schedule["eligible_universe_size"]),
            "candidate_count": candidate_count,
            "candidates": candidates,
            "candidate_symbols": tuple(row["symbol"] for row in candidates),
            "b001_symbols": tuple(row["symbol"] for row in candidates if row["B001_eligible"] == "True"),
            "b002_symbols": tuple(row["symbol"] for row in candidates if row["B002_eligible"] == "True"),
        }
    return result


def _ledger_paths(root: Path, record_directory: str) -> dict[str, Path]:
    directory = (
        root
        / "data/research/strategy_families/family_b/v1/development_evaluation"
        / record_directory
        / "executable_integer_share_500k"
    )
    return {
        name: directory / f"{name}.csv"
        for name in ("daily", "rebalances", "holdings", "periods", "position_returns")
    }


def _rows_by(rows: Sequence[Mapping[str, str]], field: str) -> dict[str, Mapping[str, str]]:
    return {str(row[field]): row for row in rows}


def _holding_maps(rows: Sequence[Mapping[str, str]]) -> dict[str, dict[str, Mapping[str, str]]]:
    result: dict[str, dict[str, Mapping[str, str]]] = defaultdict(dict)
    for row in rows:
        result[row["execution_date"]][row["symbol"]] = row
    return dict(result)


def _position_maps(
    rows: Sequence[Mapping[str, str]],
) -> dict[tuple[str, str], Mapping[str, str]]:
    return {(row["period_start"], row["symbol"]): row for row in rows}


def _weight_l1(
    first: Mapping[str, Mapping[str, str]], second: Mapping[str, Mapping[str, str]]
) -> Decimal:
    symbols = set(first) | set(second)
    return sum(
        (
            abs(
                (
                    decimal(first[symbol]["actual_weight_pct"])
                    if symbol in first
                    else Decimal("0")
                )
                - (decimal(second[symbol]["actual_weight_pct"]) if symbol in second else Decimal("0"))
            )
            for symbol in symbols
        ),
        Decimal("0"),
    )


def b001_control_equivalence(root: Path) -> dict[str, Any]:
    control_candidates = _control_candidates(root)
    family_b = _family_b_candidates(root)
    control_paths = _ledger_paths(root, "control")
    b001_paths = _ledger_paths(root, "mom_b_001")
    control_rebalances = _rows_by(read_csv(control_paths["rebalances"]), "formation_date")
    b001_rebalances = _rows_by(read_csv(b001_paths["rebalances"]), "formation_date")
    control_holdings = _holding_maps(read_csv(control_paths["holdings"]))
    b001_holdings = _holding_maps(read_csv(b001_paths["holdings"]))
    rows: list[dict[str, Any]] = []
    category_counts = {category: 0 for category in ATTRIBUTION_CATEGORIES}

    for formation_date in sorted(family_b):
        control = control_candidates[formation_date]
        treatment = family_b[formation_date]
        execution_date = treatment["execution_date"]
        control_row = control_rebalances[formation_date]
        b001_row = b001_rebalances[formation_date]
        control_set = set(control["symbols"])
        candidate_set = set(treatment["candidate_symbols"])
        b001_set = set(treatment["b001_symbols"])
        symmetric = sorted(control_set ^ b001_set)
        filter_removals = len(candidate_set - b001_set)
        control_positions = control_holdings.get(execution_date, {})
        b001_positions = b001_holdings.get(execution_date, {})
        allocation_l1 = _weight_l1(control_positions, b001_positions)
        cash_difference = decimal(b001_row["cash_residual_pct"]) - decimal(
            control_row["cash_residual_pct"]
        )
        buy_difference = decimal(b001_row["gross_buy_turnover"]) - decimal(
            control_row["gross_buy_turnover"]
        )
        sell_difference = decimal(b001_row["gross_sell_turnover"]) - decimal(
            control_row["gross_sell_turnover"]
        )
        cost_difference = decimal(b001_row["rebalance_cost"]) - decimal(
            control_row["rebalance_cost"]
        )
        status_difference = b001_row["status"] != control_row["status"]
        full_equivalent = (
            not symmetric
            and control["eligible_count"] == treatment["eligible_count"]
            and allocation_l1 == 0
            and cash_difference == 0
            and buy_difference == 0
            and sell_difference == 0
            and cost_difference == 0
            and not status_difference
        )
        minimum_breadth_event = (
            formation_date == "2022-06-30"
            and control_row["status"] == "INSUFFICIENT_UNIVERSE_RETAIN_PRIOR_PORTFOLIO"
            and b001_row["status"] == "EXECUTED"
        )
        if full_equivalent:
            allocation_category = cash_category = trade_category = cost_category = "NONE"
            cause = "NONE_EXACT_EQUIVALENCE"
        elif minimum_breadth_event:
            allocation_category = "MINIMUM_BREADTH_EFFECT"
            cash_category = "MINIMUM_BREADTH_EFFECT"
            trade_category = "MINIMUM_BREADTH_EFFECT"
            cost_category = "COST_EFFECT" if cost_difference else "NONE"
            cause = "CONTROL_MINIMUM_20_RETAINED_PRIOR_WHILE_B001_FROZEN_MINIMUM_10_EXECUTED_19"
        else:
            allocation_category = "PORTFOLIO_STATE_PATH_DEPENDENCE"
            cash_category = "INTEGER_SHARE_ALLOCATION_EFFECT" if cash_difference else "NONE"
            trade_category = "PORTFOLIO_STATE_PATH_DEPENDENCE" if buy_difference or sell_difference else "NONE"
            cost_category = "COST_EFFECT" if cost_difference else "NONE"
            cause = "DOWNSTREAM_PATH_FROM_2022_06_30_MINIMUM_BREADTH_EVENT"
        for category in (allocation_category, cash_category, trade_category, cost_category):
            if category in category_counts:
                category_counts[category] += 1
        rows.append(
            {
                "formation_date": formation_date,
                "execution_date": execution_date,
                "control_eligible_universe_count": control["eligible_count"],
                "B001_eligible_universe_count": treatment["eligible_count"],
                "control_top_decile_count": control["candidate_count"],
                "B001_top_decile_count": treatment["candidate_count"],
                "control_selected_symbols": control["symbols"],
                "B001_selected_symbols": treatment["b001_symbols"],
                "symmetric_difference_symbols": symmetric,
                "symmetric_difference_count": len(symmetric),
                "filter_removal_count": filter_removals,
                "control_status": control_row["status"],
                "B001_status": b001_row["status"],
                "control_actual_holdings": len(control_positions),
                "B001_actual_holdings": len(b001_positions),
                "allocation_difference_l1_pp": allocation_l1,
                "B001_minus_control_cash_pp": cash_difference,
                "B001_minus_control_buy_turnover_rupees": buy_difference,
                "B001_minus_control_sell_turnover_rupees": sell_difference,
                "B001_minus_control_rebalance_cost_rupees": cost_difference,
                "allocation_attribution": allocation_category,
                "cash_attribution": cash_category,
                "trade_attribution": trade_category,
                "cost_attribution": cost_category,
                "primary_cause": cause,
                "selected_set_equivalent": not symmetric,
                "full_mechanical_equivalence": full_equivalent,
            }
        )

    candidate_count = sum(row["B001_top_decile_count"] for row in rows)
    removed_count = sum(row["filter_removal_count"] for row in rows)
    selected_set_equivalent = [row["formation_date"] for row in rows if row["selected_set_equivalent"]]
    exact = [row["formation_date"] for row in rows if row["full_mechanical_equivalence"]]
    non_equivalent = [row["formation_date"] for row in rows if not row["full_mechanical_equivalence"]]
    unexplained = [
        row["formation_date"]
        for row in rows
        if "UNEXPLAINED"
        in {
            row["allocation_attribution"],
            row["cash_attribution"],
            row["trade_attribution"],
            row["cost_attribution"],
        }
    ]
    if candidate_count != 302 or removed_count != 0 or len(selected_set_equivalent) != 11:
        _fail_input("B001 zero-removal/selected-set reproduction failed")
    return {
        "rows": rows,
        "summary": {
            "candidate_count": candidate_count,
            "filter_removed_count": removed_count,
            "rebalance_dates_compared": len(rows),
            "selected_set_equivalent_dates": selected_set_equivalent,
            "exact_mechanical_equivalent_dates": exact,
            "non_equivalent_dates": non_equivalent,
            "causes_of_non_equivalence": (
                "MINIMUM_BREADTH_EFFECT_AT_2022_06_30",
                "DOWNSTREAM_PORTFOLIO_STATE_PATH_DEPENDENCE",
                "INTEGER_SHARE_ALLOCATION_EFFECT",
                "COST_EFFECT",
            ),
            "attribution_category_counts": category_counts,
            "unexplained_differences": unexplained,
            "B001_CONTROL_EQUIVALENCE_RESULT": "EXPLAINED_NON_EQUIVALENCE",
            "B001_DISTINCT_FILTER_EVIDENCE": "NONE",
            "interpretation": (
                "B001 and control have the same reconstructed pre-allocation top-decile set "
                "on all 11 dates. Their path diverges because the control's frozen Family A "
                "minimum of 20 retained its prior portfolio on 2022-06-30 while B001's frozen "
                "minimum of 10 allowed 19 holdings. Zero performance difference is attributed "
                "to the absolute filter itself."
            ),
        },
    }


def _removal_category(row: Mapping[str, str]) -> str:
    if row["above_sma200"] == "False" and row["sma200"]:
        return "BELOW_SMA200"
    flags = set(json.loads(row["data_quality_flags"] or "[]"))
    if "SMA200_UNAVAILABLE" in flags and not row["sma200"]:
        return "SMA200_UNAVAILABLE_INSUFFICIENT_HISTORY"
    if not row["close"] or not row["6m_return"]:
        return "OTHER_DATA_UNAVAILABLE"
    if any(flag.startswith("INFRASTRUCTURE") for flag in flags):
        return "INFRASTRUCTURE_FILTER"
    return "OTHER"


def _net_max_drawdown(rows: Sequence[Mapping[str, str]], starting_equity: Decimal) -> Decimal:
    peak = starting_equity
    maximum = Decimal("0")
    for row in rows:
        equity = decimal(row["net_equity"])
        peak = max(peak, equity)
        if peak:
            maximum = min(maximum, (equity / peak - Decimal("1")) * Decimal("100"))
    return maximum


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def b002_attribution(root: Path, frozen: Mapping[str, Any]) -> dict[str, Any]:
    control_candidates = _control_candidates(root)
    family_b = _family_b_candidates(root)
    control_paths = _ledger_paths(root, "control")
    b002_paths = _ledger_paths(root, "mom_b_002")
    control_rebalances = _rows_by(read_csv(control_paths["rebalances"]), "formation_date")
    b002_rebalances = _rows_by(read_csv(b002_paths["rebalances"]), "formation_date")
    control_holdings = _holding_maps(read_csv(control_paths["holdings"]))
    b002_holdings = _holding_maps(read_csv(b002_paths["holdings"]))
    control_positions = _position_maps(read_csv(control_paths["position_returns"]))
    control_periods = _rows_by(read_csv(control_paths["periods"]), "period_start")
    b002_periods = _rows_by(read_csv(b002_paths["periods"]), "period_start")

    removal_rows: list[dict[str, Any]] = []
    date_rows: list[dict[str, Any]] = []
    removal_counts = {category: 0 for category in REMOVAL_CATEGORIES}
    for formation_date, treatment in sorted(family_b.items()):
        execution_date = treatment["execution_date"]
        rejected = [row for row in treatment["candidates"] if row["B002_eligible"] != "True"]
        categories = [_removal_category(row) for row in rejected]
        for category in categories:
            removal_counts[category] += 1
        for candidate, category in zip(rejected, categories, strict=True):
            symbol = candidate["symbol"]
            control_holding = control_holdings.get(execution_date, {}).get(symbol)
            position = control_positions.get((execution_date, symbol))
            actual_contribution = Decimal("0")
            if control_holding is not None and position is not None:
                actual_contribution = decimal(control_holding["quantity"]) * (
                    decimal(position["end_price"]) - decimal(position["start_price"])
                )
            removal_rows.append(
                {
                    "formation_date": formation_date,
                    "execution_date": execution_date,
                    "symbol": symbol,
                    "relative_rank": int(candidate["relative_rank"]),
                    "close": candidate["close"],
                    "sma200": candidate["sma200"],
                    "removal_category": category,
                    "otherwise_in_control_preallocation_candidates": symbol
                    in set(control_candidates[formation_date]["symbols"]),
                    "actually_held_by_control": control_holding is not None,
                    "control_reference_market_value_rupees": decimal(
                        control_holding["market_value"]
                    )
                    if control_holding is not None
                    else Decimal("0"),
                    "control_position_period_return_pct": decimal(position["position_return_pct"])
                    if position is not None
                    else None,
                    "control_realized_contribution_rupees": actual_contribution,
                    "changed_B002_weights": True,
                    "isolated_causal_effect_identifiable": False,
                }
            )
        control_row = control_rebalances[formation_date]
        b002_row = b002_rebalances[formation_date]
        below_count = categories.count("BELOW_SMA200")
        unavailable_count = categories.count("SMA200_UNAVAILABLE_INSUFFICIENT_HISTORY")
        other_count = len(categories) - below_count - unavailable_count
        date_rows.append(
            {
                "formation_date": formation_date,
                "execution_date": execution_date,
                "control_candidate_count": control_candidates[formation_date]["candidate_count"],
                "B002_candidate_count": treatment["candidate_count"],
                "below_sma_removals": below_count,
                "SMA_unavailable_removals": unavailable_count,
                "other_removals": other_count,
                "qualifying_holdings": len(treatment["b002_symbols"]),
                "insufficient_breadth": b002_row["status"]
                == "INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH_CASH",
                "control_actual_holdings": int(control_row["actual_holdings"]),
                "B002_actual_holdings": int(b002_row["actual_holdings"]),
                "control_invested_pct": Decimal("100") - decimal(control_row["cash_residual_pct"]),
                "B002_invested_pct": Decimal("100") - decimal(b002_row["cash_residual_pct"]),
                "control_cash_pct": decimal(control_row["cash_residual_pct"]),
                "B002_cash_pct": decimal(b002_row["cash_residual_pct"]),
                "SMA_history_coverage_pct": (
                    Decimal(treatment["candidate_count"] - unavailable_count)
                    / Decimal(treatment["candidate_count"])
                    * Decimal("100")
                ),
            }
        )

    if (
        sum(row["B002_candidate_count"] for row in date_rows) != 302
        or removal_counts["BELOW_SMA200"] != 1
        or removal_counts["SMA200_UNAVAILABLE_INSUFFICIENT_HISTORY"] != 30
        or sum(removal_counts.values()) != 31
    ):
        _fail_input("B002 removal decomposition did not reproduce 302/1/30/31")

    interval_rows: list[dict[str, Any]] = []
    cumulative = Decimal("0")
    for formation_date in sorted(family_b):
        execution_date = family_b[formation_date]["execution_date"]
        control_period = control_periods[execution_date]
        b002_period = b002_periods[execution_date]
        control_rebalance = control_rebalances[formation_date]
        b002_rebalance = b002_rebalances[formation_date]
        contribution = (
            decimal(b002_period["net_period_pnl"])
            - decimal(control_period["net_period_pnl"])
            - (
                decimal(b002_rebalance["rebalance_cost"])
                - decimal(control_rebalance["rebalance_cost"])
            )
        )
        cumulative += contribution
        interval_rows.append(
            {
                "formation_date": formation_date,
                "period_start": execution_date,
                "period_end": control_period["period_end"],
                "control_starting_net_equity": decimal(
                    control_rebalance["post_rebalance_net_equity"]
                ),
                "B002_starting_net_equity": decimal(
                    b002_rebalance["post_rebalance_net_equity"]
                ),
                "control_return_pct": decimal(control_period["net_period_return_pct"]),
                "B002_return_pct": decimal(b002_period["net_period_return_pct"]),
                "return_difference_pp": decimal(b002_period["net_period_return_pct"])
                - decimal(control_period["net_period_return_pct"]),
                "control_period_pnl_rupees": decimal(control_period["net_period_pnl"]),
                "B002_period_pnl_rupees": decimal(b002_period["net_period_pnl"]),
                "control_rebalance_cost_rupees": decimal(control_rebalance["rebalance_cost"]),
                "B002_rebalance_cost_rupees": decimal(b002_rebalance["rebalance_cost"]),
                "difference_contribution_rupees": contribution,
                "cumulative_difference_contribution_rupees": cumulative,
            }
        )
    observed_final_gap = decimal(
        frozen["results"]["MOM-B-002"]["performance"]["net_ending_equity"]
    ) - decimal(frozen["results"]["CONTROL-B-000"]["performance"]["net_ending_equity"])
    if abs(cumulative - observed_final_gap) > Decimal("0.0001"):
        _fail_input(f"interval attribution failed to reconcile: {cumulative} != {observed_final_gap}")
    for row in interval_rows:
        row["share_of_final_difference_pct"] = (
            row["difference_contribution_rupees"] / observed_final_gap * Decimal("100")
        )
    top_contributors = sorted(
        interval_rows,
        key=lambda row: abs(decimal(row["difference_contribution_rupees"])),
        reverse=True,
    )[:3]

    yearly_control = {
        int(row["year"]): decimal(row["net_return_pct"])
        for row in frozen["results"]["CONTROL-B-000"]["yearly"]
    }
    yearly_b002 = {
        int(row["year"]): decimal(row["net_return_pct"])
        for row in frozen["results"]["MOM-B-002"]["yearly"]
    }
    years = (2022, 2023, 2024)
    year_rows: list[dict[str, Any]] = []
    for index, year in enumerate(years):
        earlier_control = math.prod(
            Decimal("1") + yearly_control[earlier] / Decimal("100")
            for earlier in years[:index]
        )
        later_b002 = math.prod(
            Decimal("1") + yearly_b002[later] / Decimal("100")
            for later in years[index + 1 :]
        )
        origin_contribution = (
            CAPITAL_INR
            * earlier_control
            * ((yearly_b002[year] - yearly_control[year]) / Decimal("100"))
            * later_b002
        )
        year_rows.append(
            {
                "year": year,
                "control_return_pct": yearly_control[year],
                "B002_return_pct": yearly_b002[year],
                "relative_advantage_pp": yearly_b002[year] - yearly_control[year],
                "origin_carried_forward_contribution_rupees": origin_contribution,
            }
        )
    origin_total = sum(
        (decimal(row["origin_carried_forward_contribution_rupees"]) for row in year_rows),
        Decimal("0"),
    )
    for row in year_rows:
        row["share_of_overall_relative_advantage_pct"] = (
            decimal(row["origin_carried_forward_contribution_rupees"])
            / origin_total
            * Decimal("100")
        )

    first_date = date_rows[0]
    first_interval = interval_rows[0]
    first_control_holdings = tuple(control_candidates["2022-03-31"]["symbols"])
    first_schedule = {
        "formation_date": "2022-03-31",
        "execution_date": first_date["execution_date"],
        "control_selected_holdings": first_control_holdings,
        "control_holding_count": len(first_control_holdings),
        "B002_available_SMA_count": first_date["B002_candidate_count"]
        - first_date["SMA_unavailable_removals"],
        "B002_unavailable_count": first_date["SMA_unavailable_removals"],
        "B002_qualifying_count": first_date["qualifying_holdings"],
        "B002_formed_portfolio": not first_date["insufficient_breadth"],
        "B002_cash_allocation_pct": first_date["B002_cash_pct"],
        "control_invested_pct": first_date["control_invested_pct"],
        "B002_invested_pct": first_date["B002_invested_pct"],
        "control_subsequent_period_return_pct": first_interval["control_return_pct"],
        "B002_subsequent_period_return_pct": first_interval["B002_return_pct"],
        "difference_contribution_rupees": first_interval["difference_contribution_rupees"],
        "difference_contribution_initial_capital_pp": first_interval[
            "difference_contribution_rupees"
        ]
        / CAPITAL_INR
        * Decimal("100"),
        "share_of_final_equity_gap_pct": first_interval["share_of_final_difference_pct"],
    }

    mature_index = next(
        index
        for index, row in enumerate(date_rows)
        if row["SMA_history_coverage_pct"]
        >= MATURE_HISTORY_COVERAGE_FRACTION * Decimal("100")
        and not row["insufficient_breadth"]
        and all(
            later["SMA_history_coverage_pct"]
            >= MATURE_HISTORY_COVERAGE_FRACTION * Decimal("100")
            for later in date_rows[index:]
        )
    )
    mature_date_row = date_rows[mature_index]
    mature_formation = mature_date_row["formation_date"]
    mature_execution = mature_date_row["execution_date"]
    control_daily = read_csv(control_paths["daily"])
    b002_daily = read_csv(b002_paths["daily"])
    control_daily_by_date = _rows_by(control_daily, "date")
    b002_daily_by_date = _rows_by(b002_daily, "date")
    control_mature_rows = [row for row in control_daily if row["date"] >= mature_execution]
    b002_mature_rows = [row for row in b002_daily if row["date"] >= mature_execution]
    control_mature_start = decimal(
        control_rebalances[mature_formation]["post_rebalance_net_equity"]
    )
    b002_mature_start = decimal(b002_rebalances[mature_formation]["post_rebalance_net_equity"])
    control_mature_return = (
        decimal(control_daily[-1]["net_equity"]) / control_mature_start - Decimal("1")
    ) * Decimal("100")
    b002_mature_return = (
        decimal(b002_daily[-1]["net_equity"]) / b002_mature_start - Decimal("1")
    ) * Decimal("100")
    mature_overlaps: list[Decimal] = []
    for row in date_rows[mature_index:]:
        control_symbols = set(control_holdings.get(row["execution_date"], {}))
        b002_symbols = set(b002_holdings.get(row["execution_date"], {}))
        union = control_symbols | b002_symbols
        mature_overlaps.append(
            Decimal(len(control_symbols & b002_symbols)) / Decimal(len(union)) * Decimal("100")
            if union
            else Decimal("100")
        )
    mature = {
        "definition": (
            "FIRST_FORMATION_WITH_AT_LEAST_90_PERCENT_TOP_DECILE_SMA200_COVERAGE_"
            "AND_SUFFICIENT_BREADTH_WITH_COVERAGE_REMAINING_AT_LEAST_90_PERCENT"
        ),
        "diagnostic_only": True,
        "formation_date": mature_formation,
        "execution_date": mature_execution,
        "SMA_history_coverage_pct": mature_date_row["SMA_history_coverage_pct"],
        "control_normalized_return_pct": control_mature_return,
        "B002_normalized_return_pct": b002_mature_return,
        "B002_minus_control_pp": b002_mature_return - control_mature_return,
        "control_max_drawdown_pct": _net_max_drawdown(
            control_mature_rows, control_mature_start
        ),
        "B002_max_drawdown_pct": _net_max_drawdown(b002_mature_rows, b002_mature_start),
        "average_holdings_jaccard_pct": _mean(mature_overlaps),
        "rebalance_count": len(mature_overlaps),
    }
    control_2023_2024 = (
        (Decimal("1") + yearly_control[2023] / Decimal("100"))
        * (Decimal("1") + yearly_control[2024] / Decimal("100"))
        - Decimal("1")
    ) * Decimal("100")
    b002_2023_2024 = (
        (Decimal("1") + yearly_b002[2023] / Decimal("100"))
        * (Decimal("1") + yearly_b002[2024] / Decimal("100"))
        - Decimal("1")
    ) * Decimal("100")

    true_filter = next(
        row for row in removal_rows if row["removal_category"] == "BELOW_SMA200"
    )
    true_filter_effect = {
        **true_filter,
        "control_realized_contribution_if_held_rupees": true_filter[
            "control_realized_contribution_rupees"
        ],
        "whether_exclusion_changed_portfolio_weights": True,
        "downstream_portfolio_state_impact": "NOT_SEPARATELY_IDENTIFIABLE_WITHOUT_NEW_COUNTERFACTUAL_RULE",
        "statistical_claim_allowed": False,
    }
    unavailable = [
        row
        for row in removal_rows
        if row["removal_category"] == "SMA200_UNAVAILABLE_INSUFFICIENT_HISTORY"
    ]
    first_control_invested_rupees = decimal(
        control_rebalances["2022-03-31"]["post_rebalance_gross_equity"]
    ) - decimal(control_rebalances["2022-03-31"]["cash"])
    missing_history = {
        "candidate_count": len(unavailable),
        "dates": tuple(sorted({row["formation_date"] for row in unavailable})),
        "otherwise_in_control_count": sum(
            bool(row["otherwise_in_control_preallocation_candidates"]) for row in unavailable
        ),
        "actually_held_by_control_count": sum(bool(row["actually_held_by_control"]) for row in unavailable),
        "first_schedule_B002_cash_rupees": decimal(b002_rebalances["2022-03-31"]["cash"]),
        "first_schedule_control_invested_rupees": first_control_invested_rupees,
        "first_schedule_incremental_uninvested_vs_control_rupees": first_control_invested_rupees,
        "first_interval_return_avoided_pp": -decimal(first_interval["control_return_pct"]),
        "first_interval_direct_difference_contribution_rupees": first_interval[
            "difference_contribution_rupees"
        ],
        "later_unavailable_candidate_count": len(unavailable) - 23,
        "later_unavailable_names_caused_insufficient_breadth": False,
        "later_unavailable_names_were_redistributed_not_held_as_structural_cash": True,
        "sum_control_reference_position_contributions_rupees": sum(
            (decimal(row["control_realized_contribution_rupees"]) for row in unavailable),
            Decimal("0"),
        ),
        "causal_effect_after_first_interval_identifiable": False,
    }
    year_2022 = next(row for row in year_rows if row["year"] == 2022)
    cash_effect = {
        "B002_CASH_EFFECT_MATERIALITY": "DOMINANT",
        "insufficient_breadth_cash_event_count": sum(
            bool(row["insufficient_breadth"]) for row in date_rows
        ),
        "first_interval_direct_contribution_rupees": first_interval[
            "difference_contribution_rupees"
        ],
        "first_interval_share_of_final_equity_gap_pct": first_interval[
            "share_of_final_difference_pct"
        ],
        "2022_origin_carried_forward_contribution_rupees": year_2022[
            "origin_carried_forward_contribution_rupees"
        ],
        "2022_share_of_overall_relative_advantage_pct": year_2022[
            "share_of_overall_relative_advantage_pct"
        ],
        "true_filter_actual_control_contribution_rupees": true_filter[
            "control_realized_contribution_rupees"
        ],
        "interpretation": (
            "The only insufficient-breadth/cash interval was caused by 23 unavailable SMA200 "
            "observations. Its carried-forward 2022 effect dominates the final relative "
            "advantage; the single genuine below-SMA event is not separately identifiable."
        ),
    }
    timeline_rows: list[dict[str, Any]] = []
    annotations: dict[str, list[str]] = defaultdict(list)
    annotations["2022-04-01"].extend(
        ("CONTROL_FIRST_EXECUTABLE_PORTFOLIO", "B001_FIRST_EXECUTABLE_PORTFOLIO")
    )
    annotations["2022-07-01"].append("B002_FIRST_EXECUTABLE_PORTFOLIO")
    for row in date_rows:
        if row["SMA_unavailable_removals"]:
            annotations[row["formation_date"]].append(
                f"SMA_UNAVAILABLE_CANDIDATES_{row['SMA_unavailable_removals']}"
            )
        if row["below_sma_removals"]:
            annotations[row["formation_date"]].append("TRUE_BELOW_SMA200_REMOVAL_AUBANK")
        if row["insufficient_breadth"]:
            annotations[row["formation_date"]].append("B002_INSUFFICIENT_BREADTH")
    annotations[mature_formation].append("BROAD_SMA_HISTORY_MATURITY_DIAGNOSTIC_START")
    b001_daily = read_csv(_ledger_paths(root, "mom_b_001")["daily"])
    b001_daily_by_date = _rows_by(b001_daily, "date")
    for row in control_daily:
        observed_date = row["date"]
        timeline_rows.append(
            {
                "date": observed_date,
                "CONTROL_normalized_net_equity": decimal(row["net_equity"])
                / CAPITAL_INR
                * Decimal("100"),
                "B001_normalized_net_equity": decimal(
                    b001_daily_by_date[observed_date]["net_equity"]
                )
                / CAPITAL_INR
                * Decimal("100"),
                "B002_normalized_net_equity": decimal(
                    b002_daily_by_date[observed_date]["net_equity"]
                )
                / CAPITAL_INR
                * Decimal("100"),
                "annotations": tuple(annotations.get(observed_date, ())),
                "new_strategy_curve": False,
            }
        )

    return {
        "removal_rows": removal_rows,
        "date_rows": date_rows,
        "interval_rows": interval_rows,
        "year_rows": year_rows,
        "timeline_rows": timeline_rows,
        "summary": {
            "candidate_count": sum(row["B002_candidate_count"] for row in date_rows),
            "removal_counts": removal_counts,
            "total_removed": sum(removal_counts.values()),
            "first_schedule": first_schedule,
            "top_interval_contributors": top_contributors,
            "observed_final_equity_gap_rupees": observed_final_gap,
            "year_attribution_reconciled_rupees": origin_total,
            "2022_share_of_overall_relative_advantage_pct": year_2022[
                "share_of_overall_relative_advantage_pct"
            ],
            "true_filter_effect": true_filter_effect,
            "missing_history_effect": missing_history,
            "cash_effect": cash_effect,
            "mature_history": mature,
            "control_2023_2024_return_pct": control_2023_2024,
            "B002_2023_2024_return_pct": b002_2023_2024,
            "B002_2023_2024_difference_pp": b002_2023_2024 - control_2023_2024,
            "attribution_replay": {
                "label": REPLAY_LABEL,
                "status": REPLAY_STATUS,
                "reason": (
                    "UNKNOWN does not specify a portfolio action. Passing, rejecting, or "
                    "redistributing unavailable observations would introduce a new trading rule."
                ),
                "imputed_SMA_used": False,
                "new_curve_generated": False,
            },
            "B002_TREND_FILTER_EVIDENCE": "CONFOUNDED_BY_HISTORY_AVAILABILITY",
            "B002_DEVELOPMENT_ADVANTAGE_ATTRIBUTION": "PRIMARILY_HISTORY_AVAILABILITY",
        },
    }


def _immutable_result(path: Path, body: Mapping[str, Any]) -> dict[str, Any]:
    result_hash = canonical_hash(body)
    document = {**body, "family_b_attribution_audit_hash": result_hash}
    if EXPECTED_ATTRIBUTION_AUDIT_HASH and result_hash != EXPECTED_ATTRIBUTION_AUDIT_HASH:
        raise FamilyBAttributionImmutabilityError(
            f"FAMILY_B_ATTRIBUTION_AUDIT_HASH_MISMATCH: {result_hash}"
        )
    if path.exists():
        existing = _read_json(path)
        if existing != json_ready(document):
            raise FamilyBAttributionImmutabilityError(
                "Existing Family B attribution result differs from frozen result"
            )
    else:
        write_json(path, document)
    return document


def build_family_b_attribution_audit(root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = utc_now()
    frozen_before = verify_frozen_inputs(root)
    b001 = b001_control_equivalence(root)
    b002 = b002_attribution(root, frozen_before)

    decisions = {
        "FAMILY_B_VALIDATION_DESIGN_READINESS": "NO_CANDIDATE_READY",
        "B001_ready_for_validation_design": False,
        "B002_ready_for_validation_design": False,
        "rationale": (
            "B001 produced no distinct filter evidence. B002's apparent advantage is primarily "
            "an early-history availability/cash artifact, while its single true filter event is "
            "not separately identifiable."
        ),
    }
    answers = {
        "Q1": b001["summary"]["interpretation"],
        "Q2": (
            "B002 rejected 31 candidates: one genuine close<=SMA200 observation and 30 "
            "SMA-unavailable observations. The one true event had no actual control holding "
            "contribution; the first 23 unavailable observations forced an all-cash interval."
        ),
        "Q3": (
            "The difference is a mixture of frozen implementation mechanics and data-history "
            "effects, dominated by history availability and its cash/path consequences; distinct "
            "trend-filter value is not demonstrated."
        ),
    }
    governance = {
        "diagnostic_only": True,
        "attribution_replay_label": REPLAY_LABEL,
        "new_strategy_created": False,
        "parameters_changed": False,
        "B003_created": False,
        "alternate_MA_tested": False,
        "alternate_threshold_tested": False,
        "missing_SMA_behavior_changed": False,
        "imputed_SMA_used": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
        "family_c_started": False,
        "live_signals_generated": 0,
        "live_orders_placed": 0,
        "broker_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
        "network_writes": 0,
        "database_writes": 0,
        "secrets_written": 0,
    }
    result_body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_version": FAMILY_VERSION,
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "development_only": True,
        },
        "frozen_inputs": {
            "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
            "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "result_hashes": EXPECTED_RESULT_HASHES,
            "development_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
            "snapshot_hash": frozen_before["snapshot"]["snapshot_hash"],
        },
        "primary_questions": answers,
        "B001": b001["summary"],
        "B002": b002["summary"],
        "decision": decisions,
        "governance": governance,
        "known_limitations": (
            "B001_FILTER_REMOVED_ZERO_CANDIDATES",
            "CONTROL_AND_B001_HAVE_DIFFERENT_FROZEN_MINIMUM_BREADTH_RULES",
            "B002_TRUE_FILTER_EVENT_COUNT_IS_ONE_AND_NOT_SIGNIFICANCE_EVIDENCE",
            "B002_HISTORY_NEUTRAL_REPLAY_IS_NOT_IDENTIFIABLE_WITHOUT_A_NEW_RULE",
            "POINT_IN_TIME_MEMBERSHIP_HISTORY_REMAINS_PARTIAL",
            "LATER_NEW_LISTINGS_CAN_STILL_LACK_200_SESSIONS_AFTER_BROAD_HISTORY_MATURITY",
        ),
    }

    output_root = root / "data/research/strategy_families/family_b/v1/attribution_audit"
    directories = {
        "b001": output_root / "b001_equivalence",
        "b002": output_root / "b002_attribution",
        "timeline": output_root / "timeline",
        "manifests": output_root / "manifests",
    }
    reports_root = root / "data/reports"
    result_path = directories["manifests"] / "family_b_attribution_audit_result_v1.json"
    immutable_result = _immutable_result(result_path, result_body)

    b001_summary_rows = [
        {
            **b001["summary"],
            "selected_set_equivalent_date_count": len(
                b001["summary"]["selected_set_equivalent_dates"]
            ),
            "exact_mechanical_equivalent_date_count": len(
                b001["summary"]["exact_mechanical_equivalent_dates"]
            ),
            "non_equivalent_date_count": len(b001["summary"]["non_equivalent_dates"]),
        }
    ]
    cash_rows = [
        {
            **row,
            "B002_CASH_EFFECT_MATERIALITY": b002["summary"]["cash_effect"][
                "B002_CASH_EFFECT_MATERIALITY"
            ],
        }
        for row in b002["date_rows"]
    ]
    mature_rows = [
        {
            **b002["summary"]["mature_history"],
            "control_2023_2024_return_pct": b002["summary"][
                "control_2023_2024_return_pct"
            ],
            "B002_2023_2024_return_pct": b002["summary"]["B002_2023_2024_return_pct"],
            "B002_2023_2024_difference_pp": b002["summary"]["B002_2023_2024_difference_pp"],
        }
    ]
    report_rows: dict[str, Sequence[Mapping[str, Any]]] = {
        REPORT_NAMES[1]: b001_summary_rows,
        REPORT_NAMES[2]: b001["rows"],
        REPORT_NAMES[3]: b002["removal_rows"],
        REPORT_NAMES[4]: b002["interval_rows"],
        REPORT_NAMES[5]: cash_rows,
        REPORT_NAMES[6]: b002["year_rows"],
        REPORT_NAMES[7]: mature_rows,
        REPORT_NAMES[8]: b002["timeline_rows"],
    }
    artifact_paths: list[Path] = [result_path]
    internal_rows = {
        directories["b001"] / "b001_equivalence_summary.csv": b001_summary_rows,
        directories["b001"] / "b001_rebalance_diff.csv": b001["rows"],
        directories["b002"] / "b002_removals.csv": b002["removal_rows"],
        directories["b002"] / "b002_intervals.csv": b002["interval_rows"],
        directories["b002"] / "b002_cash.csv": cash_rows,
        directories["b002"] / "year_attribution.csv": b002["year_rows"],
        directories["b002"] / "mature_history.csv": mature_rows,
        directories["timeline"] / "normalized_equity.csv": b002["timeline_rows"],
    }
    for path, rows in internal_rows.items():
        write_csv(path, rows)
        artifact_paths.append(path)
    for report_name, rows in report_rows.items():
        path = reports_root / report_name
        write_csv(path, rows)
        artifact_paths.append(path)
    documentation_path = root / "docs/strategy-family-b-attribution-audit-v1.md"
    if documentation_path.exists():
        artifact_paths.append(documentation_path)

    frozen_after = verify_frozen_inputs(root)
    baseline_unchanged = frozen_before["snapshot"] == frozen_after["snapshot"]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path) for path in artifact_paths
    }
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": started_at,
        "family_version": FAMILY_VERSION,
        "hash_gate": {
            "status": frozen_before["status"],
            "checks": frozen_before["checks"],
            "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
            "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "result_hashes": EXPECTED_RESULT_HASHES,
            "development_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        },
        "primary_questions": answers,
        "B001": b001["summary"],
        "B002": b002["summary"],
        "decision": decisions,
        "family_b_attribution_audit_hash": immutable_result[
            "family_b_attribution_audit_hash"
        ],
        "governance": governance,
        "regression": {
            "frozen_input_snapshot_before": frozen_before["snapshot"]["snapshot_hash"],
            "frozen_input_snapshot_after": frozen_after["snapshot"]["snapshot_hash"],
            "baseline_unchanged": baseline_unchanged,
            "strategy_v1": "UNCHANGED",
            "CAP4": "UNCHANGED",
            "family_a_commands_01_05": "UNCHANGED",
            "family_a_closure": "UNCHANGED",
            "family_b_command_01": "UNCHANGED",
            "family_b_command_02": "UNCHANGED",
        },
        "storage": {
            "root": output_root.relative_to(root).as_posix(),
            "b001_equivalence": directories["b001"].relative_to(root).as_posix(),
            "b002_attribution": directories["b002"].relative_to(root).as_posix(),
            "timeline": directories["timeline"].relative_to(root).as_posix(),
            "manifests": directories["manifests"].relative_to(root).as_posix(),
            "artifact_hashes": artifact_hashes,
        },
        "runtime": {
            "seconds": Decimal(str(time.perf_counter() - started)),
            "performance_replays": 0,
            "new_strategy_curves": 0,
        },
        "known_limitations": result_body["known_limitations"],
        "verification": {
            "backend_tests": "PENDING",
            "frontend_build": "PENDING",
            "ready_for_review": False,
        },
    }
    summary_path = reports_root / REPORT_NAMES[0]
    write_json(summary_path, summary)
    manifest = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_version": FAMILY_VERSION,
        "generated_at": started_at,
        "family_b_attribution_audit_hash": summary["family_b_attribution_audit_hash"],
        "frozen_input_snapshot_hash": frozen_before["snapshot"]["snapshot_hash"],
        "development_latest_date_loaded": DEVELOPMENT_END.isoformat(),
        "validation_accessed": False,
        "artifact_hashes": artifact_hashes,
        "summary_hash_at_generation": file_sha256(summary_path),
    }
    write_json(directories["manifests"] / "run_manifest_v1.json", manifest)
    return summary


def finalize_family_b_attribution_review(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports/family_b_attribution_v1_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError("Run the Family B attribution audit before finalizing")
    summary = _read_json(summary_path)
    frozen = verify_frozen_inputs(root)
    if frozen["snapshot"]["snapshot_hash"] != summary["regression"][
        "frozen_input_snapshot_after"
    ]:
        _fail_input("frozen state changed after attribution audit")
    result_path = (
        root
        / "data/research/strategy_families/family_b/v1/attribution_audit/manifests/family_b_attribution_audit_result_v1.json"
    )
    result = _read_json(result_path)
    observed_hash = result.get("family_b_attribution_audit_hash")
    if (
        observed_hash != summary.get("family_b_attribution_audit_hash")
        or _recompute_hash(result, "family_b_attribution_audit_hash") != observed_hash
        or (EXPECTED_ATTRIBUTION_AUDIT_HASH and observed_hash != EXPECTED_ATTRIBUTION_AUDIT_HASH)
    ):
        raise FamilyBAttributionImmutabilityError("Family B attribution result hash mismatch")
    manifest = _read_json(
        root
        / "data/research/strategy_families/family_b/v1/attribution_audit/manifests/run_manifest_v1.json"
    )
    mismatches = [
        relative_path
        for relative_path, expected_hash in manifest["artifact_hashes"].items()
        if not (root / relative_path).exists()
        or file_sha256(root / relative_path) != expected_hash
    ]
    if mismatches:
        raise FamilyBAttributionImmutabilityError(
            f"Family B attribution artifact mismatch: {mismatches}"
        )
    passed = backend_tests == "PASSED" and frontend_build == "PASSED"
    summary["verification"] = {
        "backend_tests": backend_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed
        and summary["regression"]["baseline_unchanged"] is True
        and summary["governance"]["validation_accessed"] is False
        and summary["decision"]["FAMILY_B_VALIDATION_DESIGN_READINESS"]
        == "NO_CANDIDATE_READY",
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    return summary


__all__ = (
    "ATTRIBUTION_CATEGORIES",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXPECTED_ATTRIBUTION_AUDIT_HASH",
    "FamilyBAttributionImmutabilityError",
    "FamilyBAttributionInputMismatch",
    "REMOVAL_CATEGORIES",
    "REPLAY_LABEL",
    "REPLAY_STATUS",
    "REPORT_NAMES",
    "b001_control_equivalence",
    "b002_attribution",
    "build_family_b_attribution_audit",
    "finalize_family_b_attribution_review",
    "verify_frozen_inputs",
)
