from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH
from app.backtesting.costs.cost_engine import SCENARIO_BASELINE_SLIPPAGE
from app.backtesting.costs.cost_models import canonical_hash
from app.research.strategy.family_a_momentum import (
    decimal,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_c_breakout_continuation import (
    BREAKOUT_WINDOW,
    COMPRESSION_THRESHOLD,
    COMPRESSION_WINDOW,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_FAMILY_C_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    FAMILY_CODE,
    FAMILY_VERSION,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    STARTING_CAPITAL,
    TARGET_NOTIONAL_FRACTION,
    _load_adjusted_bars,
    _load_aliases,
    _load_membership,
    _load_sessions,
    entry_exit_chronology,
)
from app.research.strategy.family_c_c001_attribution_audit import (
    EXPECTED_C001_RESULT_HASH,
    EXPECTED_DEVELOPMENT_REGISTRY_HASH,
    output_root as attribution_output_root,
    verify_frozen_inputs as verify_attribution_upstream,
)
from app.research.strategy.family_c_development_evaluation import (
    EXECUTABLE_MODE,
    _bar_path_available,
    _load_signal_rows,
)


COMMAND = "Step 03.03 / Command 04"
COMMAND_VERSION = "FAMILY_C_C001_IMPLEMENTATION_RESEARCH_V1"
COMMAND_PROFILE = "C001_COMPRESSION_PRIORITY_PREREGISTRATION_V1"
EXPERIMENT_ID = "C1-IMP-001"
EXPERIMENT_NAME = "C001_COMPRESSION_PRIORITY_CAPACITY_RANKING_V1"
REFERENCE_EXPERIMENT_ID = "BRK-C-001"
EXPECTED_ATTRIBUTION_HASH = (
    "26a320930facd5c3007a75e22573e27171d6e85cb6a4ea02dc209e6975a38e4b"
)
ROADMAP_STATUS = "ACTIVE_CONTROLLED_IMPLEMENTATION_RESEARCH"
SIGNAL_SET_LABEL = "FROZEN_C001_VALID_PRECAPACITY_SIGNAL_SET_V1"
STRUCTURAL_PILOT_LABEL = "STRUCTURAL_PILOT_NO_PERFORMANCE"

ORIGINAL_RANKING = (
    "BREAKOUT_STRENGTH_PCT_DESCENDING",
    "SYMBOL_ASCENDING",
)
TREATMENT_RANKING = (
    "COMPRESSION_RANGE_PCT_ASCENDING",
    "BREAKOUT_STRENGTH_PCT_DESCENDING",
    "SYMBOL_ASCENDING",
)

REPORT_NAMES = (
    "family_c_imp001_v1_summary.json",
    "family_c_imp001_v1_registry.csv",
    "family_c_imp001_v1_ranking_pilot.csv",
    "family_c_imp001_v1_real_date_pilots.csv",
    "family_c_imp001_v1_governance.csv",
    "family_c_imp001_v1_readiness.csv",
)

GOVERNANCE_ITEMS = (
    "hypothesis",
    "ID",
    "population",
    "parameters",
    "control",
    "metrics",
    "secondary_metrics",
    "numerical_criteria",
    "failure_criteria",
    "stop_conditions",
    "validation_eligibility",
    "cost_model",
    "partition",
    "hashes",
)


class FamilyCImplementationPreregInputMismatch(RuntimeError):
    pass


class FamilyCImplementationPreregImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return root / "data/research/strategy_families/family_c/v1/implementation_research"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_hash(document: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != field}


def _hash_matches(document: Mapping[str, Any], field: str, expected: str) -> bool:
    return document.get(field) == expected and canonical_hash(
        _without_hash(document, field)
    ) == expected


def command_03_snapshot(root: Path) -> dict[str, Any]:
    audit_root = attribution_output_root(root)
    paths = [path for path in audit_root.rglob("*") if path.is_file()]
    paths.extend(sorted((root / "data/reports").glob("family_c_c001_attribution_v1_*")))
    paths.extend(
        root / relative
        for relative in (
            "backend/app/research/strategy/family_c_c001_attribution_audit.py",
            "backend/scripts/run_family_c_c001_attribution_audit.py",
            "backend/tests/test_family_c_c001_attribution_audit.py",
            "docs/strategy-family-c-c001-attribution-audit-v1.md",
        )
    )
    hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
        if path.is_file()
    }
    return {"artifact_hashes": hashes, "snapshot_hash": canonical_hash(hashes)}


