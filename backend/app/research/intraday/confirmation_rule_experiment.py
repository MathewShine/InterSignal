from __future__ import annotations

import csv
import json
import math
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.costs.cost_config import (
    EXPECTED_COST_CONFIG_HASH,
    default_cost_model_config,
)
from app.backtesting.costs.cost_engine import (
    SCENARIO_BASELINE_SLIPPAGE,
    calculate_trade_cost,
    registered_cost_scenarios,
)
from app.research.intraday.confirmation_diagnostic import (
    EXPECTED_DATASET_HASHES,
    EXPERIMENT_IDS as COMMAND_01_EXPERIMENT_IDS,
    _baseline_snapshot,
    _file_sha256,
    _git_ignored,
    _load_bars,
    _population_rows,
    _prereg_baseline_dependency,
    _price_basis_scale,
    _required_session_dates,
    _scale_bars,
    _storage,
    _write_csv,
    _write_json,
    build_window_record,
    confirmation_reference,
    optional_decimal,
    sample_safety,
    validate_development_only,
)
from app.research.intraday.models import FirstTouch
from app.research.temporal_validation.config import (
    DEFAULT_TEMPORAL_CONFIG,
    DEVELOPMENT_WINDOW_VERSION,
    SEALED,
    canonical_hash,
)
from app.research.temporal_validation.models import ExperimentFreezeArtifact


EXPERIMENT_VERSION = "INTRADAY_CONFIRMATION_RULE_EXPERIMENT_V1"
EXPERIMENT_ID = "EXP-INTRARULE-001"
PROFILE = "TEN_MINUTE_OPEN_CONFIRMATION_V1"
EXPERIMENT_TYPE = "DEVELOPMENT_ONLY_CONTROLLED_RULE_EXPERIMENT"
COMMAND = "Step 02.15 / Command 02"
WINDOW_MINUTES = 10
COMPARATOR = ">="
CONTROL = "FROZEN_NEXT_OPEN_BASELINE"
TREATMENT = "TEN_MINUTE_OPEN_CONFIRMATION_V1"
FIRST_TOUCH_ENGINE = "INTRADAY_FIRST_TOUCH_ENGINE_V1"
EXPECTED_COMMAND_01_POPULATION_HASH = (
    "2308db408804b4b85addf34260e2072194c52c64fb878f79b0921054e074965c"
)
EXPECTED_COMMAND_01_PREREGISTRATION_HASH = (
    "7aea55e3e3628031ba1a05980bbef2bb86052a1264642e5e70405041e64ba89e"
)

PRIMARY_METRICS = (
    "treatment_stop_first_rate",
    "treatment_target_first_rate",
    "treatment_mfe_r",
    "treatment_mae_r",
    "confirmed_opportunity_retention_rate",
    "control_failure_rejection_rate",
    "good_opportunity_rejection_rate",
    "treatment_rr_delta_vs_control",
)
FALSIFICATION_CRITERIA = {
    "A": "FAIL if GOOD_OPPORTUNITY_REJECTION_RATE >= CONTROL_FAILURE_REJECTION_RATE",
    "B": "FAIL if matched treatment STOP_FIRST rate is not lower than matched control STOP_FIRST rate",
    "C": "FAIL if median treatment MAE_R does not improve and median treatment MFE_R deteriorates by at least 0.10R",
    "D": "FAIL if fewer than two of three DEVELOPMENT years have positive filter separation and lower treatment STOP_FIRST rate",
    "E": "FAIL if median confirmed drift >1%, median R:R delta <-0.50, or pre-confirmation/structure invalidation rate >10%",
}
MFE_BANDS = ("MFE_LT_0_5", "MFE_0_5_TO_LT_1", "MFE_1_TO_LT_1_5", "MFE_GE_1_5")
MAE_BANDS = ("MAE_LT_0_5", "MAE_0_5_TO_LT_1", "MAE_GE_1")
TREATMENT_STATUSES = (
    "CONFIRMED",
    "REJECTED",
    "PRE_CONFIRMATION_STOP_INVALIDATED",
    "PRE_CONFIRMATION_TARGET_REACHED",
    "PRE_CONFIRMATION_AMBIGUOUS",
    "TREATMENT_STRUCTURE_INVALID",
    "DATA_UNAVAILABLE",
)
REPORT_FILENAMES = (
    "intraday_confirmation_rule_v1_summary.json",
    "intraday_confirmation_rule_v1_population.csv",
    "intraday_confirmation_rule_v1_matched.csv",
    "intraday_confirmation_rule_v1_confirmed.csv",
    "intraday_confirmation_rule_v1_rejected.csv",
    "intraday_confirmation_rule_v1_outcomes.csv",
    "intraday_confirmation_rule_v1_yearly.csv",
    "intraday_confirmation_rule_v1_rr.csv",
    "intraday_confirmation_rule_v1_costs.csv",
    "intraday_confirmation_rule_v1_contexts.csv",
    "intraday_confirmation_rule_v1_pilot.csv",
)


def exact_ten_minute_rule(first_10m_close: Decimal, t1_open: Decimal) -> bool:
    return first_10m_close >= t1_open


def treatment_status(record: Mapping[str, Any]) -> str:
    if not record.get("data_available"):
        return "DATA_UNAVAILABLE"
    feasibility = str(record.get("confirmation_feasibility", ""))
    if feasibility == "INTRABAR_AMBIGUOUS":
        return "PRE_CONFIRMATION_AMBIGUOUS"
    if feasibility == "STOP_INVALIDATED_BEFORE_CONFIRMATION":
        return "PRE_CONFIRMATION_STOP_INVALIDATED"
    if feasibility == "TARGET_REACHED_BEFORE_CONFIRMATION":
        return "PRE_CONFIRMATION_TARGET_REACHED"
    if feasibility == "STRUCTURE_INVALID_AT_CONFIRMATION":
        return "TREATMENT_STRUCTURE_INVALID"
    close = Decimal(str(record["confirmation_price"]))
    session_open = Decimal(str(record["frozen_next_open"]))
    return "CONFIRMED" if exact_ten_minute_rule(close, session_open) else "REJECTED"


def favorable_control_opportunity(row: Mapping[str, Any]) -> bool:
    return str(row.get("control_path_outcome")) == "TARGET_FIRST" or Decimal(
        str(row.get("control_mfe_r") or 0)
    ) >= Decimal("1.5")


def mfe_band(value: Any) -> str:
    number = Decimal(str(value or 0))
    if number < Decimal("0.5"):
        return MFE_BANDS[0]
    if number < 1:
        return MFE_BANDS[1]
    if number < Decimal("1.5"):
        return MFE_BANDS[2]
    return MFE_BANDS[3]


def mae_band(value: Any) -> str:
    number = Decimal(str(value or 0))
    if number < Decimal("0.5"):
        return MAE_BANDS[0]
    if number < 1:
        return MAE_BANDS[1]
    return MAE_BANDS[2]


def _rate(numerator: int, denominator: int) -> Decimal | None:
    return Decimal(numerator) * 100 / Decimal(denominator) if denominator else None


def _numbers(rows: Sequence[Mapping[str, Any]], field: str) -> list[Decimal]:
    return sorted(
        Decimal(str(row[field]))
        for row in rows
        if row.get(field) is not None and str(row.get(field)) != ""
    )


def _mean(rows: Sequence[Mapping[str, Any]], field: str) -> Decimal | None:
    values = _numbers(rows, field)
    return sum(values, Decimal("0")) / len(values) if values else None


