from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.backtesting.costs.cost_models import canonical_hash, json_ready
from app.research.strategy.family_a_development_backtest import (
    IDEALIZED_MODE,
    RebalanceSchedule,
    load_rebalance_schedules,
    simulate_executable,
)
from app.research.strategy.family_a_momentum import (
    _load_adjusted_bars,
    _load_aliases,
    _load_sessions,
    decimal,
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_b_attribution_audit import (
    EXPECTED_ATTRIBUTION_AUDIT_HASH,
)
from app.research.strategy.family_b_development_evaluation import (
    CONTROL_ROLE,
    EXECUTABLE_MODE,
    EXPECTED_DEVELOPMENT_REGISTRY_HASH,
    EXPECTED_RESULT_HASHES,
    _accounting_integrity,
    _qualifying_statistics,
    _write_simulation_ledgers,
    analyze_simulation,
    cash_decomposition,
    control_reproduction_check,
    enriched_yearly,
    evaluate_treatment_criteria,
    idealized_executable_comparison,
    simulate_idealized_500k,
    treatment_schedules,
    verify_command_01_freeze,
)
from app.research.strategy.family_b_history_remediation import (
    AVAILABILITY_REASONS,
    EXPECTED_ADJUSTED_EXTENSION_HASH,
    EXPECTED_FAMILY_B_SMA_READINESS_HASH,
    EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
    EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
    EXPECTED_RAW_EXTENSION_HASH,
    _aggregate_hash,
    _dated_files,
    _recompute_hash,
    adjusted_extension_root,
    daily_extension_root,
    daily_raw_extension,
    verify_frozen_inputs as verify_command_04_upstreams,
)
from app.research.strategy.family_b_relative_absolute_momentum import (
    CAPITAL_INR,
    CONTROL_ID,
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    EXPECTED_EXPERIMENT_HASHES,
    EXPECTED_FAMILY_B_CONFIG_HASH,
    EXPECTED_SUCCESS_CRITERIA_HASH,
    MINIMUM_HOLDINGS,
    SMA_SESSIONS,
    b002_eligibility,
)


COMMAND = "Step 03.02 / Command 05"
COMMAND_VERSION = "FAMILY_B_B002_CLEAN_DEVELOPMENT_REEVALUATION_V1"
COMMAND_PROFILE = "SMA200_REMEDIATED_DEVELOPMENT_EVALUATION_V1"
CLEAN_RECORD_ID = "MOM-B-002-CLEAN-REEVALUATION"

EXPECTED_CLEAN_CONTROL_RESULT_HASH = (
    "b0cac6bbdd31e4a2c6534fd7cc4b6eba9981693506444a20164df1246b0259ae"
)
EXPECTED_CLEAN_B002_RESULT_HASH = (
    "48f70f4101175574968f2035afdb1534752a914889198d236cbd782bfe9dc6c2"
)
EXPECTED_B002_CLEAN_REEVALUATION_HASH = (
    "a6a287f60c0a995d165279a5ddb7c666eefcb174b7a6e1c3788a5634c3834987"
)
EXPECTED_CLEAN_RUN_MANIFEST_HASH = (
    "9b674d5d6aab2b8ed03bdf5a2590a14f1925ae7f4c4c04a5c09f168b21d8bc6d"
)

REPORT_NAMES = (
    "family_b_b002_clean_v1_summary.json",
    "family_b_b002_clean_v1_control.csv",
    "family_b_b002_clean_v1_b002.csv",
    "family_b_b002_clean_v1_yearly.csv",
    "family_b_b002_clean_v1_criteria.csv",
    "family_b_b002_clean_v1_filter_impact.csv",
    "family_b_b002_clean_v1_original_vs_clean.csv",
    "family_b_b002_clean_v1_cash.csv",
    "family_b_b002_clean_v1_attribution.csv",
)

FILTER_CATEGORIES = (
    "TRUE_BELOW_SMA200",
    "GENUINE_SMA_UNAVAILABLE_RECENT_LISTING",
    "CORPORATE_ACTION_UNAVAILABLE",
    "OTHER_LEGITIMATE_UNAVAILABLE",
)


class B002ReevaluationFreezeMismatch(RuntimeError):
    pass


class B002CleanReevaluationImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def output_root(root: Path) -> Path:
    return root / "data/research/strategy_families/family_b/v1/clean_reevaluation"


def _freeze_fail(reason: str, error: Exception | None = None) -> None:
    message = f"B002_REEVALUATION_FREEZE_MISMATCH: {reason}"
    if error is None:
        raise B002ReevaluationFreezeMismatch(message)
    raise B002ReevaluationFreezeMismatch(message) from error


def verify_freeze_gate(root: Path) -> dict[str, Any]:
    try:
        command_01 = verify_command_01_freeze(root)
        command_04_upstreams = verify_command_04_upstreams(root)
        history_summary = _read_json(
            root / "data/reports/family_b_history_remediation_v1_summary.json"
        )
        history_config = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/history_remediation/"
            "raw_manifest/history_remediation_config_v1.json"
        )
        history_readiness = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/history_remediation/"
            "manifests/family_b_sma_readiness_v1.json"
        )
        history_manifest = _read_json(
            root
            / "data/research/strategy_families/family_b/v1/history_remediation/"
            "manifests/history_remediation_manifest_v1.json"
        )
        command_02_results = {
            CONTROL_ID: _read_json(
                root
                / "data/research/strategy_families/family_b/v1/development_evaluation/"
                "control/development_result_v1.json"
            ),
            "MOM-B-001": _read_json(
                root
                / "data/research/strategy_families/family_b/v1/development_evaluation/"
                "mom_b_001/development_result_v1.json"
            ),
            "MOM-B-002": _read_json(
                root
                / "data/research/strategy_families/family_b/v1/development_evaluation/"
                "mom_b_002/development_result_v1.json"
            ),
        }
    except Exception as error:  # noqa: BLE001 - normalized command gate
        _freeze_fail("required frozen inputs are missing or unreadable", error)

    registry_b002 = next(
        row
        for row in command_01["registry"]["experiments"]
        if row["experiment_id"] == "MOM-B-002"
    )
    raw_files = [
        path
        for path in sorted(daily_raw_extension(root).glob("*/*/*"))
        if path.is_file() and path.suffix != ".missing"
    ]
    adjusted_files = _dated_files(
        adjusted_extension_root(root), "nse_adjusted_daily_*.csv", end=date(2021, 9, 6)
    )
    artifact_mismatches = [
        relative_path
        for relative_path, expected_hash in history_manifest.get("artifact_hashes", {}).items()
        if not (root / relative_path).exists()
        or file_sha256(root / relative_path) != expected_hash
    ]
    command_02_hashes = {
        record_id: result.get("development_result_hash")
        for record_id, result in command_02_results.items()
    }
    command_02_recomputed = all(
        _recompute_hash(result, "development_result_hash") == EXPECTED_RESULT_HASHES[record_id]
        for record_id, result in command_02_results.items()
    )
    checks = {
        "MOM_B_002_parameter_hash": registry_b002.get("parameter_hash")
        == EXPECTED_EXPERIMENT_HASHES["MOM-B-002"]["parameter_hash"],
        "MOM_B_002_preregistration_hash": registry_b002.get("preregistration_hash")
        == EXPECTED_EXPERIMENT_HASHES["MOM-B-002"]["preregistration_hash"],
        "family_b_config_hash": command_01["config"].get("family_b_config_hash")
        == EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": command_01["criteria"].get("success_criteria_hash")
        == EXPECTED_SUCCESS_CRITERIA_HASH,
        "attribution_audit_hash": command_04_upstreams["snapshot"].get(
            "attribution_audit_hash"
        )
        == EXPECTED_ATTRIBUTION_AUDIT_HASH,
        "history_config_hash": history_config.get("history_remediation_config_hash")
        == EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH
        and _recompute_hash(history_config, "history_remediation_config_hash")
        == EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
        "raw_extension_hash": _aggregate_hash(raw_files, daily_extension_root(root))
        == EXPECTED_RAW_EXTENSION_HASH,
        "adjusted_extension_hash": _aggregate_hash(adjusted_files, root)
        == EXPECTED_ADJUSTED_EXTENSION_HASH,
        "SMA_readiness_hash": history_readiness.get("family_b_sma_readiness_hash")
        == EXPECTED_FAMILY_B_SMA_READINESS_HASH
        and _recompute_hash(history_readiness, "family_b_sma_readiness_hash")
        == EXPECTED_FAMILY_B_SMA_READINESS_HASH,
        "remediation_manifest_hash": history_manifest.get(
            "history_remediation_manifest_hash"
        )
        == EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH
        and _recompute_hash(history_manifest, "history_remediation_manifest_hash")
        == EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
        "remediation_artifacts": not artifact_mismatches,
        "remediation_ready": history_summary.get("verification", {}).get(
            "ready_for_review"
        )
        is True
        and history_summary.get("decisions", {}).get(
            "FAMILY_B_B002_REEVALUATION_READINESS"
        )
        == "YES",
        "command_02_results": command_02_hashes == EXPECTED_RESULT_HASHES
        and command_02_recomputed,
        "command_02_registry": _read_json(
            root
            / "data/research/strategy_families/family_b/v1/development_evaluation/"
            "comparison/development_registry_v1.json"
        ).get("development_registry_hash")
        == EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        "development_window": DEVELOPMENT_START == date(2022, 1, 1)
        and DEVELOPMENT_END == date(2024, 12, 31),
        "validation_not_accessed": history_summary.get("governance", {}).get(
            "validation_accessed"
        )
        is False,
    }
    if not all(checks.values()):
        _freeze_fail(str({key: value for key, value in checks.items() if not value}))
    semantic = {
        "MOM_B_002_parameter_hash": EXPECTED_EXPERIMENT_HASHES["MOM-B-002"][
            "parameter_hash"
        ],
        "MOM_B_002_preregistration_hash": EXPECTED_EXPERIMENT_HASHES["MOM-B-002"][
            "preregistration_hash"
        ],
        "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "attribution_audit_hash": EXPECTED_ATTRIBUTION_AUDIT_HASH,
        "history_remediation_config_hash": EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
        "raw_extension_hash": EXPECTED_RAW_EXTENSION_HASH,
        "adjusted_extension_hash": EXPECTED_ADJUSTED_EXTENSION_HASH,
        "family_b_sma_readiness_hash": EXPECTED_FAMILY_B_SMA_READINESS_HASH,
        "history_remediation_manifest_hash": EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
        "command_02_result_hashes": EXPECTED_RESULT_HASHES,
        "command_02_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        "history_artifact_hashes": history_manifest["artifact_hashes"],
        "development_start": DEVELOPMENT_START.isoformat(),
        "development_end": DEVELOPMENT_END.isoformat(),
        "validation_accessed": False,
    }
    return {
        "status": "VERIFIED",
        "checks": checks,
        "command_01": command_01,
        "history_summary": history_summary,
        "command_02_results": command_02_results,
        "snapshot": {**semantic, "snapshot_hash": canonical_hash(semantic)},
    }