def verify_frozen_inputs(root: Path) -> dict[str, Any]:
    upstream = verify_attribution_upstream(root)
    audit_root = attribution_output_root(root)
    result_path = audit_root / "manifests/family_c_c001_attribution_result_v1.json"
    manifest_path = audit_root / "manifests/family_c_c001_attribution_manifest_v1.json"
    summary_path = root / "data/reports/family_c_c001_attribution_v1_summary.json"
    result = _read_json(result_path)
    manifest = _read_json(manifest_path)
    summary = _read_json(summary_path)
    result_field = "family_c_c001_attribution_hash"
    manifest_field = "family_c_c001_attribution_manifest_hash"
    checks = {
        "family_config_hash": result["frozen_hashes"]["family_c_config_hash"]
        == EXPECTED_FAMILY_C_CONFIG_HASH,
        "success_criteria_hash": result["frozen_hashes"]["success_criteria_hash"]
        == EXPECTED_SUCCESS_CRITERIA_HASH,
        "C001_result_hash": result["frozen_hashes"]["brk_c_001_result_hash"]
        == EXPECTED_C001_RESULT_HASH,
        "development_registry_hash": result["frozen_hashes"][
            "family_c_development_registry_hash"
        ]
        == EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        "attribution_result_hash": _hash_matches(
            result, result_field, EXPECTED_ATTRIBUTION_HASH
        ),
        "attribution_summary_hash": summary.get(result_field)
        == EXPECTED_ATTRIBUTION_HASH,
        "attribution_manifest_hash": canonical_hash(
            _without_hash(manifest, manifest_field)
        )
        == manifest.get(manifest_field),
        "manifest_summary_hash": manifest.get("summary_hash")
        == file_sha256(summary_path),
        "frozen_attribution_findings": (
            result["signal_cohort"]["C001_SIGNAL_QUALITY_ATTRIBUTION"]
            == "CLEAR_POSITIVE"
            and result["signal_cohort"]["C001_SIGNAL_TEMPORAL_CONSISTENCY"]
            == "MOSTLY_CONSISTENT"
            and result["capacity"]["C001_CAPACITY_SELECTION_QUALITY"]
            == "SELECTED_WORSE"
            and result["capacity"]["BREAKOUT_STRENGTH_CAPACITY_RANKING_RESULT"]
            == "NO_DISCRIMINATION"
            and result["attribution"]["C001_DEVELOPMENT_ADVANTAGE_ATTRIBUTION"]
            == "PRIMARILY_COMPRESSION_SIGNAL"
        ),
        "development_only": (
            result["development_partition"]["start"]
            == DEVELOPMENT_START.isoformat()
            and result["development_partition"]["end"]
            == DEVELOPMENT_END.isoformat()
            and result["development_partition"]["post_2024_accessed"] is False
            and result["development_partition"]["validation_accessed"] is False
        ),
    }
    artifact_mismatches = [
        relative
        for relative, expected_hash in manifest["artifact_hashes"].items()
        if not (root / relative).is_file()
        or file_sha256(root / relative) != expected_hash
    ]
    checks["attribution_artifact_hashes"] = not artifact_mismatches
    if not all(checks.values()):
        raise FamilyCImplementationPreregInputMismatch(
            "FAMILY_C_IMPLEMENTATION_PREREG_INPUT_MISMATCH: "
            f"checks={checks}; artifacts={artifact_mismatches}"
        )
    return {
        "status": "VERIFIED",
        "checks": checks,
        "upstream": upstream,
        "attribution_result": result,
        "attribution_summary": summary,
        "attribution_manifest": manifest,
    }


def rank_compression_priority(
    rows: Sequence[Mapping[str, Any]], available_slots: int
) -> dict[str, list[dict[str, Any]]]:
    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            decimal(row["compression_range_pct"]),
            -decimal(row["breakout_strength_pct"]),
            str(row["symbol"]),
        ),
    )
    slots = max(0, int(available_slots))
    return {
        "ranked": ordered,
        "selected": ordered[:slots],
        "rejected": ordered[slots:],
    }


def _signal_set_body(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "signal_set_label": SIGNAL_SET_LABEL,
        "family_code": FAMILY_CODE,
        "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
        "population": "FROZEN_C001_VALID_PRECAPACITY_COMPLETE_PATH_DEVELOPMENT_SIGNALS",
        "development_start": DEVELOPMENT_START.isoformat(),
        "development_end": DEVELOPMENT_END.isoformat(),
        "compression_threshold": COMPRESSION_THRESHOLD,
        "event_count": len(rows),
        "events": list(rows),
    }