def _median(rows: Sequence[Mapping[str, Any]], field: str) -> Decimal | None:
    values = _numbers(rows, field)
    if not values:
        return None
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def _percentile(
    rows: Sequence[Mapping[str, Any]], field: str, quantile: Decimal
) -> Decimal | None:
    values = _numbers(rows, field)
    if not values:
        return None
    position = quantile * Decimal(len(values) - 1)
    lower = int(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _control_path(source: Mapping[str, Any]) -> str:
    value = str(source.get("first_touch_outcome", ""))
    if value == "STOP_FIRST":
        return "STOP_FIRST"
    if value == "TARGET_FIRST":
        return "TARGET_FIRST"
    if "AMBIGUOUS" in value:
        return "AMBIGUOUS"
    return "NEITHER"


def _treatment_path(record: Mapping[str, Any]) -> str | None:
    if treatment_status(record) != "CONFIRMED":
        return None
    value = str(record.get("post_first_touch", ""))
    if value in {str(FirstTouch.STOP_FIRST), str(FirstTouch.GAP_THROUGH_STOP)}:
        return "STOP_FIRST"
    if value in {str(FirstTouch.TARGET_FIRST), str(FirstTouch.GAP_THROUGH_TARGET)}:
        return "TARGET_FIRST"
    if value == str(FirstTouch.INTRABAR_SEQUENCE_AMBIGUOUS):
        return "AMBIGUOUS"
    return "NEITHER"


def _session_date(source: Mapping[str, Any], ordinal: Any) -> str:
    text = str(ordinal or "")
    return str(source.get(f"session_date_{text}") or source.get("session_date_4"))


def _exit_reference(
    row: Mapping[str, Any], source: Mapping[str, Any], *, treatment: bool
) -> tuple[Decimal, str]:
    path = row.get("treatment_path_outcome") if treatment else row["control_path_outcome"]
    if path == "STOP_FIRST":
        ordinal = source.get("first_stop_session")
        when = (
            row.get("treatment_first_touch_timestamp")
            if treatment
            else _session_date(source, ordinal)
        )
        return Decimal(str(row["stop"])), str(when)[:10]
    if path == "TARGET_FIRST":
        ordinal = source.get("first_target_session")
        when = (
            row.get("treatment_first_touch_timestamp")
            if treatment
            else _session_date(source, ordinal)
        )
        return Decimal(str(row["target"])), str(when)[:10]
    return Decimal(str(source["close_4"])), str(source["session_date_4"])


def _cost_reference(
    *,
    row: Mapping[str, Any],
    source: Mapping[str, Any],
    entry: Decimal,
    treatment: bool,
) -> dict[str, Any]:
    quantity = int(Decimal(str(source["hypothetical_quantity"])))
    stop = Decimal(str(row["stop"]))
    exit_price, exit_date = _exit_reference(row, source, treatment=treatment)
    risk_per_share = entry - stop
    initial_risk = risk_per_share * quantity
    gross_pnl = (exit_price - entry) * quantity
    trade = {
        "quantity": quantity,
        "entry_date": row["entry_date"],
        "exit_date": exit_date,
        "entry_price": entry,
        "exit_price": exit_price,
        "gross_pnl": gross_pnl,
        "initial_planned_risk": initial_risk,
        "realized_r_multiple": gross_pnl / initial_risk,
    }
    config = default_cost_model_config()
    if config.config_hash() != EXPECTED_COST_CONFIG_HASH:
        raise ValueError("Frozen INDIA_EQUITY_COST_MODEL_V1 config changed")
    scenario = next(
        item
        for item in registered_cost_scenarios()
        if item.scenario_id == SCENARIO_BASELINE_SLIPPAGE
    )
    costed = calculate_trade_cost(trade, config=config, scenario=scenario)
    return {
        "quantity_basis": "FROZEN_STRATEGY_V1_HYPOTHETICAL_QUANTITY",
        "quantity": quantity,
        "entry_reference": entry,
        "exit_reference": exit_price,
        "exit_date": exit_date,
        "estimated_round_trip_cost": costed["total_transaction_cost"],
        "cost_r": costed["cost_r_multiple"],
        "gross_r": costed["gross_realized_r"],
        "gross_to_cost_headroom_r": costed["gross_realized_r"]
        - costed["cost_r_multiple"],
        "gross_to_cost_headroom_rupees": gross_pnl
        - costed["total_transaction_cost"],
        "cost_model": costed["cost_model_version"],
        "cost_config_hash": costed["cost_config_hash"],
        "cost_scenario": costed["scenario_id"],
        "slippage_bps_per_side": Decimal("5"),
    }


def _command_01_snapshot(root: Path) -> dict[str, Any]:
    artifact = root / "data/research/diagnostics/intraday/v1/confirmation_command_01"
    summary_path = root / "data/reports/intraday_confirmation_v1_summary.json"
    prereg_path = artifact / "registry/intraday_confirmation_registry_v1_preregistered.json"
    registry_path = artifact / "registry/intraday_confirmation_registry_v1.json"
    population_path = artifact / "population_manifest_v1.json"
    run_manifest_path = artifact / "run_manifest_v1.json"
    paths = (summary_path, prereg_path, registry_path, population_path, run_manifest_path)
    if any(not path.exists() for path in paths):
        raise FileNotFoundError("Command 01 frozen artifacts are unavailable")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if summary["population_freeze"]["intraday_confirmation_population_hash"] != EXPECTED_COMMAND_01_POPULATION_HASH:
        raise ValueError("Command 01 population hash changed")
    if summary["pre_registration"]["intraday_confirmation_prereg_hash"] != EXPECTED_COMMAND_01_PREREGISTRATION_HASH:
        raise ValueError("Command 01 preregistration hash changed")
    if tuple(row["experiment_id"] for row in registry["experiments"]) != COMMAND_01_EXPERIMENT_IDS:
        raise ValueError("Command 01 experiment IDs changed")
    experiment_hashes = {
        row["experiment_id"]: {
            "parameter_hash": row["parameter_hash"],
            "pre_registration_hash": row["pre_registration_hash"],
            "result_fingerprint": row["result_fingerprint"],
        }
        for row in registry["experiments"]
    }
    return {
        "population_hash": EXPECTED_COMMAND_01_POPULATION_HASH,
        "preregistration_hash": EXPECTED_COMMAND_01_PREREGISTRATION_HASH,
        "experiment_count": len(experiment_hashes),
        "experiment_hashes": experiment_hashes,
        "semantic_hash": canonical_hash(experiment_hashes),
        "file_hashes": {path.relative_to(root).as_posix(): _file_sha256(path) for path in paths},
    }


def baseline_snapshot(root: Path) -> dict[str, Any]:
    snapshot = _baseline_snapshot(root)
    snapshot["command_01"] = _command_01_snapshot(root)
    snapshot["cost_model_config_hash"] = default_cost_model_config().config_hash()
    return snapshot


def preregistration_dependencies(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **_prereg_baseline_dependency(snapshot),
        "command_01_population_hash": snapshot["command_01"]["population_hash"],
        "command_01_preregistration_hash": snapshot["command_01"]["preregistration_hash"],
        "command_01_experiment_hashes": snapshot["command_01"]["experiment_hashes"],
        "command_01_semantic_hash": snapshot["command_01"]["semantic_hash"],
        "cost_model_config_hash": snapshot["cost_model_config_hash"],
    }


def build_population(
    root: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]], dict[str, Any], Any]:
    command_population, sources, context = _population_rows(root)
    required = _required_session_dates(command_population, sources)
    bars = _load_bars(root, required)
    rows: list[dict[str, Any]] = []
    exclusions = Counter()
    for source_row in command_population:
        symbol = source_row["symbol"]
        entry_date = date.fromisoformat(source_row["entry_date"])
        raw_five = tuple(bars[5].get((symbol, entry_date), ()))
        raw_ten = tuple(bars[10].get((symbol, entry_date), ()))
        try:
            factor = _price_basis_scale(
                Decimal(str(source_row["frozen_next_open"])), raw_five
            )
            close, timestamp, causal = confirmation_reference(
                _scale_bars(raw_five, factor), _scale_bars(raw_ten, factor), 10
            )
        except ValueError:
            exclusions["FIRST_10M_BAR_UNAVAILABLE"] += 1
            continue
        rows.append(
            {
                "opportunity_id": source_row["opportunity_id"],
                "symbol": symbol,
                "decision_date": source_row["decision_date"],
                "entry_date": source_row["entry_date"],
                "score": source_row["score"],
                "setup_quality": source_row["setup_quality"],
                "candidate_stage": source_row["candidate_stage"],
                "regime_state": source_row["regime_state"],
                "t1_open": source_row["frozen_next_open"],
                "first_10m_close": close,
                "first_10m_timestamp": timestamp,
                "causal_source_bar_count": len(causal),
                "causal_cutoff_verified": all(bar.bar_end <= timestamp for bar in causal),
                "stop": source_row["frozen_stop"],
                "target": source_row["frozen_target"],
                "frozen_rr": source_row["frozen_effective_rr"],
                "intraday_quality": source_row["intraday_quality"],
                "corporate_action_safe": source_row["CA_safety"] == "SAFE",
                "frozen_admitted_flag": bool(source_row["is_admitted"]),
                "price_basis_scale_factor": factor,
                "price_basis_alignment": "CAUSAL_T1_OPEN_RATIO_TO_FROZEN_DAILY_BASIS",
            }
        )
    validate_development_only(
        [date.fromisoformat(row["decision_date"]) for row in rows]
    )
    return rows, sources, {**context, "command_02_exclusions": dict(exclusions)}, bars