def _optional_bool(value: str | None) -> bool | None:
    if value == "True":
        return True
    if value == "False":
        return False
    return None


def clean_b002_inputs(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    frozen_rows = read_csv(
        root
        / "data/research/strategy_families/family_b/v1/signals/"
        "family_b_signal_inputs_v1.csv"
    )
    readiness_rows = read_csv(
        root / "data/reports/family_b_history_remediation_v1_sma_before_after.csv"
    )
    readiness = {
        (row["formation_date"], row["symbol"]): row for row in readiness_rows
    }
    if len(frozen_rows) != 5490 or len(readiness) != len(frozen_rows):
        _freeze_fail(
            f"clean input row mismatch: frozen={len(frozen_rows)} readiness={len(readiness)}"
        )
    frozen_calendar = read_csv(
        root
        / "data/research/strategy_families/family_b/v1/rebalance_calendar/"
        "family_b_rebalance_calendar_v1.csv"
    )
    top_by_date = {
        row["decision_date"]: int(row["top_decile_size"]) for row in frozen_calendar
    }
    clean_rows: list[dict[str, Any]] = []
    for source in frozen_rows:
        key = (source["decision_date"], source["symbol"])
        if key not in readiness:
            _freeze_fail(f"missing remediation readiness row: {key}")
        remediated = readiness[key]
        rank = int(source["relative_rank"]) if source.get("relative_rank") else None
        top_decile = rank is not None and rank <= top_by_date[source["decision_date"]]
        close = decimal(source["close"]) if source.get("close") else None
        available = remediated["new_SMA200_available"] == "True"
        observation_count = int(remediated["new_SMA_observation_count_used"] or 0)
        sma = decimal(remediated["new_SMA200"]) if available else None
        if available != (observation_count == SMA_SESSIONS and sma is not None):
            _freeze_fail(f"non-exact remediated SMA row: {key}")
        status = b002_eligibility(top_decile, close, sma, observation_count)
        flags = set(json.loads(source.get("data_quality_flags") or "[]"))
        flags.discard("SMA200_UNAVAILABLE")
        if not available:
            flags.add("SMA200_UNAVAILABLE_GENUINE_OR_STRUCTURAL_HISTORY")
            flags.add(remediated["availability_reason"])
        clean_rows.append(
            {
                "decision_date": source["decision_date"],
                "symbol": source["symbol"],
                "6m_return": decimal(source["6m_return"])
                if source.get("6m_return")
                else None,
                "relative_rank": rank,
                "relative_percentile": decimal(source["relative_percentile"])
                if source.get("relative_percentile")
                else None,
                "sma200": sma,
                "close": close,
                "absolute_6m_positive": _optional_bool(
                    source.get("absolute_6m_positive")
                ),
                "above_sma200": close > sma
                if close is not None and sma is not None
                else None,
                "B001_eligible": _optional_bool(source.get("B001_eligible")),
                "B002_eligible": True
                if status == "ELIGIBLE"
                else None
                if status == "UNAVAILABLE"
                else False,
                "data_quality_flags": tuple(sorted(flags)) or ("NONE",),
                "membership_confidence": source["membership_confidence"],
                "frozen_formation_member": remediated["frozen_formation_member"]
                == "True",
                "frozen_B002_top_decile_candidate": remediated[
                    "frozen_B002_top_decile_candidate"
                ]
                == "True",
                "SMA_availability_reason": remediated["availability_reason"],
                "SMA_remediation_outcome": remediated["remediation_outcome"],
                "SMA_observation_count": observation_count,
                "SMA_window_start": remediated["new_SMA_window_start"] or None,
                "SMA_window_end": remediated["new_SMA_window_end"] or None,
                "no_future_observations": remediated["no_future_observations"]
                == "True",
                "history_data_version": "DAILY_HISTORY_PREHISTORY_V2",
                "relative_input_source": (
                    "FROZEN_126_SESSION_VALUE_WITHIN_IMMUTABLE_V2_OVERLAP"
                ),
                "prehistory_performance_observation": False,
            }
        )
    by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in clean_rows:
        by_date[str(row["decision_date"])].append(row)
    clean_calendar: list[dict[str, Any]] = []
    for source in frozen_calendar:
        decision_date_text = source["decision_date"]
        pass_count = sum(
            row["B002_eligible"] is True for row in by_date[decision_date_text]
        )
        clean_calendar.append(
            {
                **source,
                "eligible_universe_size": int(source["eligible_universe_size"]),
                "top_decile_size": int(source["top_decile_size"]),
                "B001_pass_count": int(source["B001_pass_count"]),
                "B002_pass_count": pass_count,
                "B002_breadth_status": (
                    "PORTFOLIO_FORMATION_ALLOWED"
                    if pass_count >= MINIMUM_HOLDINGS
                    else "INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH"
                ),
                "future_returns_accessed": False,
            }
        )
    candidates = [row for row in clean_rows if row["frozen_B002_top_decile_candidate"]]
    if len(candidates) != 302:
        _freeze_fail(f"frozen B002 candidate count changed: {len(candidates)}")
    if any(row["SMA_availability_reason"] == "DATASET_TRUNCATION" for row in candidates):
        _freeze_fail("dataset-truncation leakage remains in clean candidates")
    return clean_rows, clean_calendar


def _simulation_accounting(
    simulation: Mapping[str, Any],
    schedules: Sequence[RebalanceSchedule],
    clean_rows: Sequence[Mapping[str, Any]],
    freeze: Mapping[str, Any],
) -> dict[str, bool]:
    base = _accounting_integrity(
        simulation, schedules, freeze["command_01"]["command_01_summary"]
    )
    candidate_rows = [
        row for row in clean_rows if row["frozen_B002_top_decile_candidate"]
    ]
    unavailable = [row for row in candidate_rows if row["sma200"] is None]
    return {
        "cash_reconciliation": base["cash_reconciliation"],
        "equity_reconciliation": base["equity_reconciliation"],
        "execution_chronology": base["execution_chronology"],
        "point_in_time_universe": all(
            row["frozen_formation_member"] for row in clean_rows
        ),
        "no_lookahead": all(row["no_future_observations"] for row in clean_rows),
        "corporate_action_safety": all(
            row["SMA_availability_reason"] in AVAILABILITY_REASONS
            for row in clean_rows
        ),
        "clean_remediation_lineage": freeze["status"] == "VERIFIED",
        "exact_SMA200_only": all(
            (row["sma200"] is None and row["SMA_observation_count"] == 0)
            or (row["sma200"] is not None and row["SMA_observation_count"] == SMA_SESSIONS)
            for row in clean_rows
        ),
        "no_silent_missing_SMA_substitution": all(
            row["B002_eligible"] is None for row in unavailable
        ),
        "prehistory_not_performance": all(
            row["prehistory_performance_observation"] is False for row in clean_rows
        )
        and all(
            DEVELOPMENT_START <= date.fromisoformat(str(row["date"])) <= DEVELOPMENT_END
            for row in simulation["daily"]
        ),
    }


def _mean(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def filter_attribution(
    clean_rows: Sequence[Mapping[str, Any]],
    calendar_rows: Sequence[Mapping[str, Any]],
    control_simulation: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    calendar = {str(row["decision_date"]): row for row in calendar_rows}
    control_holdings = {
        (str(row["execution_date"]), str(row["symbol"])): row
        for row in control_simulation["holdings"]
    }
    control_positions = {
        (str(row["period_start"]), str(row["symbol"])): row
        for row in control_simulation["position_returns"]
    }
    candidates = [
        row for row in clean_rows if row["frozen_B002_top_decile_candidate"]
    ]
    unavailable_by_date = Counter(
        str(row["decision_date"]) for row in candidates if row["sma200"] is None
    )
    removals: list[dict[str, Any]] = []
    for row in candidates:
        if row["B002_eligible"] is True:
            continue
        if row["above_sma200"] is False:
            category = "TRUE_BELOW_SMA200"
        elif row["SMA_availability_reason"] == "GENUINE_RECENT_LISTING":
            category = "GENUINE_SMA_UNAVAILABLE_RECENT_LISTING"
        elif row["SMA_availability_reason"] == "CORPORATE_ACTION_EXCLUDED":
            category = "CORPORATE_ACTION_UNAVAILABLE"
        else:
            category = "OTHER_LEGITIMATE_UNAVAILABLE"
        formation = str(row["decision_date"])
        schedule = calendar[formation]
        execution = str(schedule["execution_date"])
        holding = control_holdings.get((execution, str(row["symbol"])))
        position = control_positions.get((execution, str(row["symbol"])))
        contribution = Decimal("0")
        if holding is not None and position is not None:
            contribution = decimal(holding["quantity"]) * (
                decimal(position["end_price"]) - decimal(position["start_price"])
            )
        candidate_count = int(schedule["top_decile_size"])
        qualifying_count = int(schedule["B002_pass_count"])
        sufficient = qualifying_count >= MINIMUM_HOLDINGS
        control_equal_weight = Decimal("100") / Decimal(candidate_count)
        clean_equal_weight = (
            Decimal("100") / Decimal(qualifying_count)
            if sufficient and qualifying_count
            else Decimal("0")
        )
        removals.append(
            {
                "formation_date": formation,
                "execution_date": execution,
                "symbol": row["symbol"],
                "relative_rank": row["relative_rank"],
                "formation_close": row["close"],
                "SMA200": row["sma200"],
                "removal_category": category,
                "SMA_availability_reason": row["SMA_availability_reason"],
                "control_inclusion": holding is not None,
                "control_actual_weight_pct": decimal(holding["actual_weight_pct"])
                if holding is not None
                else Decimal("0"),
                "control_subsequent_realized_contribution_if_held_rupees": contribution,
                "control_position_period_return_pct": decimal(
                    position["position_return_pct"]
                )
                if position is not None
                else None,
                "candidate_equal_weight_pct": control_equal_weight,
                "clean_qualifying_count": qualifying_count,
                "clean_equal_weight_per_retained_name_pct": clean_equal_weight,
                "portfolio_weight_redistribution_effect_pp": clean_equal_weight
                - control_equal_weight,
                "clean_minimum_holdings_satisfied": sufficient,
                "same_date_legitimate_unavailable_count": unavailable_by_date[formation],
                "isolated_true_filter_effect_interpretable": category
                == "TRUE_BELOW_SMA200"
                and holding is not None
                and unavailable_by_date[formation] == 0,
                "descriptive_only": True,
            }
        )
    counts = Counter(row["removal_category"] for row in removals)
    true_rows = [row for row in removals if row["removal_category"] == "TRUE_BELOW_SMA200"]
    legitimate_unavailable = len(removals) - len(true_rows)
    summary = {
        "top_decile_candidate_count": len(candidates),
        "qualifying_count": len(candidates) - len(removals),
        "total_removal_count": len(removals),
        "true_below_SMA_removal_count": len(true_rows),
        "SMA_unavailable_count": legitimate_unavailable,
        "category_counts": {category: counts[category] for category in FILTER_CATEGORIES},
        "true_below_SMA_removal_rate": Decimal(len(true_rows))
        / Decimal(len(candidates)),
        "legitimate_unavailable_removal_rate": Decimal(legitimate_unavailable)
        / Decimal(len(candidates)),
        "dataset_truncation_leakage_count": sum(
            row["SMA_availability_reason"] == "DATASET_TRUNCATION"
            for row in removals
        ),
        "true_filter_control_inclusion_count": sum(
            row["control_inclusion"] for row in true_rows
        ),
        "true_filter_isolated_interpretable_count": sum(
            row["isolated_true_filter_effect_interpretable"] for row in true_rows
        ),
        "true_filter_control_realized_contribution_rupees": sum(
            (
                decimal(row["control_subsequent_realized_contribution_if_held_rupees"])
                for row in true_rows
            ),
            Decimal("0"),
        ),
    }
    return removals, summary


def classify_clean_filter_evidence(
    filter_rows: Sequence[Mapping[str, Any]], accounting_clean: bool
) -> tuple[str, str, dict[str, Any]]:
    true_rows = [
        row for row in filter_rows if row["removal_category"] == "TRUE_BELOW_SMA200"
    ]
    isolated = [
        row for row in true_rows if row["isolated_true_filter_effect_interpretable"]
    ]
    if not accounting_clean:
        evidence = "INCONCLUSIVE"
        attribution = "INCONCLUSIVE"
    elif not true_rows:
        evidence = "NOT_DEMONSTRATED"
        attribution = "EVIDENCE_TOO_SPARSE"
    elif isolated and any(
        decimal(row["portfolio_weight_redistribution_effect_pp"]) != 0
        for row in isolated
    ):
        evidence = "MEANINGFUL"
        contribution = sum(
            (
                decimal(row["control_subsequent_realized_contribution_if_held_rupees"])
                for row in isolated
            ),
            Decimal("0"),
        )
        attribution = (
            "TREND_FILTER_CONTRIBUTES_POSITIVELY"
            if contribution < 0
            else "TREND_FILTER_DETRIMENTAL"
            if contribution > 0
            else "TREND_FILTER_NEUTRAL"
        )
    else:
        evidence = "WEAK"
        attribution = "EVIDENCE_TOO_SPARSE"
    details = {
        "true_removal_count": len(true_rows),
        "isolated_interpretable_count": len(isolated),
        "isolated_control_contribution_rupees": sum(
            (
                decimal(row["control_subsequent_realized_contribution_if_held_rupees"])
                for row in isolated
            ),
            Decimal("0"),
        ),
        "classification_method": (
            "ACTUAL_BELOW_SMA_EXCLUSIONS_REQUIRE_CONTROL_INCLUSION_NONZERO_WEIGHT_"
            "REDISTRIBUTION_AND_CLEAN_ACCOUNTING; CONTRIBUTION_SIGN_IS_DESCRIPTIVE"
        ),
        "new_numeric_threshold_introduced": False,
    }
    return evidence, attribution, details


def _year(rows: Sequence[Mapping[str, Any]], year: int) -> Mapping[str, Any]:
    return next(row for row in rows if int(row["year"]) == year)


def _compounded_2023_2024(rows: Sequence[Mapping[str, Any]]) -> Decimal:
    first = decimal(_year(rows, 2023)["net_return_pct"]) / Decimal("100")
    second = decimal(_year(rows, 2024)["net_return_pct"]) / Decimal("100")
    return ((Decimal("1") + first) * (Decimal("1") + second) - Decimal("1")) * Decimal(
        "100"
    )


def original_clean_comparison(
    original: Mapping[str, Any],
    clean_performance: Mapping[str, Any],
    clean_yearly: Sequence[Mapping[str, Any]],
    control_yearly: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    original_performance = original["performance"]
    original_yearly = original["yearly"]
    original_2022 = decimal(_year(original_yearly, 2022)["net_return_pct"])
    clean_2022 = decimal(_year(clean_yearly, 2022)["net_return_pct"])
    control_2022 = decimal(_year(control_yearly, 2022)["net_return_pct"])
    clean_2023 = decimal(_year(clean_yearly, 2023)["net_return_pct"])
    control_2023 = decimal(_year(control_yearly, 2023)["net_return_pct"])
    clean_2024 = decimal(_year(clean_yearly, 2024)["net_return_pct"])
    control_2024 = decimal(_year(control_yearly, 2024)["net_return_pct"])
    clean_2023_2024 = _compounded_2023_2024(clean_yearly)
    control_2023_2024 = _compounded_2023_2024(control_yearly)
    original_advantage = original_2022 - control_2022
    clean_advantage = clean_2022 - control_2022
    advantage_finding = (
        "DISAPPEARED"
        if clean_advantage <= 0
        else "REDUCED_BUT_REMAINS"
        if clean_advantage < original_advantage
        else "UNCHANGED_OR_INCREASED"
    )
    return {
        "original_B002_net_ending_equity": decimal(
            original_performance["net_ending_equity"]
        ),
        "clean_B002_net_ending_equity": decimal(clean_performance["net_ending_equity"]),
        "original_B002_net_return_pct": decimal(
            original_performance["net_total_return_pct"]
        ),
        "clean_B002_net_return_pct": decimal(clean_performance["net_total_return_pct"]),
        "original_B002_net_CAGR_pct": decimal(original_performance["net_cagr_pct"]),
        "clean_B002_net_CAGR_pct": decimal(clean_performance["net_cagr_pct"]),
        "clean_minus_original_CAGR_pp": decimal(clean_performance["net_cagr_pct"])
        - decimal(original_performance["net_cagr_pct"]),
        "original_B002_max_drawdown_pct": decimal(
            original_performance["net_max_drawdown_pct"]
        ),
        "clean_B002_max_drawdown_pct": decimal(
            clean_performance["net_max_drawdown_pct"]
        ),
        "original_B002_2022_return_pct": original_2022,
        "clean_B002_2022_return_pct": clean_2022,
        "clean_minus_original_2022_pp": clean_2022 - original_2022,
        "control_2022_return_pct": control_2022,
        "original_2022_advantage_vs_control_pp": original_advantage,
        "clean_2022_advantage_vs_control_pp": clean_advantage,
        "previous_2022_advantage_finding": advantage_finding,
        "clean_B002_2023_return_pct": clean_2023,
        "control_2023_return_pct": control_2023,
        "clean_minus_control_2023_pp": clean_2023 - control_2023,
        "clean_B002_2024_return_pct": clean_2024,
        "control_2024_return_pct": control_2024,
        "clean_minus_control_2024_pp": clean_2024 - control_2024,
        "original_2023_2024_compounded_return_pct": _compounded_2023_2024(
            original_yearly
        ),
        "clean_2023_2024_compounded_return_pct": clean_2023_2024,
        "control_2023_2024_compounded_return_pct": control_2023_2024,
        "clean_minus_control_2023_2024_pp": clean_2023_2024
        - control_2023_2024,
        "diagnostic_only": True,
        "original_result_overwritten": False,
    }


def _immutable_document(
    path: Path,
    body: Mapping[str, Any],
    hash_field: str,
    expected_hash: str,
) -> dict[str, Any]:
    observed_hash = canonical_hash(body)
    document = {**body, hash_field: observed_hash}
    if expected_hash and observed_hash != expected_hash:
        raise B002CleanReevaluationImmutabilityError(
            f"{hash_field} mismatch: {observed_hash}"
        )
    if path.exists():
        existing = _read_json(path)
        if existing != json_ready(document):
            raise B002CleanReevaluationImmutabilityError(
                f"Existing immutable document changed: {path}"
            )
        return existing
    write_json(path, document)
    return json_ready(document)


def build_b002_clean_reevaluation(root: Path) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = utc_now()
    freeze_before = verify_freeze_gate(root)
    clean_rows, calendar_rows = clean_b002_inputs(root)
    symbols = {str(row["symbol"]) for row in clean_rows}
    bars = _load_adjusted_bars(root, symbols, _load_aliases(root))
    sessions = [
        session
        for session in _load_sessions(root)
        if DEVELOPMENT_START <= session <= DEVELOPMENT_END
    ]
    if not sessions or sessions[-1] != DEVELOPMENT_END:
        _freeze_fail("development-only price session boundary failed")

    schedules = {
        CONTROL_ID: load_rebalance_schedules(root)["MOM-A-002"],
        CLEAN_RECORD_ID: treatment_schedules(clean_rows, calendar_rows, "MOM-B-002"),
    }
    simulations: dict[str, dict[str, dict[str, Any]]] = {}
    for record_id in (CONTROL_ID, CLEAN_RECORD_ID):
        idealized = simulate_idealized_500k(
            record_id, schedules[record_id], sessions, bars
        )
        executable = simulate_executable(
            record_id,
            schedules[record_id],
            sessions,
            bars,
            starting_capital=CAPITAL_INR,
            mode=EXECUTABLE_MODE,
        )
        if record_id == CLEAN_RECORD_ID:
            for schedule, row in zip(
                schedules[record_id], executable["rebalances"], strict=True
            ):
                if not schedule.sufficient_universe:
                    if int(row["actual_holdings"]) != 0:
                        raise B002CleanReevaluationImmutabilityError(
                            "Clean B002 retained holdings during insufficient breadth"
                        )
                    row["status"] = "INSUFFICIENT_ABSOLUTE_MOMENTUM_BREADTH_CASH"
        simulations[record_id] = {
            IDEALIZED_MODE: idealized,
            EXECUTABLE_MODE: executable,
        }

    analyses = {
        record_id: {
            mode: analyze_simulation(simulation) for mode, simulation in modes.items()
        }
        for record_id, modes in simulations.items()
    }
    yearly = {
        record_id: {
            mode: enriched_yearly(simulations[record_id][mode], analyses[record_id][mode])
            for mode in (IDEALIZED_MODE, EXECUTABLE_MODE)
        }
        for record_id in (CONTROL_ID, CLEAN_RECORD_ID)
    }
    control_performance = analyses[CONTROL_ID][EXECUTABLE_MODE]["summary"]
    clean_performance = analyses[CLEAN_RECORD_ID][EXECUTABLE_MODE]["summary"]
    control_reproduction = control_reproduction_check(root, control_performance)
    if not control_reproduction["all_metrics_exact"]:
        _freeze_fail("CONTROL-B-000 reproduction was not exact")

    accounting = {
        record_id: _simulation_accounting(
            simulations[record_id][EXECUTABLE_MODE],
            schedules[record_id],
            clean_rows,
            freeze_before,
        )
        for record_id in (CONTROL_ID, CLEAN_RECORD_ID)
    }
    filter_rows, filter_summary = filter_attribution(
        clean_rows, calendar_rows, simulations[CONTROL_ID][EXECUTABLE_MODE]
    )
    accounting_clean = all(accounting[CLEAN_RECORD_ID].values())
    evidence, attribution, attribution_details = classify_clean_filter_evidence(
        filter_rows, accounting_clean
    )
    criteria = evaluate_treatment_criteria(
        "MOM-B-002",
        clean_performance,
        control_performance,
        yearly[CLEAN_RECORD_ID][EXECUTABLE_MODE],
        yearly[CONTROL_ID][EXECUTABLE_MODE],
        calendar_rows,
        accounting[CLEAN_RECORD_ID],
    )
    clean_result = criteria["development_result"]
    comparison = original_clean_comparison(
        freeze_before["command_02_results"]["MOM-B-002"],
        clean_performance,
        yearly[CLEAN_RECORD_ID][EXECUTABLE_MODE],
        yearly[CONTROL_ID][EXECUTABLE_MODE],
    )
    clean_cash = cash_decomposition(simulations[CLEAN_RECORD_ID][EXECUTABLE_MODE])
    control_cash = cash_decomposition(simulations[CONTROL_ID][EXECUTABLE_MODE])
    qualifying = _qualifying_statistics(calendar_rows, "MOM-B-002")
    implementation = {
        record_id: idealized_executable_comparison(
            analyses[record_id][IDEALIZED_MODE]["summary"],
            analyses[record_id][EXECUTABLE_MODE]["summary"],
        )
        for record_id in (CONTROL_ID, CLEAN_RECORD_ID)
    }
    no_history_artifact = filter_summary["dataset_truncation_leakage_count"] == 0
    validation_ready = (
        clean_result in {"SUPPORTED", "STRONGLY_SUPPORTED"}
        and accounting_clean
        and no_history_artifact
        and evidence == "MEANINGFUL"
    )
    validation_status = (
        "READY"
        if validation_ready
        else "NOT_READY"
        if clean_result == "FAILED"
        else "INCONCLUSIVE"
        if clean_result == "INCONCLUSIVE" or not accounting_clean
        else "MORE_DEVELOPMENT_EVIDENCE_REQUIRED"
    )
    family_status = (
        "CANDIDATE_FOR_VALIDATION_DESIGN"
        if validation_status == "READY"
        else "STOP_FAMILY_B"
        if clean_result == "FAILED"
        else "INCONCLUSIVE"
        if validation_status == "INCONCLUSIVE"
        else "CONTINUE_DEVELOPMENT_RESEARCH"
    )

    root_out = output_root(root)
    directories = {
        "control": root_out / "control",
        "b002": root_out / "b002",
        "comparison": root_out / "comparison",
        "ledgers": root_out / "ledgers",
        "manifests": root_out / "manifests",
    }
    reports_root = root / "data/reports"
    control_body = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "record_id": CONTROL_ID,
        "role": CONTROL_ROLE,
        "source_control_result_hash": EXPECTED_RESULT_HASHES[CONTROL_ID],
        "cost_model": freeze_before["command_01"]["config"]["costs"],
        "performance": control_performance,
        "idealized_performance": analyses[CONTROL_ID][IDEALIZED_MODE]["summary"],
        "yearly": yearly[CONTROL_ID][EXECUTABLE_MODE],
        "cash": control_cash,
        "accounting": accounting[CONTROL_ID],
        "control_reproduction": control_reproduction,
        "idealized_vs_executable": implementation[CONTROL_ID],
        "development_only": True,
        "validation_accessed": False,
        "source_control_overwritten": False,
    }
    control_result_doc = _immutable_document(
        directories["control"] / "clean_control_result_v1.json",
        control_body,
        "clean_control_result_hash",
        EXPECTED_CLEAN_CONTROL_RESULT_HASH,
    )
    b002_body = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "record_id": CLEAN_RECORD_ID,
        "source_experiment_id": "MOM-B-002",
        "parameter_hash": EXPECTED_EXPERIMENT_HASHES["MOM-B-002"]["parameter_hash"],
        "preregistration_hash": EXPECTED_EXPERIMENT_HASHES["MOM-B-002"][
            "preregistration_hash"
        ],
        "family_b_config_hash": EXPECTED_FAMILY_B_CONFIG_HASH,
        "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        "history_remediation_hashes": {
            "history_remediation_config_hash": EXPECTED_HISTORY_REMEDIATION_CONFIG_HASH,
            "raw_extension_hash": EXPECTED_RAW_EXTENSION_HASH,
            "adjusted_extension_hash": EXPECTED_ADJUSTED_EXTENSION_HASH,
            "family_b_sma_readiness_hash": EXPECTED_FAMILY_B_SMA_READINESS_HASH,
            "history_remediation_manifest_hash": EXPECTED_HISTORY_REMEDIATION_MANIFEST_HASH,
        },
        "cost_model": freeze_before["command_01"]["config"]["costs"],
        "performance": clean_performance,
        "idealized_performance": analyses[CLEAN_RECORD_ID][IDEALIZED_MODE]["summary"],
        "yearly": yearly[CLEAN_RECORD_ID][EXECUTABLE_MODE],
        "criteria": criteria,
        "filter_impact": filter_summary,
        "qualifying_breadth": qualifying,
        "cash": clean_cash,
        "accounting": accounting[CLEAN_RECORD_ID],
        "idealized_vs_executable": implementation[CLEAN_RECORD_ID],
        "MOM_B_002_CLEAN_REEVALUATION_RESULT": clean_result,
        "B002_CLEAN_TREND_FILTER_EVIDENCE": evidence,
        "B002_CLEAN_DEVELOPMENT_ATTRIBUTION": attribution,
        "attribution_details": attribution_details,
        "development_only": True,
        "prehistory_performance_observations": 0,
        "parameters_changed": False,
        "alternate_SMA_tested": False,
        "combined_filter_tested": False,
        "validation_accessed": False,
    }
    b002_result_doc = _immutable_document(
        directories["b002"] / "clean_b002_result_v1.json",
        b002_body,
        "clean_b002_result_hash",
        EXPECTED_CLEAN_B002_RESULT_HASH,
    )
    reevaluation_body = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "freeze_snapshot_hash": freeze_before["snapshot"]["snapshot_hash"],
        "clean_control_result_hash": control_result_doc["clean_control_result_hash"],
        "clean_b002_result_hash": b002_result_doc["clean_b002_result_hash"],
        "comparison": comparison,
        "criteria": criteria,
        "filter_impact": filter_summary,
        "decisions": {
            "MOM_B_002_CLEAN_REEVALUATION_RESULT": clean_result,
            "B002_CLEAN_TREND_FILTER_EVIDENCE": evidence,
            "B002_CLEAN_DEVELOPMENT_ATTRIBUTION": attribution,
            "B002_VALIDATION_DESIGN_READINESS": validation_status,
            "FAMILY_B_POST_REMEDIATION_STATUS": family_status,
            "B001_STATUS": "NO_DISTINCT_FILTER_EVIDENCE",
        },
        "governance": {
            "B002_parameters_changed": False,
            "alternate_SMA_tested": False,
            "B001_rerun": False,
            "B003_created": False,
            "combined_filter_tested": False,
            "validation_accessed": False,
            "post_2024_rows_loaded": False,
            "strategy_v2_created": False,
            "family_c_started": False,
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "database_writes": 0,
            "network_calls": 0,
            "secrets_written": 0,
        },
    }
    reevaluation_doc = _immutable_document(
        directories["manifests"] / "b002_clean_reevaluation_v1.json",
        reevaluation_body,
        "b002_clean_reevaluation_hash",
        EXPECTED_B002_CLEAN_REEVALUATION_HASH,
    )

    artifact_paths: list[Path] = [
        directories["control"] / "clean_control_result_v1.json",
        directories["b002"] / "clean_b002_result_v1.json",
        directories["manifests"] / "b002_clean_reevaluation_v1.json",
    ]
    for record_id, key in ((CONTROL_ID, "control"), (CLEAN_RECORD_ID, "b002")):
        for mode in (IDEALIZED_MODE, EXECUTABLE_MODE):
            artifact_paths.extend(
                _write_simulation_ledgers(
                    directories[key] / mode.lower(), simulations[record_id][mode]
                )
            )
    combined = {
        key: []
        for key in (
            "daily",
            "rebalances",
            "holdings",
            "costs",
            "periods",
            "position_returns",
        )
    }
    for record_id in (CONTROL_ID, CLEAN_RECORD_ID):
        for mode in (IDEALIZED_MODE, EXECUTABLE_MODE):
            for key in combined:
                combined[key].extend(simulations[record_id][mode][key])
    for key, rows in combined.items():
        path = directories["ledgers"] / f"combined_{key}.csv"
        write_csv(path, rows)
        artifact_paths.append(path)

    control_report = [{"role": CONTROL_ROLE, **control_performance}]
    b002_report = [
        {
            **clean_performance,
            **qualifying,
            **filter_summary,
            "average_invested_pct": clean_performance["average_invested_pct"],
            "MOM_B_002_CLEAN_REEVALUATION_RESULT": clean_result,
        }
    ]
    yearly_report = [
        {"record_id": record_id, **row}
        for record_id in (CONTROL_ID, CLEAN_RECORD_ID)
        for row in yearly[record_id][EXECUTABLE_MODE]
    ]
    criteria_report = [
        {
            "criterion": criterion,
            "status": "PASS" if passed else "FAIL",
            "passed": passed,
            "success_criteria_hash": EXPECTED_SUCCESS_CRITERIA_HASH,
        }
        for criterion, passed in criteria["criteria"].items()
    ]
    comparison_report = [
        {
            "metric": key,
            "value": value,
            "diagnostic_only": True,
        }
        for key, value in comparison.items()
    ]
    cash_report = [
        {"record_id": CONTROL_ID, **control_cash},
        {"record_id": CLEAN_RECORD_ID, **clean_cash},
    ]
    true_attribution = [
        {
            **row,
            "B002_CLEAN_TREND_FILTER_EVIDENCE": evidence,
            "B002_CLEAN_DEVELOPMENT_ATTRIBUTION": attribution,
        }
        for row in filter_rows
        if row["removal_category"] == "TRUE_BELOW_SMA200"
    ]
    if not true_attribution:
        true_attribution = [
            {
                "formation_date": "",
                "execution_date": "",
                "symbol": "",
                "B002_CLEAN_TREND_FILTER_EVIDENCE": evidence,
                "B002_CLEAN_DEVELOPMENT_ATTRIBUTION": attribution,
            }
        ]
    report_values = {
        REPORT_NAMES[1]: control_report,
        REPORT_NAMES[2]: b002_report,
        REPORT_NAMES[3]: yearly_report,
        REPORT_NAMES[4]: criteria_report,
        REPORT_NAMES[5]: filter_rows,
        REPORT_NAMES[6]: comparison_report,
        REPORT_NAMES[7]: cash_report,
        REPORT_NAMES[8]: true_attribution,
    }
    for name, rows in report_values.items():
        path = reports_root / name
        write_csv(path, rows)
        artifact_paths.append(path)
    input_path = directories["comparison"] / "clean_b002_signal_inputs_v1.csv"
    calendar_path = directories["comparison"] / "clean_b002_rebalance_calendar_v1.csv"
    filter_path = directories["comparison"] / "clean_b002_filter_impact_v1.csv"
    write_csv(input_path, clean_rows)
    write_csv(calendar_path, calendar_rows)
    write_csv(filter_path, filter_rows)
    artifact_paths.extend((input_path, calendar_path, filter_path))

    documentation_path = root / "docs/strategy-family-b-b002-clean-reevaluation-v1.md"
    if documentation_path.exists():
        artifact_paths.append(documentation_path)
    freeze_after = verify_freeze_gate(root)
    baseline_unchanged = freeze_before["snapshot"] == freeze_after["snapshot"]
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path) for path in artifact_paths
    }
    manifest_path = directories["manifests"] / "run_manifest_v1.json"
    completion_timestamp = started_at
    if manifest_path.exists():
        completion_timestamp = _read_json(manifest_path).get(
            "completion_timestamp", completion_timestamp
        )
    manifest_body = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "completion_timestamp": completion_timestamp,
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
        },
        "freeze_snapshot_hash": freeze_after["snapshot"]["snapshot_hash"],
        "clean_control_result_hash": control_result_doc["clean_control_result_hash"],
        "clean_b002_result_hash": b002_result_doc["clean_b002_result_hash"],
        "b002_clean_reevaluation_hash": reevaluation_doc[
            "b002_clean_reevaluation_hash"
        ],
        "artifact_hashes": artifact_hashes,
        "validation_accessed": False,
    }
    manifest = _immutable_document(
        manifest_path,
        manifest_body,
        "clean_run_manifest_hash",
        EXPECTED_CLEAN_RUN_MANIFEST_HASH,
    )
    summary = {
        **reevaluation_body,
        "generated_at": started_at,
        "clean_control_result_hash": control_result_doc["clean_control_result_hash"],
        "clean_b002_result_hash": b002_result_doc["clean_b002_result_hash"],
        "b002_clean_reevaluation_hash": reevaluation_doc[
            "b002_clean_reevaluation_hash"
        ],
        "clean_run_manifest_hash": manifest["clean_run_manifest_hash"],
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "first_performance_session": sessions[0],
            "last_performance_session": sessions[-1],
            "prehistory_performance_observations": 0,
            "development_only": True,
        },
        "control": control_result_doc,
        "clean_B002": b002_result_doc,
        "regression": {
            "freeze_snapshot_before": freeze_before["snapshot"]["snapshot_hash"],
            "freeze_snapshot_after": freeze_after["snapshot"]["snapshot_hash"],
            "baseline_unchanged": baseline_unchanged,
            "strategy_v1": "UNCHANGED",
            "CAP4": "UNCHANGED",
            "family_a_commands_01_05": "UNCHANGED",
            "family_a_closure": "UNCHANGED",
            "family_b_command_01": "UNCHANGED",
            "family_b_command_02": "UNCHANGED",
            "family_b_command_03": "UNCHANGED",
            "family_b_command_04": "UNCHANGED",
            "original_CONTROL_B_000": "UNCHANGED",
            "original_MOM_B_001": "UNCHANGED",
            "original_MOM_B_002": "UNCHANGED",
        },
        "storage": {
            "root": root_out.relative_to(root).as_posix(),
            **{
                key: value.relative_to(root).as_posix()
                for key, value in directories.items()
            },
            "artifact_hashes": artifact_hashes,
        },
        "runtime": {
            "seconds": Decimal(str(time.perf_counter() - started)),
            "simulation_count": 4,
            "records": 2,
            "modes_per_record": 2,
        },
        "known_limitations": (
            "FIVE_GENUINE_RECENT_LISTING_CANDIDATE_ROWS_REMAIN_UNAVAILABLE",
            "TWO_CORPORATE_ACTION_EXCLUDED_CANDIDATE_ROWS_REMAIN_UNAVAILABLE",
            "POINT_IN_TIME_MEMBERSHIP_HISTORY_RETAINS_FROZEN_PARTIAL_CONFIDENCE",
            "TRUE_FILTER_ATTRIBUTION_IS_DESCRIPTIVE_AND_NOT_A_NEW_THRESHOLD",
            "Q4_2024_FORMATION_NEXT_OPEN_REMAINS_WITHIN_DEVELOPMENT_BUT_ITS_FINAL_"
            "PERIOD_IS_PARTIAL_AT_2024_12_31",
        ),
        "verification": {
            "backend_tests": "PENDING",
            "frontend_build": "PENDING",
            "ready_for_review": False,
        },
    }
    write_json(reports_root / REPORT_NAMES[0], summary)
    return summary