def build_c001_signal_set(root: Path) -> list[dict[str, Any]]:
    signal_rows = _load_signal_rows(root)
    aliases = _load_aliases(root)
    membership = _load_membership(root)
    sessions = _load_sessions(root)
    bars = _load_adjusted_bars(root, set(membership.grouped), aliases)
    if any(session > DEVELOPMENT_END for session in bars):
        raise ValueError("Post-2024 bars loaded during signal-set construction")
    output = []
    for row in signal_rows:
        if not bool(row["c001_signal"]):
            continue
        compression = row["compression_range_pct"]
        if compression is None or decimal(compression) > COMPRESSION_THRESHOLD:
            raise ValueError("Frozen C001 signal escaped exact <=8% threshold")
        chronology = entry_exit_chronology(sessions, row["decision_date"])
        available, _ = _bar_path_available(str(row["symbol"]), chronology, bars)
        if not available:
            continue
        if chronology["entry_date"] is None or chronology["exit_date"] is None:
            raise ValueError("Complete frozen C001 signal lacks chronology")
        output.append(
            {
                "event_key": f"{row['decision_date'].isoformat()}|{row['symbol']}",
                "formation_date": row["decision_date"].isoformat(),
                "entry_date": chronology["entry_date"].isoformat(),
                "required_exit_date": chronology["exit_date"].isoformat(),
                "symbol": row["symbol"],
                "isin": row["isin"],
                "compression_range_pct": compression,
                "breakout_strength_pct": row["breakout_strength_pct"],
                "control_signal": bool(row["control_signal"]),
                "c001_signal": True,
            }
        )
    output.sort(key=lambda row: (row["formation_date"], row["symbol"]))
    if len({row["event_key"] for row in output}) != len(output):
        raise ValueError("Duplicate C001 signal-set key")
    return output


def verify_signal_set_identity(
    root: Path, signal_set: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    attribution_events = read_csv(
        root / "data/reports/family_c_c001_attribution_v1_event_cohort.csv"
    )
    frozen = {
        row["event_key"]: row
        for row in attribution_events
        if row["compression_pass"] == "True"
    }
    treatment = {str(row["event_key"]): row for row in signal_set}
    missing = sorted(set(frozen) - set(treatment))
    extra = sorted(set(treatment) - set(frozen))
    field_mismatches = []
    for key in sorted(set(frozen) & set(treatment)):
        old = frozen[key]
        new = treatment[key]
        if (
            old["formation_date"] != new["formation_date"]
            or old["entry_date"] != new["entry_date"]
            or old["symbol"] != new["symbol"]
            or decimal(old["compression_range_pct"])
            != decimal(new["compression_range_pct"])
            or decimal(old["breakout_strength_pct"])
            != decimal(new["breakout_strength_pct"])
        ):
            field_mismatches.append(key)
    equal = not missing and not extra and not field_mismatches
    if not equal:
        raise FamilyCImplementationPreregInputMismatch(
            "FAMILY_C_IMPLEMENTATION_PREREG_INPUT_MISMATCH: signal-set identity"
        )
    body = _signal_set_body(signal_set)
    return {
        "equal": equal,
        "frozen_count": len(frozen),
        "treatment_count": len(treatment),
        "missing_count": len(missing),
        "extra_count": len(extra),
        "field_mismatch_count": len(field_mismatches),
        "c001_signal_set_hash": canonical_hash(body),
        "signal_set_body": body,
    }


def implementation_research_config() -> dict[str, Any]:
    body = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_version": FAMILY_VERSION,
        "family_code": FAMILY_CODE,
        "architecture_scope": "PREREGISTRATION_IMPLEMENTATION_ARCHITECTURE_STRUCTURAL_PILOTS_ONLY",
        "experiment_limit": 1,
        "experiment_id": EXPERIMENT_ID,
        "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
        "hypothesis": (
            "When valid frozen C001 signals exceed available slots, prioritizing tighter "
            "pre-breakout compression may preserve more of the demonstrated compression "
            "edge than ranking by breakout magnitude."
        ),
        "only_experimental_change": "SAME_DAY_CAPACITY_RANKING",
        "original_ranking": ORIGINAL_RANKING,
        "treatment_ranking": TREATMENT_RANKING,
        "development_partition": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "validation_accessed": False,
        },
        "future_performance_mode": EXECUTABLE_MODE,
        "performance_run_in_this_command": False,
        "promotion_allowed": False,
    }
    return {**body, "implementation_research_config_hash": canonical_hash(body)}


def implementation_parameters(signal_set_hash: str) -> dict[str, Any]:
    body = {
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "family_code": FAMILY_CODE,
        "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
        "c001_signal_set_hash": signal_set_hash,
        "breakout": {
            "lookback_sessions": BREAKOUT_WINDOW,
            "rule": "CLOSE_T_STRICTLY_GREATER_THAN_MAX_HIGH_T_MINUS_20_THROUGH_T_MINUS_1",
        },
        "compression": {
            "window_sessions": COMPRESSION_WINDOW,
            "rule": "MAX_HIGH_MINUS_MIN_LOW_DIVIDED_BY_CLOSE_T",
            "operator": "<=",
            "threshold": COMPRESSION_THRESHOLD,
        },
        "entry": "T_PLUS_1_ELIGIBLE_OPEN",
        "holding_completed_sessions": HOLDING_SESSIONS,
        "exit": "NEXT_ELIGIBLE_OPEN_AFTER_T_PLUS_10",
        "starting_capital": STARTING_CAPITAL,
        "max_concurrent_positions": MAX_CONCURRENT_POSITIONS,
        "target_notional_fraction_of_current_equity": TARGET_NOTIONAL_FRACTION,
        "whole_shares": True,
        "one_position_per_symbol": True,
        "leverage": False,
        "stop": None,
        "target": None,
        "trailing_exit": None,
        "capacity_ranking": TREATMENT_RANKING,
        "continuous_compression_score": False,
        "weighted_ranking": False,
        "secondary_ranking_experiment": False,
        "costs": {
            "model": "INDIA_EQUITY_COST_MODEL_V1",
            "profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "scenario": SCENARIO_BASELINE_SLIPPAGE,
            "slippage_bps_per_side": "5",
            "cost_config_hash": EXPECTED_COST_CONFIG_HASH,
        },
    }
    return {**body, "parameter_hash": canonical_hash(body)}