def freeze_population(rows: Sequence[Mapping[str, Any]]) -> str:
    ordered = sorted((dict(row) for row in rows), key=lambda row: row["opportunity_id"])
    if len({row["opportunity_id"] for row in ordered}) != len(ordered):
        raise ValueError("Experiment population contains duplicate opportunity IDs")
    if any(not ("2022-01-01" <= row["decision_date"] <= "2024-12-31") for row in ordered):
        raise ValueError("Experiment population contains non-DEVELOPMENT rows")
    required = {
        "symbol",
        "entry_date",
        "t1_open",
        "first_10m_close",
        "stop",
        "target",
        "frozen_rr",
        "intraday_quality",
        "corporate_action_safe",
        "frozen_admitted_flag",
    }
    if any(required.difference(row) for row in ordered):
        raise ValueError("Experiment population row is missing a required frozen field")
    if any(not row["corporate_action_safe"] for row in ordered):
        raise ValueError("Experiment population contains a corporate-action-unsafe row")
    if any(not str(row["intraday_quality"]).startswith("USABLE_STRICT") for row in ordered):
        raise ValueError("Experiment population contains a non-strict intraday row")
    return canonical_hash(ordered)


def build_preregistration(
    population_hash: str, dependencies: Mapping[str, Any]
) -> dict[str, Any]:
    parameters = {
        "experiment_version": EXPERIMENT_VERSION,
        "population_hash": population_hash,
        "profile": PROFILE,
        "experiment_type": EXPERIMENT_TYPE,
        "one_changed_dimension": "ENTRY_CONFIRMATION_TIMING_AND_SIGN_FILTER_ONLY",
        "architecture_led_window_choice": "10m midpoint of original intended 5m-to-15m confirmation window; not selected by historical performance",
        "window_minutes": WINDOW_MINUTES,
        "confirmation_comparator": COMPARATOR,
        "confirmation_rule": "first_10m_close >= T1_session_open",
        "confirmation_reference": "FIRST_COMPLETED_DERIVED_10M_BAR_CLOSE",
        "control": CONTROL,
        "treatment": TREATMENT,
        "stop_target": "FROZEN_UNCHANGED",
        "holding_horizon": "FROZEN_STRATEGY_V1_MAX_4_SESSIONS",
        "risk_structure": "FROZEN_RISK_STRUCTURE_V1_1",
        "ranking": "FROZEN_UNCHANGED_NO_ADMISSION_RERUN",
        "cost_model": "INDIA_EQUITY_COST_MODEL_V1",
        "cost_scenario": "COST-SCENARIO-002_BASELINE_5BPS_PER_SIDE",
        "cost_quantity_basis": "FROZEN_STRATEGY_V1_HYPOTHETICAL_QUANTITY",
        "primary_metrics": PRIMARY_METRICS,
        "favorable_control_definition": "TARGET_FIRST OR control_MFE_R >= 1.5",
        "mfe_bands": MFE_BANDS,
        "mae_bands": MAE_BANDS,
        "falsification_criteria": FALSIFICATION_CRITERIA,
        "material_mfe_deterioration_r": Decimal("0.10"),
        "material_rr_degradation_r": Decimal("-0.50"),
        "material_delay_drift_pct": Decimal("1.0"),
        "material_invalidation_rate_pct": Decimal("10"),
        "post_confirmation_path_starts": "NEXT_ELIGIBLE_5M_BAR",
        "first_touch_engine": FIRST_TOUCH_ENGINE,
        "same_bar_policy": "PRESERVE_INTRABAR_SEQUENCE_AMBIGUOUS",
        "price_basis_alignment": "CAUSAL_T1_OPEN_RATIO_TO_FROZEN_DAILY_BASIS",
        "development_start": DEFAULT_TEMPORAL_CONFIG.development_start,
        "development_end": DEFAULT_TEMPORAL_CONFIG.development_end,
        "validation_state": SEALED,
        "validation_run_count": 0,
        "treatment_windows_run": (10,),
        "vwap_filter_used": False,
        "opening_range_filter_used": False,
        "optimization_allowed": False,
        "portfolio_rerun_allowed": False,
        "strategy_v2_allowed": False,
    }
    body = {
        "experiment_id": EXPERIMENT_ID,
        "experiment_version": EXPERIMENT_VERSION,
        "profile": PROFILE,
        "experiment_type": EXPERIMENT_TYPE,
        "hypothesis": "A simple causal 10-minute open confirmation rule may avoid some early-weakness failures without excessive delay cost.",
        "rule": "CONFIRMED iff first_10m_close >= T1_session_open",
        "population_hash": population_hash,
        "parameters": parameters,
        "parameter_hash": canonical_hash(parameters),
        "primary_metrics": PRIMARY_METRICS,
        "falsification_criteria": FALSIFICATION_CRITERIA,
        "baseline_dependencies": dict(dependencies),
        "promotion_allowed": False,
        "validation_authorized": False,
        "pre_registered": True,
        "written_before_outcome_computation": True,
    }
    return {
        **body,
        "experiment_preregistration_hash": canonical_hash(body),
        "status": "REGISTERED",
    }