def finalize_b002_clean_reevaluation_review(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports/family_b_b002_clean_v1_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError("Run clean B002 reevaluation before finalizing")
    summary = _read_json(summary_path)
    freeze = verify_freeze_gate(root)
    if freeze["snapshot"]["snapshot_hash"] != summary["regression"][
        "freeze_snapshot_after"
    ]:
        _freeze_fail("frozen inputs changed after clean reevaluation")
    documents = (
        (
            output_root(root) / "control/clean_control_result_v1.json",
            "clean_control_result_hash",
            EXPECTED_CLEAN_CONTROL_RESULT_HASH,
        ),
        (
            output_root(root) / "b002/clean_b002_result_v1.json",
            "clean_b002_result_hash",
            EXPECTED_CLEAN_B002_RESULT_HASH,
        ),
        (
            output_root(root) / "manifests/b002_clean_reevaluation_v1.json",
            "b002_clean_reevaluation_hash",
            EXPECTED_B002_CLEAN_REEVALUATION_HASH,
        ),
        (
            output_root(root) / "manifests/run_manifest_v1.json",
            "clean_run_manifest_hash",
            EXPECTED_CLEAN_RUN_MANIFEST_HASH,
        ),
    )
    for path, hash_field, expected in documents:
        document = _read_json(path)
        if (
            document.get(hash_field) != expected
            or _recompute_hash(document, hash_field) != expected
        ):
            raise B002CleanReevaluationImmutabilityError(
                f"Immutable clean reevaluation document mismatch: {path}"
            )
    manifest = _read_json(output_root(root) / "manifests/run_manifest_v1.json")
    mismatches = [
        relative_path
        for relative_path, expected_hash in manifest["artifact_hashes"].items()
        if not (root / relative_path).exists()
        or file_sha256(root / relative_path) != expected_hash
    ]
    if mismatches:
        raise B002CleanReevaluationImmutabilityError(
            f"Clean reevaluation artifact mismatch: {mismatches}"
        )
    passed = backend_tests == "PASSED" and frontend_build == "PASSED"
    summary["verification"] = {
        "backend_tests": backend_tests,
        "frontend_build": frontend_build,
        "ready_for_review": passed
        and summary["regression"]["baseline_unchanged"] is True
        and summary["governance"]["validation_accessed"] is False
        and all(summary["clean_B002"]["accounting"].values()),
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    return summary


__all__ = (
    "CLEAN_RECORD_ID",
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXPECTED_B002_CLEAN_REEVALUATION_HASH",
    "EXPECTED_CLEAN_B002_RESULT_HASH",
    "EXPECTED_CLEAN_CONTROL_RESULT_HASH",
    "EXPECTED_CLEAN_RUN_MANIFEST_HASH",
    "FILTER_CATEGORIES",
    "REPORT_NAMES",
    "build_b002_clean_reevaluation",
    "classify_clean_filter_evidence",
    "clean_b002_inputs",
    "filter_attribution",
    "finalize_b002_clean_reevaluation_review",
    "original_clean_comparison",
    "output_root",
    "verify_freeze_gate",
)