def implementation_success_criteria(
    frozen_c001_metrics: Mapping[str, Any],
    frozen_admitted_metrics: Mapping[str, Any],
) -> dict[str, Any]:
    body = {
        "criteria_version": "C1_IMP_001_IMPLEMENTATION_SUCCESS_CRITERIA_V1",
        "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
        "reference_values": {
            "admitted_normalized_event_expectancy": frozen_admitted_metrics[
                "net_expectancy"
            ],
            "admitted_normalized_event_profit_factor": frozen_admitted_metrics[
                "net_profit_factor"
            ],
            "admitted_normalized_event_win_rate": frozen_admitted_metrics[
                "win_rate"
            ],
            "portfolio_net_CAGR": frozen_c001_metrics["net_CAGR"],
            "portfolio_max_drawdown": frozen_c001_metrics["max_drawdown"],
            "portfolio_normalized_cost_drag": frozen_c001_metrics[
                "normalized_cost_drag"
            ],
            "yearly_returns": frozen_c001_metrics["yearly_returns"],
        },
        "admitted_quality_dimensions": {
            "EXPECTANCY": {
                "formula": "TREATMENT_ADMITTED_EXPECTANCY_GTE_REFERENCE_TIMES_1_15",
                "multiplier": "1.15",
            },
            "PROFIT_FACTOR": {
                "formula": "TREATMENT_ADMITTED_PF_GTE_REFERENCE_PLUS_0_05",
                "absolute_increment": "0.05",
            },
            "WIN_RATE": {
                "formula": "TREATMENT_ADMITTED_WIN_RATE_MINUS_REFERENCE_GTE_0_03",
                "percentage_point_increment": "0.03",
            },
        },
        "primary_implementation_success": "AT_LEAST_TWO_OF_THREE_ADMITTED_QUALITY_DIMENSIONS",
        "standard_criteria_A_H": {
            "A_CAPACITY_QUALITY_IMPROVEMENT": "AT_LEAST_TWO_OF_THREE_ADMITTED_QUALITY_DIMENSIONS",
            "B_PORTFOLIO_PROFITABILITY": "NET_EXPECTANCY_GT_0_AND_NET_PF_GTE_1_10",
            "C_RETURN_NON_DEGRADATION": "NET_CAGR_GTE_REFERENCE_NET_CAGR_TIMES_0_90",
            "D_DRAWDOWN_NON_DEGRADATION": "MAX_DRAWDOWN_RELATIVE_WORSENING_LTE_0_10",
            "E_TEMPORAL_SUPPORT": "AT_LEAST_TWO_OF_THREE_YEARS_NONNEGATIVE_AND_AT_MOST_ONE_YEAR_UNDERPERFORMS_REFERENCE_BY_GT_0_10",
            "F_COST_NON_DEGRADATION": "NORMALIZED_COST_DRAG_LTE_REFERENCE_TIMES_1_20",
            "G_SAMPLE_ADEQUACY": "NORMAL_GTE_500_LIMITED_250_TO_499_FATAL_LT_250",
            "H_ACCOUNTING_DATA_INTEGRITY": "ALL_FROZEN_ACCOUNTING_AND_DATA_CHECKS_PASS",
        },
        "strongly_supported": {
            "all_A_H_pass": True,
            "all_three_admitted_quality_dimensions_improve": True,
            "net_CAGR_strictly_greater_than_reference": True,
            "net_profit_factor_minimum": "1.15",
        },
        "supported": {
            "all_A_H_pass": True,
            "minimum_admitted_quality_dimensions_improved": 2,
        },
        "partially_supported": {
            "fatal_failure": False,
            "minimum_A_H_pass": 6,
            "minimum_admitted_quality_dimensions_improved": 1,
        },
        "failed": {
            "fatal_failure": True,
            "or_fewer_than_A_H_pass": 6,
            "or_at_least_two_admitted_quality_dimensions_clearly_worse": True,
        },
        "inconclusive": "UNRESOLVED_MECHANICS_OR_DATA_ONLY",
        "high_win_rate_flag": "YES_IF_POSITION_WIN_RATE_GTE_0_60_DESCRIPTIVE_ONLY",
        "signal_set_invariant": "EXACT_EQUALITY_REQUIRED_OR_STOP",
        "accounting_data_requirements": (
            "NO_LOOKAHEAD",
            "CLEAN_CHRONOLOGY",
            "SAME_C001_SIGNAL_SET",
            "EXACT_CAPACITY_RANKING",
            "WHOLE_SHARE_ACCOUNTING",
            "CASH_EQUITY_RECONCILIATION",
            "TERMINAL_PATH_PROTECTION",
            "CORPORATE_ACTION_SAFETY",
        ),
    }
    return {
        **body,
        "implementation_success_criteria_hash": canonical_hash(body),
    }