def build_experiment_freeze(
    preregistration: Mapping[str, Any], development_result_hash: str
) -> ExperimentFreezeArtifact:
    artifact = ExperimentFreezeArtifact(
        experiment_id=EXPERIMENT_ID,
        experiment_version=EXPERIMENT_VERSION,
        hypothesis=str(preregistration["hypothesis"]),
        development_window=DEVELOPMENT_WINDOW_VERSION,
        parameters=preregistration["parameters"],
        primary_metric="CONTROL_FAILURE_REJECTION_RATE_MINUS_GOOD_OPPORTUNITY_REJECTION_RATE",
        secondary_metrics=PRIMARY_METRICS,
        falsification_criteria=tuple(FALSIFICATION_CRITERIA.values()),
        promotion_criteria=("DEVELOPMENT RESULT CANNOT PROMOTE A RULE",),
        minimum_sample=300,
        baseline_dependencies={
            "command_01_population_hash": EXPECTED_COMMAND_01_POPULATION_HASH,
            "command_01_preregistration_hash": EXPECTED_COMMAND_01_PREREGISTRATION_HASH,
            "command_05b_5m_hash": EXPECTED_DATASET_HASHES["normalized_5m_dataset_hash"],
            "command_05b_10m_hash": EXPECTED_DATASET_HASHES["derived_10m_dataset_hash"],
            "cost_config_hash": EXPECTED_COST_CONFIG_HASH,
        },
        development_result_hash=development_result_hash,
        cost_model="INDIA_EQUITY_COST_MODEL_V1",
        frozen_at="DETERMINISTIC_AFTER_DEVELOPMENT_RESULT_COMPUTATION",
        validation_authorized=False,
    )
    artifact.validate()
    if artifact.parameter_hash() != preregistration["parameter_hash"]:
        raise ValueError("Experiment freeze parameter hash does not match preregistration")
    return artifact