def preregistration(
    config: Mapping[str, Any],
    parameters: Mapping[str, Any],
    criteria: Mapping[str, Any],
    signal_set_hash: str,
) -> dict[str, Any]:
    body = {
        "command_version": COMMAND_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "family_code": FAMILY_CODE,
        "status": "PREREGISTERED",
        "promotion_allowed": False,
        "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
        "hypothesis": config["hypothesis"],
        "only_experimental_change": "SAME_DAY_CAPACITY_RANKING",
        "parameter_hash": parameters["parameter_hash"],
        "implementation_success_criteria_hash": criteria[
            "implementation_success_criteria_hash"
        ],
        "implementation_research_config_hash": config[
            "implementation_research_config_hash"
        ],
        "c001_signal_set_hash": signal_set_hash,
        "family_c_c001_attribution_hash": EXPECTED_ATTRIBUTION_HASH,
        "development_partition": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
        },
        "performance_run": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    return {**body, "preregistration_hash": canonical_hash(body)}


def synthetic_ranking_pilot() -> list[dict[str, Any]]:
    fixtures = [
        {"symbol": "ECHO", "compression_range_pct": "0.060", "breakout_strength_pct": "0.090"},
        {"symbol": "CHARLIE", "compression_range_pct": "0.050", "breakout_strength_pct": "0.020"},
        {"symbol": "ALPHA", "compression_range_pct": "0.050", "breakout_strength_pct": "0.020"},
        {"symbol": "BRAVO", "compression_range_pct": "0.050", "breakout_strength_pct": "0.030"},
        {"symbol": "DELTA", "compression_range_pct": "0.040", "breakout_strength_pct": "0.010"},
    ]
    result = rank_compression_priority(fixtures, 3)
    expected_order = ("DELTA", "BRAVO", "ALPHA", "CHARLIE", "ECHO")
    actual_order = tuple(row["symbol"] for row in result["ranked"])
    if actual_order != expected_order:
        raise ValueError(f"Compression-priority ranking pilot failed: {actual_order}")
    return [
        {
            "pilot_label": STRUCTURAL_PILOT_LABEL,
            "symbol": row["symbol"],
            "compression_range_pct": row["compression_range_pct"],
            "breakout_strength_pct": row["breakout_strength_pct"],
            "treatment_rank": rank,
            "selected_with_three_slots": rank <= 3,
            "expected_rank": expected_order.index(row["symbol"]) + 1,
            "ordering_verified": True,
            "performance_calculated": False,
        }
        for rank, row in enumerate(result["ranked"], 1)
    ]


def real_date_structural_pilots(
    root: Path, signal_set: Sequence[Mapping[str, Any]], pilot_dates: int = 5
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    admissions = read_csv(
        attribution_output_root(root)
        / "capacity/c001_admission_classification_v1.csv"
    )
    signal_map = {str(row["event_key"]): row for row in signal_set}
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in admissions:
        if row["admission_status"] not in {
            "ADMITTED",
            "CAPACITY_REJECTED",
            "AFFORDABILITY_REJECTED",
        }:
            continue
        event = signal_map.get(row["event_key"])
        if event is None:
            raise ValueError("Admission candidate missing from frozen signal set")
        grouped[row["formation_date"]].append({**row, **event})
    eligible_dates = [
        (formation_date, rows)
        for formation_date, rows in grouped.items()
        if any(row["admission_status"] == "CAPACITY_REJECTED" for row in rows)
        and not any(row["admission_status"] == "AFFORDABILITY_REJECTED" for row in rows)
    ]
    chosen = sorted(
        eligible_dates,
        key=lambda item: (-len(item[1]), item[0]),
    )[:pilot_dates]
    output: list[dict[str, Any]] = []
    for formation_date, rows in sorted(chosen):
        open_before_values = {
            int(row["open_positions_before_entry"]) for row in rows
        }
        if len(open_before_values) != 1:
            raise ValueError("Real-date pilot has inconsistent pre-entry occupancy")
        open_before = next(iter(open_before_values))
        available_slots = MAX_CONCURRENT_POSITIONS - open_before
        ranked = rank_compression_priority(rows, available_slots)["ranked"]
        for new_rank, row in enumerate(ranked, 1):
            old_admitted = row["admission_status"] == "ADMITTED"
            new_selected = new_rank <= available_slots
            output.append(
                {
                    "pilot_label": STRUCTURAL_PILOT_LABEL,
                    "formation_date": formation_date,
                    "entry_date": row["entry_date"],
                    "symbol": row["symbol"],
                    "compression_range_pct": row["compression_range_pct"],
                    "breakout_strength_pct": row["breakout_strength_pct"],
                    "old_rank": int(row["same_day_rank"]),
                    "new_rank": new_rank,
                    "old_admitted_status": row["admission_status"],
                    "new_hypothetical_rank_status": "HYPOTHETICALLY_SELECTED_BY_SLOT_QUOTA"
                    if new_selected
                    else "HYPOTHETICALLY_CAPACITY_REJECTED",
                    "open_positions_before_entry": open_before,
                    "available_slots": available_slots,
                    "selection_changed": old_admitted != new_selected,
                    "affordability_simulated": False,
                    "performance_calculated": False,
                    "validation_accessed": False,
                }
            )
    findings = {
        "real_date_pilot_count": len(chosen),
        "candidate_row_count": len(output),
        "selection_changed_rows": sum(row["selection_changed"] for row in output),
        "old_admitted_new_rejected": sum(
            row["old_admitted_status"] == "ADMITTED"
            and row["new_hypothetical_rank_status"]
            == "HYPOTHETICALLY_CAPACITY_REJECTED"
            for row in output
        ),
        "old_rejected_new_selected": sum(
            row["old_admitted_status"] == "CAPACITY_REJECTED"
            and row["new_hypothetical_rank_status"]
            == "HYPOTHETICALLY_SELECTED_BY_SLOT_QUOTA"
            for row in output
        ),
        "pilot_dates": [formation_date for formation_date, _ in sorted(chosen)],
        "performance_calculated": False,
    }
    return output, findings


def governance_rows(
    config: Mapping[str, Any],
    parameters: Mapping[str, Any],
    criteria: Mapping[str, Any],
    prereg: Mapping[str, Any],
) -> list[dict[str, Any]]:
    evidence = {
        "hypothesis": config["hypothesis"],
        "ID": EXPERIMENT_ID,
        "population": SIGNAL_SET_LABEL,
        "parameters": parameters["parameter_hash"],
        "control": REFERENCE_EXPERIMENT_ID,
        "metrics": "FROZEN_PRIMARY_FUTURE_METRICS",
        "secondary_metrics": "FROZEN_CAPACITY_QUALITY_METRICS",
        "numerical_criteria": criteria["implementation_success_criteria_hash"],
        "failure_criteria": criteria["failed"],
        "stop_conditions": "INPUT_OR_SIGNAL_SET_MISMATCH_AND_FATAL_SAMPLE_FAILURE",
        "validation_eligibility": "NOT_ELIGIBLE_IN_THIS_COMMAND",
        "cost_model": parameters["costs"],
        "partition": prereg["development_partition"],
        "hashes": {
            "config": config["implementation_research_config_hash"],
            "parameters": parameters["parameter_hash"],
            "criteria": criteria["implementation_success_criteria_hash"],
            "preregistration": prereg["preregistration_hash"],
        },
    }
    return [
        {
            "check_number": index,
            "check": item,
            "status": "PASS",
            "evidence": evidence[item],
            "governance_version": "RESEARCH_EXPERIMENT_GOVERNANCE_V2",
        }
        for index, item in enumerate(GOVERNANCE_ITEMS, 1)
    ]


def _immutable_json(path: Path, document: Mapping[str, Any], hash_field: str) -> None:
    if path.is_file():
        previous = _read_json(path)
        if previous.get(hash_field) != document.get(hash_field):
            raise FamilyCImplementationPreregImmutabilityError(
                f"Frozen implementation preregistration would change: {path.name}"
            )
    write_json(path, document)


def build_family_c_c001_implementation_research(root: Path) -> dict[str, Any]:
    started_at = utc_now()
    frozen = verify_frozen_inputs(root)
    command_03_before = command_03_snapshot(root)

    signal_set = build_c001_signal_set(root)
    signal_identity = verify_signal_set_identity(root, signal_set)
    signal_set_record = {
        **signal_identity["signal_set_body"],
        "c001_signal_set_hash": signal_identity["c001_signal_set_hash"],
    }
    config = implementation_research_config()
    parameters = implementation_parameters(signal_identity["c001_signal_set_hash"])
    attribution = frozen["attribution_result"]
    frozen_c001_metrics = frozen["upstream"]["development_summary"]["results"][
        "BRK-C-001"
    ]["executable_metrics"]
    admitted_metrics = next(
        row
        for row in attribution["capacity"]["admitted_vs_capacity_rejected"]
        if row["cohort"] == "C001_ADMITTED" and "year" not in row
    )
    criteria = implementation_success_criteria(
        frozen_c001_metrics, admitted_metrics
    )
    prereg = preregistration(
        config,
        parameters,
        criteria,
        signal_identity["c001_signal_set_hash"],
    )
    registry_body = {
        "registry_version": "FAMILY_C_IMPLEMENTATION_RESEARCH_REGISTRY_V1",
        "family_code": FAMILY_CODE,
        "experiment_count": 1,
        "experiments": [
            {
                "experiment_id": EXPERIMENT_ID,
                "experiment_name": EXPERIMENT_NAME,
                "status": "PREREGISTERED",
                "promotion_allowed": False,
                "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
                "parameter_hash": parameters["parameter_hash"],
                "preregistration_hash": prereg["preregistration_hash"],
                "implementation_success_criteria_hash": criteria[
                    "implementation_success_criteria_hash"
                ],
                "c001_signal_set_hash": signal_identity["c001_signal_set_hash"],
            }
        ],
        "validation_accessed": False,
        "performance_run": False,
    }
    registry = {
        **registry_body,
        "implementation_research_registry_hash": canonical_hash(registry_body),
    }
    synthetic = synthetic_ranking_pilot()
    real_date_pilots, real_date_findings = real_date_structural_pilots(
        root, signal_set
    )
    governance = governance_rows(config, parameters, criteria, prereg)
    governance_pass = len(governance) == 14 and all(
        row["status"] == "PASS" for row in governance
    )

    readiness_checks = {
        "frozen_inputs_verified": frozen["status"] == "VERIFIED",
        "one_experiment_only": registry["experiment_count"] == 1,
        "signal_set_equal": signal_identity["equal"],
        "signal_set_nonempty": bool(signal_set),
        "synthetic_ranking_verified": all(
            row["ordering_verified"] for row in synthetic
        ),
        "real_date_pilots_present": real_date_findings[
            "real_date_pilot_count"
        ]
        >= 3,
        "governance_14_of_14": governance_pass,
        "only_capacity_ranking_changes": config["only_experimental_change"]
        == "SAME_DAY_CAPACITY_RANKING",
        "performance_not_run": True,
        "validation_not_accessed": True,
    }
    architecture_result = (
        "READY_FOR_CONTROLLED_DEVELOPMENT_TEST"
        if all(readiness_checks.values())
        else "METHODOLOGY_FIX_REQUIRED"
    )

    research_root = output_root(root)
    registry_root = research_root / "registry"
    pilots_root = research_root / "pilots"
    manifests_root = research_root / "manifests"
    governance_root = research_root / "governance"
    ranking_root = research_root / "ranking"
    reports_root = root / "data/reports"
    manifest_path = manifests_root / "implementation_research_manifest_v1.json"

    _immutable_json(
        registry_root / "implementation_research_config_v1.json",
        config,
        "implementation_research_config_hash",
    )
    _immutable_json(
        registry_root / "c1_imp_001_preregistration_v1.json",
        prereg,
        "preregistration_hash",
    )
    _immutable_json(
        registry_root / "implementation_research_registry_v1.json",
        registry,
        "implementation_research_registry_hash",
    )
    _immutable_json(
        governance_root / "implementation_success_criteria_v1.json",
        criteria,
        "implementation_success_criteria_hash",
    )
    _immutable_json(
        ranking_root / "c001_signal_set_v1.json",
        signal_set_record,
        "c001_signal_set_hash",
    )
    write_csv(ranking_root / "c001_signal_set_v1.csv", signal_set)
    write_csv(pilots_root / "synthetic_ranking_pilot_v1.csv", synthetic)
    write_csv(pilots_root / "real_date_ranking_pilots_v1.csv", real_date_pilots)
    write_csv(governance_root / "governance_v2_checklist_v1.csv", governance)

    registry_report = registry["experiments"]
    readiness_rows = [
        {
            "check": key,
            "status": "PASS" if value else "FAIL",
            "architecture_result": architecture_result,
        }
        for key, value in readiness_checks.items()
    ]
    write_csv(reports_root / REPORT_NAMES[1], registry_report)
    write_csv(reports_root / REPORT_NAMES[2], synthetic)
    write_csv(reports_root / REPORT_NAMES[3], real_date_pilots)
    write_csv(reports_root / REPORT_NAMES[4], governance)
    write_csv(reports_root / REPORT_NAMES[5], readiness_rows)

    command_03_after = command_03_snapshot(root)
    if command_03_before != command_03_after:
        raise FamilyCImplementationPreregImmutabilityError(
            "Family C Command 03 changed during implementation preregistration"
        )

    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": started_at,
        "family_version": FAMILY_VERSION,
        "family_code": FAMILY_CODE,
        "freeze_gate": {"status": frozen["status"], "checks": frozen["checks"]},
        "frozen_hashes": {
            "family_c_config_hash": EXPECTED_FAMILY_C_CONFIG_HASH,
            "family_c_success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
            "brk_c_001_result_hash": EXPECTED_C001_RESULT_HASH,
            "family_c_development_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
            "family_c_c001_attribution_hash": EXPECTED_ATTRIBUTION_HASH,
        },
        "configuration": config,
        "parameters": parameters,
        "success_criteria": criteria,
        "preregistration": prereg,
        "registry": registry,
        "signal_set": {
            key: value
            for key, value in signal_identity.items()
            if key != "signal_set_body"
        },
        "pilots": {
            "synthetic": {
                "row_count": len(synthetic),
                "expected_order": [
                    "DELTA",
                    "BRAVO",
                    "ALPHA",
                    "CHARLIE",
                    "ECHO",
                ],
                "status": "PASS",
                "performance_calculated": False,
            },
            "real_dates": real_date_findings,
        },
        "governance": {
            "version": "RESEARCH_EXPERIMENT_GOVERNANCE_V2",
            "passed": len(governance),
            "required": 14,
            "status": "PASS" if governance_pass else "FAIL",
        },
        "classifications": {
            "C1_IMP_001_ARCHITECTURE_RESULT": architecture_result,
            "ROADMAP_STATUS": ROADMAP_STATUS,
        },
        "readiness_checks": readiness_checks,
        "performance": {
            "performance_run": False,
            "calculated_metrics": [],
            "C1_IMP_001_FUTURE_RESULT": None,
        },
        "governance_prohibitions": {
            "second_ranking_tested": False,
            "compression_threshold_changed": False,
            "capacity_changed": False,
            "holding_period_changed": False,
            "position_sizing_changed": False,
            "stop_added": False,
            "target_added": False,
            "volume_added": False,
            "gap_filter_added": False,
            "breakout_threshold_added": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "family_d_started": False,
        },
        "immutability": {
            "command_03_snapshot_before": command_03_before["snapshot_hash"],
            "command_03_snapshot_after": command_03_after["snapshot_hash"],
            "command_03_unchanged": True,
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
            "root": research_root.relative_to(root).as_posix(),
            "artifact_hashes": {},
        },
        "known_limitations": (
            "STRUCTURAL_ARCHITECTURE_ONLY_NO_C1_IMP_001_PERFORMANCE",
            "REAL_DATE_PILOTS_COMPARE_ORDER_AND_SLOT_SELECTION_ONLY",
            "PILOTS_DO_NOT_SIMULATE_AFFORDABILITY_OR_PORTFOLIO_PATH",
            "DEVELOPMENT_PARTITION_ONLY_VALIDATION_NOT_ACCESSED",
            "HYPOTHESIS_IS_PREREGISTERED_NOT_PROVEN",
        ),
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    summary_path = reports_root / REPORT_NAMES[0]
    write_json(summary_path, summary)
    artifact_paths = [
        *(
            path
            for path in research_root.rglob("*")
            if path.is_file() and path != manifest_path
        ),
        *(reports_root / name for name in REPORT_NAMES[1:]),
    ]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(artifact_paths))
    }
    summary["storage"]["artifact_hashes"] = artifact_hashes
    write_json(summary_path, summary)
    manifest_body = {
        "command_version": COMMAND_VERSION,
        "family_version": FAMILY_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "implementation_research_config_hash": config[
            "implementation_research_config_hash"
        ],
        "parameter_hash": parameters["parameter_hash"],
        "preregistration_hash": prereg["preregistration_hash"],
        "implementation_success_criteria_hash": criteria[
            "implementation_success_criteria_hash"
        ],
        "c001_signal_set_hash": signal_identity["c001_signal_set_hash"],
        "artifact_hashes": artifact_hashes,
        "summary_hash": file_sha256(summary_path),
        "command_03_snapshot_hash": command_03_after["snapshot_hash"],
        "performance_run": False,
        "validation_accessed": False,
    }
    manifest = {
        **manifest_body,
        "implementation_research_manifest_hash": canonical_hash(manifest_body),
    }
    write_json(manifest_path, manifest)
    return summary