def _matched_rows(
    population: Sequence[Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    context: Mapping[str, Any],
    bars: Any,
    notify: Callable[[str], None],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, population_row in enumerate(population, start=1):
        opportunity_id = population_row["opportunity_id"]
        source = sources[opportunity_id]
        adapter = {
            **dict(population_row),
            "frozen_next_open": population_row["t1_open"],
            "frozen_stop": population_row["stop"],
            "frozen_target": population_row["target"],
            "frozen_effective_rr": population_row["frozen_rr"],
            "is_admitted": population_row["frozen_admitted_flag"],
        }
        record = build_window_record(
            manifest_row=adapter,
            source=source,
            risk_row=context["risk_rows"].get(opportunity_id, {}),
            window=10,
            bars_by_window=bars,
        )
        status = treatment_status(record)
        control_path = _control_path(source)
        treatment_path = _treatment_path(record) if status == "CONFIRMED" else None
        matched = {
            **dict(population_row),
            "population": "FROZEN_ADMITTED_SUBSET"
            if population_row["frozen_admitted_flag"]
            else "SOURCE_ONLY",
            "control_eligible": True,
            "treatment_status": status,
            "control_entry_reference": population_row["t1_open"],
            "treatment_entry_reference": record.get("confirmation_price")
            if status == "CONFIRMED"
            else None,
            "price_drift_pct": record.get("price_change_from_open_pct"),
            "control_rr": population_row["frozen_rr"],
            "treatment_rr": record.get("confirmation_effective_rr")
            if status == "CONFIRMED"
            else None,
            "rr_delta": record.get("rr_delta") if status == "CONFIRMED" else None,
            "control_path_outcome": control_path,
            "treatment_path_outcome": treatment_path,
            "control_mfe_r": optional_decimal(source.get("mfe_r_4")),
            "control_mae_r": optional_decimal(source.get("mae_r_4")),
            "treatment_mfe_r": record.get("mfe_confirm_r")
            if status == "CONFIRMED"
            else None,
            "treatment_mae_r": record.get("mae_confirm_r")
            if status == "CONFIRMED"
            else None,
            "treatment_first_touch_timestamp": record.get("post_first_touch_timestamp"),
            "daily_gap_band": source.get("gap_category"),
            "pre_confirmation_stop_touched": record.get("stop_touched_before_confirmation"),
            "pre_confirmation_target_touched": record.get("target_touched_before_confirmation"),
            "pre_confirmation_ambiguous": record.get("preconfirmation_ambiguity"),
            "control_favorable": False,
            "rejected_control_mfe_band": None,
            "rejected_control_mae_band": None,
            "control_cost": None,
            "treatment_cost": None,
        }
        matched["control_favorable"] = favorable_control_opportunity(matched)
        if status == "REJECTED":
            matched["rejected_control_mfe_band"] = mfe_band(matched["control_mfe_r"])
            matched["rejected_control_mae_band"] = mae_band(matched["control_mae_r"])
        if status == "CONFIRMED":
            matched["control_cost"] = _cost_reference(
                row=matched,
                source=source,
                entry=Decimal(str(matched["control_entry_reference"])),
                treatment=False,
            )
            matched["treatment_cost"] = _cost_reference(
                row=matched,
                source=source,
                entry=Decimal(str(matched["treatment_entry_reference"])),
                treatment=True,
            )
            matched["control_cost_r"] = matched["control_cost"]["cost_r"]
            matched["treatment_cost_r"] = matched["treatment_cost"]["cost_r"]
            matched["cost_r_delta"] = (
                matched["treatment_cost_r"] - matched["control_cost_r"]
            )
        else:
            matched["control_cost_r"] = None
            matched["treatment_cost_r"] = None
            matched["cost_r_delta"] = None
        output.append(matched)
        if index % 250 == 0:
            notify(f"Evaluated {index}/{len(population)} matched 10m opportunities")
    return output


def population_metrics(
    rows: Sequence[Mapping[str, Any]], population: str
) -> dict[str, Any]:
    selected = (
        list(rows)
        if population == "SOURCE_OPPORTUNITIES"
        else [row for row in rows if row["frozen_admitted_flag"]]
    )
    confirmed = [row for row in selected if row["treatment_status"] == "CONFIRMED"]
    rejected = [row for row in selected if row["treatment_status"] == "REJECTED"]
    status_counts = Counter(row["treatment_status"] for row in selected)
    control_failures = [row for row in selected if row["control_path_outcome"] == "STOP_FIRST"]
    favorable = [row for row in selected if row["control_favorable"]]
    rejected_failures = [row for row in control_failures if row["treatment_status"] == "REJECTED"]
    rejected_good = [row for row in favorable if row["treatment_status"] == "REJECTED"]
    failure_rate = _rate(len(rejected_failures), len(control_failures))
    good_rate = _rate(len(rejected_good), len(favorable))
    separation = failure_rate - good_rate if failure_rate is not None and good_rate is not None else None
    control_paths = Counter(row["control_path_outcome"] for row in confirmed)
    treatment_paths = Counter(row["treatment_path_outcome"] for row in confirmed)
    control_mfe = _median(confirmed, "control_mfe_r")
    treatment_mfe = _median(confirmed, "treatment_mfe_r")
    control_mae = _median(confirmed, "control_mae_r")
    treatment_mae = _median(confirmed, "treatment_mae_r")
    status_output = {status: status_counts.get(status, 0) for status in TREATMENT_STATUSES}
    return {
        "population": population,
        "source_count": len(selected),
        "population_sample_safety": sample_safety(len(selected)),
        "treatment_sample_safety": sample_safety(len(confirmed)),
        "sample_safety": sample_safety(len(confirmed)),
        "status_counts": status_output,
        "confirmed_count": len(confirmed),
        "rejected_count": len(rejected),
        "confirmed_retention_rate_pct": _rate(len(confirmed), len(selected)),
        "rejection_rate_pct": _rate(len(rejected), len(selected)),
        "control_failure_count": len(control_failures),
        "control_failure_rejected_count": len(rejected_failures),
        "control_failure_rejection_rate_pct": failure_rate,
        "favorable_control_count": len(favorable),
        "good_opportunity_rejected_count": len(rejected_good),
        "good_opportunity_rejection_rate_pct": good_rate,
        "filter_separation_pp": separation,
        "matched_control_paths": {
            name: {
                "count": control_paths.get(name, 0),
                "rate_pct": _rate(control_paths.get(name, 0), len(confirmed)),
            }
            for name in ("STOP_FIRST", "TARGET_FIRST", "AMBIGUOUS", "NEITHER")
        },
        "matched_treatment_paths": {
            name: {
                "count": treatment_paths.get(name, 0),
                "rate_pct": _rate(treatment_paths.get(name, 0), len(confirmed)),
            }
            for name in ("STOP_FIRST", "TARGET_FIRST", "AMBIGUOUS", "NEITHER")
        },
        "median_control_mfe_r": control_mfe,
        "median_treatment_mfe_r": treatment_mfe,
        "median_mfe_delta_r": treatment_mfe - control_mfe,
        "median_control_mae_r": control_mae,
        "median_treatment_mae_r": treatment_mae,
        "median_mae_delta_r": treatment_mae - control_mae,
        "confirmed_price_drift": {
            "mean_pct": _mean(confirmed, "price_drift_pct"),
            "median_pct": _median(confirmed, "price_drift_pct"),
            "p25_pct": _percentile(confirmed, "price_drift_pct", Decimal("0.25")),
            "p75_pct": _percentile(confirmed, "price_drift_pct", Decimal("0.75")),
            "p90_pct": _percentile(confirmed, "price_drift_pct", Decimal("0.90")),
            "gt_1_pct_rate": _rate(sum(Decimal(str(row["price_drift_pct"])) > 1 for row in confirmed), len(confirmed)),
            "gt_2_pct_rate": _rate(sum(Decimal(str(row["price_drift_pct"])) > 2 for row in confirmed), len(confirmed)),
            "cheaper_than_open_rate": _rate(sum(Decimal(str(row["price_drift_pct"])) < 0 for row in confirmed), len(confirmed)),
        },
        "rr": {
            "median_control_rr": _median(confirmed, "control_rr"),
            "median_treatment_rr": _median(confirmed, "treatment_rr"),
            "median_delta": _median(confirmed, "rr_delta"),
            "mean_delta": _mean(confirmed, "rr_delta"),
            "lt_1_5_rate_pct": _rate(sum(Decimal(str(row["treatment_rr"])) < Decimal("1.5") for row in confirmed), len(confirmed)),
            "ge_2_rate_pct": _rate(sum(Decimal(str(row["treatment_rr"])) >= 2 for row in confirmed), len(confirmed)),
            "ge_2_5_rate_pct": _rate(sum(Decimal(str(row["treatment_rr"])) >= Decimal("2.5") for row in confirmed), len(confirmed)),
        },
        "costs": {
            "median_control_cost_r": _median(confirmed, "control_cost_r"),
            "median_treatment_cost_r": _median(confirmed, "treatment_cost_r"),
            "median_cost_r_delta": _median(confirmed, "cost_r_delta"),
            "mean_control_cost_r": _mean(confirmed, "control_cost_r"),
            "mean_treatment_cost_r": _mean(confirmed, "treatment_cost_r"),
        },
        "rejected_cohort": {
            "control_paths": dict(sorted(Counter(row["control_path_outcome"] for row in rejected).items())),
            "control_favorable_count": sum(row["control_favorable"] for row in rejected),
            "mfe_bands": dict(sorted(Counter(row["rejected_control_mfe_band"] for row in rejected).items())),
            "mae_bands": dict(sorted(Counter(row["rejected_control_mae_band"] for row in rejected).items())),
        },
    }


def temporal_consistency(yearly: Sequence[Mapping[str, Any]]) -> str:
    if len(yearly) != 3 or any(row["confirmed_count"] < 30 for row in yearly):
        return "INCONCLUSIVE"
    supportive = sum(
        Decimal(str(row["filter_separation_pp"])) > 0
        and Decimal(str(row["treatment_stop_first_rate_pct"]))
        < Decimal(str(row["control_stop_first_rate_pct"]))
        for row in yearly
    )
    inverse = sum(Decimal(str(row["filter_separation_pp"])) <= 0 for row in yearly)
    if supportive == 3:
        return "CONSISTENT"
    if supportive >= 2:
        return "MOSTLY_CONSISTENT"
    if inverse >= 2:
        return "INVERSE"
    return "UNSTABLE"


def _yearly(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for year in (2022, 2023, 2024):
        selected = [row for row in rows if row["decision_date"].startswith(str(year))]
        metrics = population_metrics(selected, "SOURCE_OPPORTUNITIES")
        output.append(
            {
                "year": year,
                "source_count": len(selected),
                "sample_safety": metrics["treatment_sample_safety"],
                "confirmed_count": metrics["confirmed_count"],
                "confirmed_retention_rate_pct": metrics["confirmed_retention_rate_pct"],
                "failure_rejection_rate_pct": metrics["control_failure_rejection_rate_pct"],
                "good_opportunity_rejection_rate_pct": metrics["good_opportunity_rejection_rate_pct"],
                "filter_separation_pp": metrics["filter_separation_pp"],
                "control_stop_first_count": metrics["matched_control_paths"]["STOP_FIRST"]["count"],
                "control_stop_first_rate_pct": metrics["matched_control_paths"]["STOP_FIRST"]["rate_pct"],
                "treatment_stop_first_count": metrics["matched_treatment_paths"]["STOP_FIRST"]["count"],
                "treatment_stop_first_rate_pct": metrics["matched_treatment_paths"]["STOP_FIRST"]["rate_pct"],
                "control_target_first_count": metrics["matched_control_paths"]["TARGET_FIRST"]["count"],
                "treatment_target_first_count": metrics["matched_treatment_paths"]["TARGET_FIRST"]["count"],
                "control_mfe_r": metrics["median_control_mfe_r"],
                "treatment_mfe_r": metrics["median_treatment_mfe_r"],
                "control_mae_r": metrics["median_control_mae_r"],
                "treatment_mae_r": metrics["median_treatment_mae_r"],
                "median_rr_delta": metrics["rr"]["median_delta"],
            }
        )
    return output


def falsification_results(
    metrics: Mapping[str, Any], yearly: Sequence[Mapping[str, Any]], consistency: str
) -> dict[str, Any]:
    control_stop = Decimal(str(metrics["matched_control_paths"]["STOP_FIRST"]["rate_pct"]))
    treatment_stop = Decimal(str(metrics["matched_treatment_paths"]["STOP_FIRST"]["rate_pct"]))
    invalid_count = sum(
        metrics["status_counts"][name]
        for name in (
            "PRE_CONFIRMATION_STOP_INVALIDATED",
            "PRE_CONFIRMATION_TARGET_REACHED",
            "PRE_CONFIRMATION_AMBIGUOUS",
            "TREATMENT_STRUCTURE_INVALID",
        )
    )
    invalid_rate = _rate(invalid_count, metrics["source_count"])
    return {
        "A": {
            "passed": metrics["control_failure_rejection_rate_pct"]
            > metrics["good_opportunity_rejection_rate_pct"],
            "observed": metrics["filter_separation_pp"],
        },
        "B": {"passed": treatment_stop < control_stop, "observed_delta_pp": treatment_stop - control_stop},
        "C": {
            "passed": not (
                metrics["median_mae_delta_r"] >= 0
                and metrics["median_mfe_delta_r"] <= Decimal("-0.10")
            ),
            "mfe_delta_r": metrics["median_mfe_delta_r"],
            "mae_delta_r": metrics["median_mae_delta_r"],
        },
        "D": {
            "passed": consistency in {"CONSISTENT", "MOSTLY_CONSISTENT"},
            "observed": consistency,
        },
        "E": {
            "passed": metrics["confirmed_price_drift"]["median_pct"] <= 1
            and metrics["rr"]["median_delta"] >= Decimal("-0.50")
            and invalid_rate <= 10,
            "median_drift_pct": metrics["confirmed_price_drift"]["median_pct"],
            "median_rr_delta": metrics["rr"]["median_delta"],
            "invalidation_rate_pct": invalid_rate,
        },
    }


def _classifications(
    metrics: Mapping[str, Any], criteria: Mapping[str, Any], consistency: str
) -> dict[str, str]:
    passed = sum(row["passed"] for row in criteria.values())
    if passed == 5:
        result = "SUPPORTED_FOR_NEXT_STAGE"
    elif passed == 4 and criteria["A"]["passed"] and criteria["B"]["passed"]:
        result = "WEAKLY_SUPPORTED"
    elif passed >= 2:
        result = "MIXED"
    else:
        result = "NOT_SUPPORTED"
    hypothesis = (
        "SURVIVES_DEVELOPMENT_TEST"
        if result == "SUPPORTED_FOR_NEXT_STAGE"
        else "WEAKENS"
        if result in {"WEAKLY_SUPPORTED", "MIXED"}
        else "REJECTED"
    )
    eligible = (
        metrics["confirmed_count"] >= 300
        and criteria["A"]["passed"]
        and criteria["B"]["passed"]
        and criteria["E"]["passed"]
        and consistency in {"CONSISTENT", "MOSTLY_CONSISTENT"}
        and metrics["rr"]["median_delta"] >= Decimal("-0.50")
        and metrics["status_counts"]["DATA_UNAVAILABLE"] == 0
    )
    return {
        "TEMPORAL_RULE_CONSISTENCY": consistency,
        "TEN_MINUTE_CONFIRMATION_RULE_RESULT": result,
        "TEN_MINUTE_CONFIRMATION_HYPOTHESIS": hypothesis,
        "ELIGIBLE_FOR_VALIDATION_CONSIDERATION": "YES" if eligible else "NO",
    }


def _contexts(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    dimensions = (
        ("score", "score"),
        ("setup_quality", "setup_quality"),
        ("candidate_stage", "candidate_stage"),
        ("regime_state", "regime_state"),
        ("frozen_rr_band", None),
        ("gap_band", None),
    )
    output = []
    for dimension, field in dimensions:
        groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            if dimension == "frozen_rr_band":
                rr = Decimal(str(row["frozen_rr"]))
                value = "RR_LT_2" if rr < 2 else "RR_2_TO_LT_2_5" if rr < Decimal("2.5") else "RR_GE_2_5"
            elif dimension == "gap_band":
                value = str(row.get("daily_gap_band") or "COMMAND_01_FROZEN_GAP_BAND_UNAVAILABLE")
            else:
                value = str(row.get(field) or "UNAVAILABLE")
            groups[value].append(row)
        for value, selected in sorted(groups.items()):
            confirmed = [row for row in selected if row["treatment_status"] == "CONFIRMED"]
            output.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "count": len(selected),
                    "sample_safety": sample_safety(len(selected)),
                    "confirmed_count": len(confirmed),
                    "confirmed_rate_pct": _rate(len(confirmed), len(selected)),
                    "control_stop_first_rate_pct": _rate(sum(row["control_path_outcome"] == "STOP_FIRST" for row in confirmed), len(confirmed)),
                    "treatment_stop_first_rate_pct": _rate(sum(row["treatment_path_outcome"] == "STOP_FIRST" for row in confirmed), len(confirmed)),
                    "median_rr_delta": _median(confirmed, "rr_delta"),
                    "interpretation_allowed": len(selected) >= 30,
                    "rule_selection_allowed": False,
                }
            )
    return output


def _pilot(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: row["opportunity_id"])
    categories = (
        ("CONFIRMED_CLOSE_GT_OPEN", lambda r: r["treatment_status"] == "CONFIRMED" and Decimal(str(r["first_10m_close"])) > Decimal(str(r["t1_open"]))),
        ("REJECTED_CLOSE_LT_OPEN", lambda r: r["treatment_status"] == "REJECTED"),
        ("CONFIRMED_CLOSE_EQ_OPEN", lambda r: r["treatment_status"] == "CONFIRMED" and Decimal(str(r["first_10m_close"])) == Decimal(str(r["t1_open"]))),
        ("STOP_BEFORE_CONFIRMATION", lambda r: r["treatment_status"] == "PRE_CONFIRMATION_STOP_INVALIDATED"),
        ("TARGET_BEFORE_CONFIRMATION", lambda r: r["treatment_status"] == "PRE_CONFIRMATION_TARGET_REACHED"),
        ("CONFIRMED_RR_IMPROVED", lambda r: r["treatment_status"] == "CONFIRMED" and Decimal(str(r["rr_delta"])) > 0),
        ("CONFIRMED_RR_DEGRADED", lambda r: r["treatment_status"] == "CONFIRMED" and Decimal(str(r["rr_delta"])) < 0),
        ("REJECTED_CONTROL_STOP_FIRST", lambda r: r["treatment_status"] == "REJECTED" and r["control_path_outcome"] == "STOP_FIRST"),
        ("REJECTED_FAVORABLE_CONTROL", lambda r: r["treatment_status"] == "REJECTED" and r["control_favorable"]),
        ("CONFIRMED_CONTROL_STOP_FIRST", lambda r: r["treatment_status"] == "CONFIRMED" and r["control_path_outcome"] == "STOP_FIRST"),
        ("CONFIRMED_CONTROL_TARGET_FIRST", lambda r: r["treatment_status"] == "CONFIRMED" and r["control_path_outcome"] == "TARGET_FIRST"),
        ("DEVELOPMENT_2022", lambda r: r["decision_date"].startswith("2022")),
        ("DEVELOPMENT_2023", lambda r: r["decision_date"].startswith("2023")),
        ("DEVELOPMENT_2024", lambda r: r["decision_date"].startswith("2024")),
    )
    cases = []
    for category, predicate in categories:
        selected = next((row for row in ordered if predicate(row)), None)
        if selected is None:
            cases.append({"category": category, "availability": "NOT_AVAILABLE", "validation_result": "NOT_AVAILABLE"})
            continue
        checks = {
            "development_only": "2022-01-01" <= selected["decision_date"] <= "2024-12-31",
            "t1_open_present": selected.get("t1_open") is not None,
            "first_10m_close_present": selected.get("first_10m_close") is not None,
            "confirmation_status_present": selected["treatment_status"] in TREATMENT_STATUSES,
            "pre_confirmation_path_present": selected.get("pre_confirmation_stop_touched") is not None
            and selected.get("pre_confirmation_target_touched") is not None
            and selected.get("pre_confirmation_ambiguous") is not None,
            "entry_reference_valid": selected["treatment_status"] != "CONFIRMED"
            or selected.get("treatment_entry_reference") == selected.get("first_10m_close"),
            "stop_target_present": selected.get("stop") is not None and selected.get("target") is not None,
            "treatment_rr_when_confirmed": selected["treatment_status"] != "CONFIRMED"
            or selected.get("treatment_rr") is not None,
            "post_confirmation_path_when_confirmed": selected["treatment_status"] != "CONFIRMED"
            or selected.get("treatment_path_outcome") is not None,
            "control_path_present": selected.get("control_path_outcome") is not None,
            "mfe_mae_present": selected.get("control_mfe_r") is not None and selected.get("control_mae_r") is not None,
            "year_assignment": selected["decision_date"][:4] in {"2022", "2023", "2024"},
            "cost_metadata_when_confirmed": selected["treatment_status"] != "CONFIRMED" or selected.get("treatment_cost") is not None,
        }
        cases.append(
            {
                "category": category,
                "availability": "AVAILABLE",
                "opportunity_id": selected["opportunity_id"],
                "symbol": selected["symbol"],
                "decision_date": selected["decision_date"],
                "entry_date": selected["entry_date"],
                "t1_open": selected["t1_open"],
                "first_10m_close": selected["first_10m_close"],
                "treatment_status": selected["treatment_status"],
                "pre_confirmation_stop_touched": selected["pre_confirmation_stop_touched"],
                "pre_confirmation_target_touched": selected["pre_confirmation_target_touched"],
                "pre_confirmation_ambiguous": selected["pre_confirmation_ambiguous"],
                "treatment_entry_reference": selected["treatment_entry_reference"],
                "stop": selected["stop"],
                "target": selected["target"],
                "control_path": selected["control_path_outcome"],
                "treatment_path": selected["treatment_path_outcome"],
                "treatment_rr": selected["treatment_rr"],
                "control_mfe_r": selected["control_mfe_r"],
                "treatment_mfe_r": selected["treatment_mfe_r"],
                "control_mae_r": selected["control_mae_r"],
                "treatment_mae_r": selected["treatment_mae_r"],
                "control_cost": selected["control_cost"],
                "treatment_cost": selected["treatment_cost"],
                "year": int(selected["decision_date"][:4]),
                "checks": checks,
                "validation_result": "PASS" if all(checks.values()) else "FAIL",
            }
        )
    return {
        "case_count": len(cases),
        "available_count": sum(row["availability"] == "AVAILABLE" for row in cases),
        "not_available_count": sum(row["availability"] == "NOT_AVAILABLE" for row in cases),
        "failed_count": sum(row["validation_result"] == "FAIL" for row in cases),
        "passed": all(row["validation_result"] in {"PASS", "NOT_AVAILABLE"} for row in cases),
        "cases": cases,
    }


def _artifact_root(root: Path) -> Path:
    return root / "data/research/experiments/intraday/v1/ten_min_confirmation_rule"


def _report_root(root: Path) -> Path:
    return root / "data/reports"


def run_intraday_confirmation_rule_experiment(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(repo_root)
    notify = progress or (lambda _message: None)
    notify("Verifying frozen baseline, cost, temporal, intraday, and Command 01 hashes")
    before = baseline_snapshot(root)
    population, sources, context, bars = build_population(root)
    population_hash = freeze_population(population)
    artifact_root = _artifact_root(root)
    reports_root = _report_root(root)
    population_manifest = {
        "experiment_id": EXPERIMENT_ID,
        "experiment_version": EXPERIMENT_VERSION,
        "experiment_population_hash": population_hash,
        "row_count": len(population),
        "rows": population,
    }
    population_path = artifact_root / "population_manifest_v1.json"
    _write_json(population_path, population_manifest)
    prereg = build_preregistration(population_hash, preregistration_dependencies(before))
    prereg_path = artifact_root / "registry/intraday_confirmation_rule_registry_v1_preregistered.json"
    _write_json(prereg_path, prereg)
    notify("Population and exact 10m >= open rule frozen before outcome computation")

    matched = _matched_rows(population, sources, context, bars, notify)
    source_metrics = population_metrics(matched, "SOURCE_OPPORTUNITIES")
    admitted_metrics = population_metrics(matched, "FROZEN_ADMITTED_SUBSET")
    yearly = _yearly(matched)
    consistency = temporal_consistency(yearly)
    criteria = falsification_results(source_metrics, yearly, consistency)
    classifications = _classifications(source_metrics, criteria, consistency)
    contexts = _contexts(matched)
    pilot = _pilot(matched)
    development_result = {
        "source_metrics": source_metrics,
        "admitted_metrics": admitted_metrics,
        "yearly": yearly,
        "falsification_results": criteria,
        "classifications": classifications,
    }
    development_result_hash = canonical_hash(development_result)
    freeze = build_experiment_freeze(prereg, development_result_hash)
    freeze_snapshot = freeze.snapshot()
    freeze_path = artifact_root / "experiment_freeze_v1.json"
    _write_json(freeze_path, freeze_snapshot)
    result_fingerprint = canonical_hash(development_result)
    registry = {
        "registry_version": "INTRADAY_CONTROLLED_EXPERIMENT_REGISTRY_V1",
        "experiment_count": 1,
        "experiments": [
            {
                **prereg,
                "status": "COMPLETE",
                "experiment_type": EXPERIMENT_TYPE,
                "development_result_hash": development_result_hash,
                "development_freeze_hash": freeze_snapshot["development_freeze_hash"],
                "result_fingerprint": result_fingerprint,
                "promotion_allowed": False,
                "validation_authorized": False,
            }
        ],
    }
    registry_path = artifact_root / "registry/intraday_confirmation_rule_registry_v1.json"
    result_path = artifact_root / f"runs/{EXPERIMENT_ID}/result.json"
    _write_json(registry_path, registry)
    _write_json(result_path, development_result)

    confirmed = [row for row in matched if row["treatment_status"] == "CONFIRMED"]
    rejected = [row for row in matched if row["treatment_status"] == "REJECTED"]
    cost_rows = [
        {
            "opportunity_id": row["opportunity_id"],
            "symbol": row["symbol"],
            "decision_date": row["decision_date"],
            "control_entry_reference": row["control_entry_reference"],
            "treatment_entry_reference": row["treatment_entry_reference"],
            "control_cost_r": row["control_cost_r"],
            "treatment_cost_r": row["treatment_cost_r"],
            "cost_r_delta": row["cost_r_delta"],
            "control_estimated_round_trip_cost": row["control_cost"]["estimated_round_trip_cost"],
            "treatment_estimated_round_trip_cost": row["treatment_cost"]["estimated_round_trip_cost"],
            "control_gross_to_cost_headroom_r": row["control_cost"]["gross_to_cost_headroom_r"],
            "treatment_gross_to_cost_headroom_r": row["treatment_cost"]["gross_to_cost_headroom_r"],
            "quantity_basis": row["treatment_cost"]["quantity_basis"],
            "cost_model": row["treatment_cost"]["cost_model"],
            "cost_scenario": row["treatment_cost"]["cost_scenario"],
        }
        for row in confirmed
    ]
    report_payloads: tuple[tuple[str, Iterable[Mapping[str, Any]]], ...] = (
        (REPORT_FILENAMES[1], population),
        (REPORT_FILENAMES[2], matched),
        (REPORT_FILENAMES[3], confirmed),
        (REPORT_FILENAMES[4], rejected),
        (REPORT_FILENAMES[5], (source_metrics, admitted_metrics)),
        (REPORT_FILENAMES[6], yearly),
        (REPORT_FILENAMES[7], ({"population": "SOURCE_OPPORTUNITIES", **source_metrics["rr"]}, {"population": "FROZEN_ADMITTED_SUBSET", **admitted_metrics["rr"]})),
        (REPORT_FILENAMES[8], cost_rows),
        (REPORT_FILENAMES[9], contexts),
        (REPORT_FILENAMES[10], pilot["cases"]),
    )
    report_paths: list[Path] = []
    for name, rows in report_payloads:
        path = reports_root / name
        _write_csv(path, rows)
        report_paths.append(path)

    after = baseline_snapshot(root)
    mutation_violations = sum(before.get(key) != after.get(key) for key in before)
    governance = {
        "validation_state": SEALED,
        "validation_run_count": 0,
        "validation_authorized": False,
        "validation_rows_accessed": 0,
        "holdout_performance_exposed": False,
        "rule_promoted": False,
        "best_or_winner_selected": False,
        "optimization_performed": False,
        "five_minute_treatment_run": False,
        "fifteen_minute_treatment_run": False,
        "vwap_filter_used": False,
        "opening_range_filter_used": False,
        "portfolio_rerun_performed": False,
        "strategy_v2_created": False,
        "strategy_v1_modified": False,
        "live_signals": 0,
        "live_orders": 0,
        "broker_order_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
    }
    ignore_checks = {
        "backend_env": _git_ignored(root, "backend/.env"),
        "experiment_registry": _git_ignored(root, registry_path.relative_to(root).as_posix()),
        "experiment_reports": _git_ignored(root, f"data/reports/{REPORT_FILENAMES[0]}"),
        "experiment_csv": _git_ignored(root, f"data/reports/{REPORT_FILENAMES[2]}"),
    }
    summary = {
        "phase": "Step 02 — Controlled Intraday Research",
        "command": COMMAND,
        "experiment_version": EXPERIMENT_VERSION,
        "profile": PROFILE,
        "experiment_id": EXPERIMENT_ID,
        "experiment_type": EXPERIMENT_TYPE,
        "population": {
            "experiment_population_hash": population_hash,
            "source_count": len(population),
            "admitted_count": sum(row["frozen_admitted_flag"] for row in population),
            "development_start": DEFAULT_TEMPORAL_CONFIG.development_start,
            "development_end": DEFAULT_TEMPORAL_CONFIG.development_end,
            "exclusions": context["command_02_exclusions"],
        },
        "pre_registration": {
            "experiment_preregistration_hash": prereg["experiment_preregistration_hash"],
            "parameter_hash": prereg["parameter_hash"],
            "path": str(prereg_path),
        },
        "experiment_freeze": freeze_snapshot,
        "source_metrics": source_metrics,
        "admitted_metrics": admitted_metrics,
        "yearly": yearly,
        "falsification_results": criteria,
        "classifications": classifications,
        "contexts": contexts,
        "pilot": pilot,
        "baseline_regression": {
            "before": before,
            "after": after,
            "baseline_mutation_violations": mutation_violations,
            "all_frozen_hashes_unchanged": mutation_violations == 0,
        },
        "governance": governance,
        "security": {
            "output_ignore_checks": ignore_checks,
            "all_required_outputs_ignored": all(ignore_checks.values()),
            "secrets_logged": False,
            "provider_headers_logged": False,
        },
        "paths": {
            "registry": str(registry_path),
            "experiment_freeze": str(freeze_path),
            "reports": [str(reports_root / name) for name in REPORT_FILENAMES],
            "documentation": str(root / "docs/intraday-confirmation-rule-experiment-v1.md"),
        },
        "tests": {"backend_passed": tests_passed},
        "frontend": {"build_passed": frontend_build_passed, "tile_added": False},
        "runtime_seconds": Decimal(str(time.perf_counter() - started)),
        "storage": {},
        "known_limitations": [
            "The real intraday population is bounded to the frozen 100-symbol DEVELOPMENT scope.",
            "Control MFE/MAE use frozen open risk while treatment MFE/MAE use confirmation-price risk; the R denominators differ.",
            "Trade-level costs reuse frozen Strategy V1 hypothetical quantity and a 5 bps-per-side research assumption; they are metadata, not a portfolio equity curve.",
            "Raw Groww prices remain at rest and are causally rebased in memory to the frozen adjusted daily price basis.",
            "Same-bar stop/target ambiguity is preserved; confirmation references are hypothetical, not executions.",
        ],
        "recommended_next_action": "Review the DEVELOPMENT-only controlled experiment. A later explicit command may consider validation authorization only if governance accepts the gate; do not unseal validation now.",
    }
    summary["ready_for_review"] = (
        tests_passed
        and frontend_build_passed
        and len(population) == 1101
        and mutation_violations == 0
        and pilot["passed"]
        and all(ignore_checks.values())
        and governance["validation_state"] == SEALED
        and governance["validation_run_count"] == 0
    )
    summary_path = reports_root / REPORT_FILENAMES[0]
    _write_json(summary_path, summary)
    report_paths.insert(0, summary_path)
    artifact_paths = (
        population_path,
        prereg_path,
        registry_path,
        result_path,
        freeze_path,
        *report_paths,
    )
    summary["storage"] = _storage(artifact_paths)
    summary["runtime_seconds"] = Decimal(str(time.perf_counter() - started))
    _write_json(summary_path, summary)
    run_manifest_path = artifact_root / "run_manifest_v1.json"
    _write_json(
        run_manifest_path,
        {
            "experiment_id": EXPERIMENT_ID,
            "experiment_version": EXPERIMENT_VERSION,
            "experiment_population_hash": population_hash,
            "experiment_preregistration_hash": prereg["experiment_preregistration_hash"],
            "parameter_hash": prereg["parameter_hash"],
            "development_result_hash": development_result_hash,
            "development_freeze_hash": freeze_snapshot["development_freeze_hash"],
            "report_hashes": {path.name: _file_sha256(path) for path in report_paths},
            "baseline_mutation_violations": mutation_violations,
            "validation_state": SEALED,
            "validation_run_count": 0,
            "ready_for_review": summary["ready_for_review"],
        },
    )
    notify(
        f"Completed isolated 10m experiment in {summary['runtime_seconds']:.2f}s; validation, portfolio, and live paths remained untouched"
    )
    return summary


__all__ = [
    "COMPARATOR",
    "EXPERIMENT_ID",
    "EXPERIMENT_VERSION",
    "FALSIFICATION_CRITERIA",
    "PRIMARY_METRICS",
    "PROFILE",
    "REPORT_FILENAMES",
    "TREATMENT_STATUSES",
    "WINDOW_MINUTES",
    "build_preregistration",
    "build_experiment_freeze",
    "exact_ten_minute_rule",
    "falsification_results",
    "favorable_control_opportunity",
    "freeze_population",
    "mae_band",
    "mfe_band",
    "population_metrics",
    "run_intraday_confirmation_rule_experiment",
    "temporal_consistency",
    "treatment_status",
]