def finalize_family_c_c001_implementation_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    manifest_path = output_root(root) / "manifests/implementation_research_manifest_v1.json"
    summary = _read_json(summary_path)
    passed = all(
        "passed" in value.lower()
        for value in (backend_targeted_tests, backend_full_tests, frontend_build)
    )
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed,
    }
    write_json(summary_path, summary)
    manifest = _read_json(manifest_path)
    manifest["summary_hash"] = file_sha256(summary_path)
    field = "implementation_research_manifest_hash"
    manifest[field] = canonical_hash(_without_hash(manifest, field))
    write_json(manifest_path, manifest)
    return summary


__all__ = [
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXPERIMENT_ID",
    "EXPERIMENT_NAME",
    "EXPECTED_ATTRIBUTION_HASH",
    "GOVERNANCE_ITEMS",
    "ORIGINAL_RANKING",
    "REFERENCE_EXPERIMENT_ID",
    "REPORT_NAMES",
    "ROADMAP_STATUS",
    "TREATMENT_RANKING",
    "build_c001_signal_set",
    "build_family_c_c001_implementation_research",
    "finalize_family_c_c001_implementation_review",
    "governance_rows",
    "implementation_parameters",
    "implementation_research_config",
    "implementation_success_criteria",
    "preregistration",
    "rank_compression_priority",
    "real_date_structural_pilots",
    "synthetic_ranking_pilot",
    "verify_frozen_inputs",
    "verify_signal_set_identity",
]
