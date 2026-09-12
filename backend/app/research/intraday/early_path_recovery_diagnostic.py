from __future__ import annotations

import json
import math
import time
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH, default_cost_model_config
from app.research.intraday.confirmation_diagnostic import (
    EXPECTED_DATASET_HASHES,
    _file_sha256,
    _git_ignored,
    _load_bars,
    _path_metrics,
    _population_rows,
    _price_basis_scale,
    _required_session_dates,
    _scale_bars,
    _storage,
    _write_csv,
    _write_json,
    confirmation_rr,
    optional_decimal,
    preconfirmation_touch_state,
    sample_safety,
    validate_development_only,
)
from app.research.intraday.confirmation_rule_experiment import (
    EXPECTED_COMMAND_01_POPULATION_HASH,
    EXPECTED_COMMAND_01_PREREGISTRATION_HASH,
    baseline_snapshot as command_02_baseline_snapshot,
    preregistration_dependencies as command_02_preregistration_dependencies,
)
from app.research.intraday.models import FirstTouch
from app.research.intraday.vwap import calculate_session_vwap
from app.research.temporal_validation.config import DEFAULT_TEMPORAL_CONFIG, SEALED, canonical_hash


DIAGNOSTIC_VERSION = "EARLY_PATH_RECOVERY_DIAGNOSTIC_V1"
PROFILE = "DEVELOPMENT_EARLY_PATH_RECOVERY_V1"
FAMILY = "EARLY_PATH_QUALITY_DIAGNOSTIC"
COMMAND = "Step 02.15 / Command 03"
FIRST_TOUCH_ENGINE = "INTRADAY_FIRST_TOUCH_ENGINE_V1"

EXPECTED_COMMAND_02_POPULATION_HASH = "2781390eeba0c9ed388afaf5f0f88f6995a1230de52ead32dd8744e2719ccb99"
EXPECTED_COMMAND_02_PREREGISTRATION_HASH = "41cf34d866ea3eeaa56f58e7812742636b4f7b242914f652b510a213f3f46276"
EXPECTED_COMMAND_02_PARAMETER_HASH = "5e9dceac2bb2f14dc51b7bb5d4595723aeb070459f9d2bf7ae25237857622c83"
EXPECTED_COMMAND_02_DEVELOPMENT_FREEZE_HASH = "291e142e648e50076d0f9eba70b65e23300f6b88de72bbe0e910fcbf038656a9"
EXPECTED_COMMAND_02_DEVELOPMENT_RESULT_HASH = "e3942f389b7c9203342d1fcaaa6b0ca8c5ad8db4e45900f5a7c0e48f0d1bea4c"

EXPERIMENTS = (
    ("EXP-EARLYPATH-001", "BASELINE_EARLY_PATH_PROFILE"),
    ("EXP-EARLYPATH-002", "FIRST_5M_STATE"),
    ("EXP-EARLYPATH-003", "FIVE_TO_TEN_MIN_RECOVERY"),
    ("EXP-EARLYPATH-004", "TEN_TO_FIFTEEN_MIN_RECOVERY"),
    ("EXP-EARLYPATH-005", "OPEN_RECLAIM_STATE"),
    ("EXP-EARLYPATH-006", "HIGHER_LOW_STRUCTURE"),
    ("EXP-EARLYPATH-007", "EARLY_CLOSE_LOCATION"),
    ("EXP-EARLYPATH-008", "PERSISTENT_STRENGTH_VS_RECOVERY"),
    ("EXP-EARLYPATH-009", "PERSISTENT_WEAKNESS"),
    ("EXP-EARLYPATH-010", "EARLY_PATH_CONTEXT_INTERACTIONS"),
)
EXPERIMENT_IDS = tuple(item[0] for item in EXPERIMENTS)

FIRST5_STATES = ("FIRST5_STRONG", "FIRST5_WEAK", "FIRST5_FLAT")
RECOVERY10_STATES = (
    "RECOVER_BY_10",
    "PARTIAL_RECOVERY_BY_10",
    "PERSISTENT_WEAK_TO_10",
)
RECOVERY15_STATES = (
    "RECOVER_BY_15",
    "PARTIAL_RECOVERY_BY_15",
    "PERSISTENT_WEAK_TO_15",
)
RECLAIM_STATES = (
    "NEVER_BELOW_OPEN_FIRST15",
    "DIP_AND_RECLAIM_BY_10",
    "DIP_AND_RECLAIM_BY_15",
    "BELOW_OPEN_AT_15",
    "MIXED_OPEN_RECLAIM",
)
RECLAIM_TIME_BUCKETS = ("NONE", "5M", "10M", "15M")
RECLAIM_TIME_DEFINITIONS = {
    "NONE": "c1,c2,c3 all < open_0; no completed close at/above open in the first 15m",
    "5M": "c1 >= open_0; the first completed bar is already at/above open (no prior completed 5m close exists)",
    "10M": "c1 < open_0 and c2 >= open_0; first literal completed-close reclaim",
    "15M": "c1 < open_0 and c2 < open_0 and c3 >= open_0; first literal completed-close reclaim",
}
HIGHER_LOW_STATES = ("TWO_STEP_HIGHER_LOW", "ONE_STEP_HIGHER_LOW", "NO_HIGHER_LOW")
CLOSE_LOCATION_BUCKETS = ("LOW_QUARTER", "LOW_MID", "HIGH_MID", "HIGH_QUARTER", "ZERO_RANGE")
PRIMARY_PATH_STATES = (
    "PERSISTENT_STRENGTH_15",
    "RECOVERY_STRENGTH_15",
    "PERSISTENT_WEAKNESS_15",
    "MIXED_EARLY_PATH",
)
POST15_PATHS = ("STOP_FIRST", "TARGET_FIRST", "AMBIGUOUS", "NEITHER")
POPULATIONS = ("SOURCE_OPPORTUNITIES", "FROZEN_ADMITTED_SUBSET")

STATE_DEFINITIONS = {
    "FIRST5_STRONG": "c1 > open_0",
    "FIRST5_WEAK": "c1 < open_0",
    "FIRST5_FLAT": "c1 == open_0 at canonical Decimal precision",
    "RECOVER_BY_10": "FIRST5_WEAK and c2 >= open_0",
    "PARTIAL_RECOVERY_BY_10": "FIRST5_WEAK and c1 < c2 < open_0",
    "PERSISTENT_WEAK_TO_10": "FIRST5_WEAK and c2 <= c1 and c2 < open_0",
    "RECOVER_BY_15": "c2 < open_0 and c3 >= open_0",
    "PARTIAL_RECOVERY_BY_15": "c2 < open_0 and c2 < c3 < open_0",
    "PERSISTENT_WEAK_TO_15": "c2 < open_0 and c3 <= c2 and c3 < open_0",
    "NEVER_BELOW_OPEN_FIRST15": "c1,c2,c3 all >= open_0",
    "DIP_AND_RECLAIM_BY_10": "c1 < open_0 and c2 >= open_0",
    "DIP_AND_RECLAIM_BY_15": "c1 < open_0 and c2 < open_0 and c3 >= open_0",
    "BELOW_OPEN_AT_15": "c3 < open_0",
    "HIGHER_LOW_10": "l2 > l1",
    "HIGHER_LOW_15": "l3 > l2",
    "TWO_STEP_HIGHER_LOW": "l2 > l1 and l3 > l2",
    "ONE_STEP_HIGHER_LOW": "exactly one of l2 > l1 and l3 > l2",
    "NO_HIGHER_LOW": "neither l2 > l1 nor l3 > l2",
    "PERSISTENT_STRENGTH_15": "c1,c2,c3 all >= open_0",
    "RECOVERY_STRENGTH_15": "at least one of c1,c2 is below open_0 and c3 >= open_0",
    "PERSISTENT_WEAKNESS_15": "c1,c2,c3 all < open_0",
    "MIXED_EARLY_PATH": "all other non-overlapping early close sequences",
}

CLASSIFICATION_RULES = {
    "persistent_weakness_promising": "count >=100; control failure enrichment >=10pp; favorable enrichment <=0pp; direction supportive in at least two years",
    "recovery_promising": "both recovery and persistent-weakness cells >=100; recovery failure at least 10pp lower and favorable rate at least 10pp higher; direction supportive in at least two years",
    "higher_low_promising": "two-step and no-higher-low cells >=100; failure at least 5pp lower and favorable rate at least 5pp higher",
    "close_location_promising": "high-quarter and low-quarter cells >=100; failure at least 5pp lower and favorable rate at least 5pp higher",
    "weak_association": "relevant cells >=30 and both directional differences are at least 3pp",
    "later_testing_gate": "one promising concept with candidate-state count >=300, supportive direction in at least two years, no single context dependency, and no VWAP/OR/threshold optimization",
    "sample_safety": {"VERY_SMALL": "<30", "SMALL": "30-99", "LIMITED": "100-299", "ADEQUATE_FOR_DESCRIPTION": ">=300"},
}

REPORT_FILENAMES = (
    "early_path_recovery_v1_summary.json",
    "early_path_recovery_v1_population.csv",
    "early_path_recovery_v1_first5.csv",
    "early_path_recovery_v1_recovery10.csv",
    "early_path_recovery_v1_recovery15.csv",
    "early_path_recovery_v1_reclaim.csv",
    "early_path_recovery_v1_higher_low.csv",
    "early_path_recovery_v1_close_location.csv",
    "early_path_recovery_v1_states.csv",
    "early_path_recovery_v1_contexts.csv",
    "early_path_recovery_v1_yearly.csv",
    "early_path_recovery_v1_pilot.csv",
)


def first5_state(c1: Decimal, open_0: Decimal) -> str:
    if c1 > open_0:
        return "FIRST5_STRONG"
    if c1 < open_0:
        return "FIRST5_WEAK"
    return "FIRST5_FLAT"


def recovery10_state(c1: Decimal, c2: Decimal, open_0: Decimal) -> str:
    if c1 >= open_0:
        return "NOT_APPLICABLE"
    if c2 >= open_0:
        return "RECOVER_BY_10"
    if c2 > c1:
        return "PARTIAL_RECOVERY_BY_10"
    return "PERSISTENT_WEAK_TO_10"


def recovery15_state(c2: Decimal, c3: Decimal, open_0: Decimal) -> str:
    if c2 >= open_0:
        return "NOT_APPLICABLE"
    if c3 >= open_0:
        return "RECOVER_BY_15"
    if c3 > c2:
        return "PARTIAL_RECOVERY_BY_15"
    return "PERSISTENT_WEAK_TO_15"


def open_reclaim_state(c1: Decimal, c2: Decimal, c3: Decimal, open_0: Decimal) -> str:
    if all(value >= open_0 for value in (c1, c2, c3)):
        return "NEVER_BELOW_OPEN_FIRST15"
    if c1 < open_0 and c2 >= open_0:
        return "DIP_AND_RECLAIM_BY_10"
    if c1 < open_0 and c2 < open_0 and c3 >= open_0:
        return "DIP_AND_RECLAIM_BY_15"
    if c3 < open_0:
        return "BELOW_OPEN_AT_15"
    return "MIXED_OPEN_RECLAIM"


def reclaim_time_bucket(c1: Decimal, c2: Decimal, c3: Decimal, open_0: Decimal) -> str:
    if c1 >= open_0:
        return "5M"
    if c2 >= open_0:
        return "10M"
    if c3 >= open_0:
        return "15M"
    return "NONE"


def higher_low_state(l1: Decimal, l2: Decimal, l3: Decimal) -> str:
    first = l2 > l1
    second = l3 > l2
    if first and second:
        return "TWO_STEP_HIGHER_LOW"
    if first != second:
        return "ONE_STEP_HIGHER_LOW"
    return "NO_HIGHER_LOW"


def close_location(close: Decimal, high: Decimal, low: Decimal) -> Decimal | None:
    if high < low or not low <= close <= high:
        raise ValueError("Close location requires low <= close <= high")
    if high == low:
        return None
    return (close - low) / (high - low)


def close_location_bucket(value: Decimal | None) -> str:
    if value is None:
        return "ZERO_RANGE"
    if value < Decimal("0.25"):
        return "LOW_QUARTER"
    if value < Decimal("0.50"):
        return "LOW_MID"
    if value < Decimal("0.75"):
        return "HIGH_MID"
    return "HIGH_QUARTER"


def primary_path_state(c1: Decimal, c2: Decimal, c3: Decimal, open_0: Decimal) -> str:
    if all(value >= open_0 for value in (c1, c2, c3)):
        return "PERSISTENT_STRENGTH_15"
    if any(value < open_0 for value in (c1, c2)) and c3 >= open_0:
        return "RECOVERY_STRENGTH_15"
    if all(value < open_0 for value in (c1, c2, c3)):
        return "PERSISTENT_WEAKNESS_15"
    return "MIXED_EARLY_PATH"


def favorable_control_path(control_path: str, control_mfe_r: Any) -> bool:
    return control_path == "TARGET_FIRST" or Decimal(str(control_mfe_r or 0)) >= Decimal("1.5")


def failure_control_path(control_path: str) -> bool:
    return control_path == "STOP_FIRST"


def _rate(numerator: int, denominator: int) -> Decimal | None:
    return Decimal(numerator) * 100 / Decimal(denominator) if denominator else None


def _values(rows: Sequence[Mapping[str, Any]], field: str) -> list[Decimal]:
    return sorted(
        Decimal(str(row[field]))
        for row in rows
        if row.get(field) is not None and str(row.get(field)) != ""
    )


def _mean(rows: Sequence[Mapping[str, Any]], field: str) -> Decimal | None:
    values = _values(rows, field)
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _median(rows: Sequence[Mapping[str, Any]], field: str) -> Decimal | None:
    values = _values(rows, field)
    if not values:
        return None
    middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


def _percentile(rows: Sequence[Mapping[str, Any]], field: str, probability: Decimal) -> Decimal | None:
    values = _values(rows, field)
    if not values:
        return None
    position = probability * Decimal(len(values) - 1)
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


def _post15_path(value: Any) -> str:
    text = str(value or "")
    if text in {str(FirstTouch.STOP_FIRST), str(FirstTouch.GAP_THROUGH_STOP)}:
        return "STOP_FIRST"
    if text in {str(FirstTouch.TARGET_FIRST), str(FirstTouch.GAP_THROUGH_TARGET)}:
        return "TARGET_FIRST"
    if "AMBIGUOUS" in text:
        return "AMBIGUOUS"
    return "NEITHER"


def _command_02_snapshot(root: Path) -> dict[str, Any]:
    artifact = root / "data/research/experiments/intraday/v1/ten_min_confirmation_rule"
    paths = (
        root / "data/reports/intraday_confirmation_rule_v1_summary.json",
        artifact / "population_manifest_v1.json",
        artifact / "registry/intraday_confirmation_rule_registry_v1_preregistered.json",
        artifact / "registry/intraday_confirmation_rule_registry_v1.json",
        artifact / "runs/EXP-INTRARULE-001/result.json",
        artifact / "experiment_freeze_v1.json",
        artifact / "run_manifest_v1.json",
    )
    if any(not path.exists() for path in paths):
        raise FileNotFoundError("Command 02 frozen artifacts are unavailable")
    summary = json.loads(paths[0].read_text(encoding="utf-8"))
    registry = json.loads(paths[3].read_text(encoding="utf-8"))
    freeze = json.loads(paths[5].read_text(encoding="utf-8"))
    expected = {
        "population_hash": EXPECTED_COMMAND_02_POPULATION_HASH,
        "preregistration_hash": EXPECTED_COMMAND_02_PREREGISTRATION_HASH,
        "parameter_hash": EXPECTED_COMMAND_02_PARAMETER_HASH,
        "development_freeze_hash": EXPECTED_COMMAND_02_DEVELOPMENT_FREEZE_HASH,
        "development_result_hash": EXPECTED_COMMAND_02_DEVELOPMENT_RESULT_HASH,
    }
    observed = {
        "population_hash": summary["population"]["experiment_population_hash"],
        "preregistration_hash": summary["pre_registration"]["experiment_preregistration_hash"],
        "parameter_hash": summary["pre_registration"]["parameter_hash"],
        "development_freeze_hash": freeze["development_freeze_hash"],
        "development_result_hash": freeze["development_result_hash"],
    }
    if observed != expected:
        raise ValueError("Command 02 controlled experiment hashes changed")
    if registry.get("experiment_count") != 1 or [row["experiment_id"] for row in registry["experiments"]] != ["EXP-INTRARULE-001"]:
        raise ValueError("Command 02 controlled experiment registry changed")
    return {
        **observed,
        "experiment_count": 1,
        "experiment_id": "EXP-INTRARULE-001",
        "semantic_hash": canonical_hash(observed),
        "file_hashes": {path.relative_to(root).as_posix(): _file_sha256(path) for path in paths},
    }


def baseline_snapshot(root: Path) -> dict[str, Any]:
    snapshot = command_02_baseline_snapshot(root)
    snapshot["command_02"] = _command_02_snapshot(root)
    if default_cost_model_config().config_hash() != EXPECTED_COST_CONFIG_HASH:
        raise ValueError("Frozen cost-model configuration changed")
    return snapshot


def preregistration_dependencies(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    dependencies = command_02_preregistration_dependencies(snapshot)
    dependencies["command_02"] = {
        key: snapshot["command_02"][key]
        for key in (
            "population_hash",
            "preregistration_hash",
            "parameter_hash",
            "development_freeze_hash",
            "development_result_hash",
            "experiment_count",
            "experiment_id",
            "semantic_hash",
        )
    }
    return dependencies


def build_population(
    root: Path,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]], dict[str, Any], Any]:
    command_population, sources, context = _population_rows(root)
    required_dates = _required_session_dates(command_population, sources)
    bars = _load_bars(root, required_dates)
    output: list[dict[str, Any]] = []
    exclusions = Counter()
    for row in command_population:
        key = (row["symbol"], date.fromisoformat(row["entry_date"]))
        raw = tuple(sorted(bars[5].get(key, ()), key=lambda item: item.bar_start))
        if len(raw) < 3:
            exclusions["FIRST_15M_UNAVAILABLE"] += 1
            continue
        first_three_raw = raw[:3]
        if tuple(item.session_sequence for item in first_three_raw) != (1, 2, 3):
            exclusions["FIRST_15M_NOT_CANONICAL_SEQUENCE"] += 1
            continue
        factor = _price_basis_scale(Decimal(str(row["frozen_next_open"])), raw)
        first_three = _scale_bars(first_three_raw, factor)
        if any(item.is_partial_bar or item.source_bar_count != 1 for item in first_three):
            exclusions["FIRST_15M_PARTIAL_OR_NONCANONICAL"] += 1
            continue
        bar_payload = [
            {
                "bar_number": index,
                "bar_start": item.bar_start,
                "bar_end": item.bar_end,
                "open": item.open,
                "high": item.high,
                "low": item.low,
                "close": item.close,
                "volume": item.volume,
            }
            for index, item in enumerate(first_three, start=1)
        ]
        output.append(
            {
                "opportunity_id": row["opportunity_id"],
                "symbol": row["symbol"],
                "decision_date": row["decision_date"],
                "entry_date": row["entry_date"],
                "score": row["score"],
                "setup_quality": row["setup_quality"],
                "candidate_stage": row["candidate_stage"],
                "regime_state": row["regime_state"],
                "open_0": row["frozen_next_open"],
                "frozen_stop": row["frozen_stop"],
                "frozen_target": row["frozen_target"],
                "frozen_rr": row["frozen_effective_rr"],
                "first_15m_bars": bar_payload,
                "c1": first_three[0].close,
                "c2": first_three[1].close,
                "c3": first_three[2].close,
                "h1": first_three[0].high,
                "h2": first_three[1].high,
                "h3": first_three[2].high,
                "l1": first_three[0].low,
                "l2": first_three[1].low,
                "l3": first_three[2].low,
                "first_15m_completed_at": first_three[2].bar_end,
                "intraday_quality": row["intraday_quality"],
                "CA_safety": row["CA_safety"],
                "frozen_admitted_flag": bool(row["is_admitted"]),
                "price_basis_scale_factor": factor,
                "price_basis_alignment": "CAUSAL_T1_OPEN_RATIO_TO_FROZEN_DAILY_BASIS",
                "causal_source_bar_count": 3,
            }
        )
    validate_development_only(date.fromisoformat(row["decision_date"]) for row in output)
    return output, sources, {**context, "command_03_exclusions": dict(exclusions)}, bars


def freeze_population(rows: Sequence[Mapping[str, Any]]) -> str:
    ordered = sorted((dict(row) for row in rows), key=lambda row: row["opportunity_id"])
    if len({row["opportunity_id"] for row in ordered}) != len(ordered):
        raise ValueError("Early-path population contains duplicate opportunity IDs")
    if any(not ("2022-01-01" <= row["decision_date"] <= "2024-12-31") for row in ordered):
        raise ValueError("Early-path population contains a non-DEVELOPMENT row")
    required = {
        "symbol",
        "entry_date",
        "open_0",
        "frozen_stop",
        "frozen_target",
        "frozen_rr",
        "first_15m_bars",
        "intraday_quality",
        "CA_safety",
        "frozen_admitted_flag",
    }
    if any(required.difference(row) for row in ordered):
        raise ValueError("Early-path population row is missing a frozen field")
    if any(len(row["first_15m_bars"]) != 3 for row in ordered):
        raise ValueError("Early-path population requires exactly three canonical 5m bars")
    if any(row["CA_safety"] != "SAFE" or not str(row["intraday_quality"]).startswith("USABLE_STRICT") for row in ordered):
        raise ValueError("Early-path population contains an unsafe or non-strict row")
    return canonical_hash(ordered)


def build_preregistration(population_hash: str, dependencies: Mapping[str, Any]) -> dict[str, Any]:
    metric_sets = {
        "EXP-EARLYPATH-001": ("population", "year_counts", "state_distributions", "control_paths"),
        "EXP-EARLYPATH-002": ("first5_state", "control_paths", "post15_paths", "mfe", "mae", "favorable_rate"),
        "EXP-EARLYPATH-003": ("recovery10_state", "failure_rate", "favorable_rate", "recovery_value", "post15_quality"),
        "EXP-EARLYPATH-004": ("recovery15_state", "failure_rate", "favorable_rate", "post15_quality"),
        "EXP-EARLYPATH-005": ("open_reclaim_state", "reclaim_time_bucket", "failure_rate", "favorable_rate", "post15_quality"),
        "EXP-EARLYPATH-006": ("higher_low_state", "higher_high_context", "failure_rate", "favorable_rate", "post15_quality"),
        "EXP-EARLYPATH-007": ("early15_close_location", "bar1_close_location", "quartile_buckets", "post15_quality"),
        "EXP-EARLYPATH-008": ("persistent_strength", "recovery_strength", "extension", "diagnostic_rr", "post15_quality"),
        "EXP-EARLYPATH-009": ("persistent_weakness", "population_enrichment", "failure_rate", "favorable_rate", "post15_quality"),
        "EXP-EARLYPATH-010": ("score", "setup", "candidate_stage", "regime", "frozen_rr", "gap", "year"),
    }
    records = []
    for experiment_id, name in EXPERIMENTS:
        parameters = {
            "diagnostic_version": DIAGNOSTIC_VERSION,
            "profile": PROFILE,
            "family": FAMILY,
            "experiment_id": experiment_id,
            "experiment_name": name,
            "population_hash": population_hash,
            "development_start": DEFAULT_TEMPORAL_CONFIG.development_start,
            "development_end": DEFAULT_TEMPORAL_CONFIG.development_end,
            "validation_state": SEALED,
            "validation_run_count": 0,
            "bar_definitions": {"BAR1": "09:15-09:20", "BAR2": "09:20-09:25", "BAR3": "09:25-09:30"},
            "state_definitions": STATE_DEFINITIONS,
            "first5_states": FIRST5_STATES,
            "recovery10_states": RECOVERY10_STATES,
            "recovery15_states": RECOVERY15_STATES,
            "reclaim_states": RECLAIM_STATES,
            "reclaim_time_buckets": RECLAIM_TIME_BUCKETS,
            "reclaim_time_definitions": RECLAIM_TIME_DEFINITIONS,
            "higher_low_states": HIGHER_LOW_STATES,
            "close_location_buckets": CLOSE_LOCATION_BUCKETS,
            "primary_path_states": PRIMARY_PATH_STATES,
            "post15_path_starts": "FIRST_5M_BAR_WITH_BAR_START_AT_OR_AFTER_09:30",
            "first_touch_engine": FIRST_TOUCH_ENGINE,
            "favorable_path": "TARGET_FIRST OR control_MFE_R >= 1.5",
            "failure_path": "control STOP_FIRST",
            "classification_rules": CLASSIFICATION_RULES,
            "no_hypothetical_entry": True,
            "no_rule_creation": True,
            "threshold_optimization_allowed": False,
            "vwap_rule_allowed": False,
            "opening_range_rule_allowed": False,
            "portfolio_rerun_allowed": False,
            "strategy_v2_allowed": False,
        }
        body = {
            "experiment_id": experiment_id,
            "name": name,
            "diagnostic_version": DIAGNOSTIC_VERSION,
            "family": FAMILY,
            "population_hash": population_hash,
            "metrics": metric_sets[experiment_id],
            "baseline_dependencies": dict(dependencies),
            "parameters": parameters,
            "parameter_hash": canonical_hash(parameters),
            "promotion_allowed": False,
            "validation_authorized": False,
            "diagnostic_only": True,
            "pre_registered": True,
        }
        records.append({**body, "pre_registration_hash": canonical_hash(body), "status": "REGISTERED"})
    return {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "profile": PROFILE,
        "family": FAMILY,
        "population_hash": population_hash,
        "experiment_count": len(records),
        "experiment_ids": EXPERIMENT_IDS,
        "experiments": records,
        "definitions_frozen_before_results": True,
        "no_post_result_definition_edits": True,
        "promotion_allowed": False,
        "validation_authorized": False,
        "early_path_preregistration_hash": canonical_hash(records),
    }


def _evaluate_records(
    population: Sequence[Mapping[str, Any]],
    sources: Mapping[str, Mapping[str, Any]],
    bars: Any,
    notify: Callable[[str], None],
) -> list[dict[str, Any]]:
    output = []
    for index, population_row in enumerate(population, start=1):
        source = sources[population_row["opportunity_id"]]
        open_0 = Decimal(str(population_row["open_0"]))
        stop = Decimal(str(population_row["frozen_stop"]))
        target = Decimal(str(population_row["frozen_target"]))
        c1, c2, c3 = (Decimal(str(population_row[name])) for name in ("c1", "c2", "c3"))
        h1, h2, h3 = (Decimal(str(population_row[name])) for name in ("h1", "h2", "h3"))
        l1, l2, l3 = (Decimal(str(population_row[name])) for name in ("l1", "l2", "l3"))
        entry_date = date.fromisoformat(population_row["entry_date"])
        factor = Decimal(str(population_row["price_basis_scale_factor"]))
        first_three = tuple(
            _scale_bars(
                tuple(sorted(bars[5][(population_row["symbol"], entry_date)], key=lambda item: item.bar_start))[:3],
                factor,
            )
        )
        session_dates = [
            date.fromisoformat(str(source[f"session_date_{ordinal}"]))
            for ordinal in range(1, 5)
            if source.get(f"session_date_{ordinal}")
        ]
        all_five = tuple(
            _scale_bars(
                tuple(
                    bar
                    for session_date in session_dates
                    for bar in bars[5].get((population_row["symbol"], session_date), ())
                ),
                factor,
            )
        )
        risk = open_0 - stop
        post = _path_metrics(
            confirmation_price=open_0,
            confirmation_timestamp=first_three[2].bar_end,
            stop=stop,
            target=target,
            risk=risk,
            all_bars=all_five,
            max_holding_date=max(session_dates),
        )
        touch = preconfirmation_touch_state(first_three, stop, target)
        early_high = max(h1, h2, h3)
        early_low = min(l1, l2, l3)
        location15 = close_location(c3, early_high, early_low)
        location5 = close_location(c1, h1, l1)
        path_state = primary_path_state(c1, c2, c3, open_0)
        control_path = _control_path(source)
        control_mfe = optional_decimal(source.get("mfe_r_4"))
        rr15, _rr_risk, _rr_reward = confirmation_rr(c3, stop, target)
        vwap_points = calculate_session_vwap(first_three)
        vwap15 = vwap_points[-1].vwap if vwap_points else None
        extension = (c3 / open_0 - 1) * 100
        record = {
            **dict(population_row),
            "population": "FROZEN_ADMITTED_SUBSET" if population_row["frozen_admitted_flag"] else "SOURCE_ONLY",
            "first5_state": first5_state(c1, open_0),
            "recovery10_state": recovery10_state(c1, c2, open_0),
            "recovery15_state": recovery15_state(c2, c3, open_0),
            "open_reclaim_state": open_reclaim_state(c1, c2, c3, open_0),
            "reclaim_time_bucket": reclaim_time_bucket(c1, c2, c3, open_0),
            "higher_low_10": l2 > l1,
            "higher_low_15": l3 > l2,
            "two_step_higher_low": l2 > l1 and l3 > l2,
            "lower_low_10": l2 < l1,
            "lower_low_15": l3 < l2,
            "higher_low_state": higher_low_state(l1, l2, l3),
            "higher_high_10": h2 > h1,
            "higher_high_15": h3 > h2,
            "early15_high": early_high,
            "early15_low": early_low,
            "early15_close_location": location15,
            "early15_close_location_bucket": close_location_bucket(location15),
            "bar1_close_location": location5,
            "bar1_close_location_bucket": close_location_bucket(location5),
            "primary_path_state": path_state,
            "pre15_stop_touched": touch["stop_touched"],
            "pre15_target_touched": touch["target_touched"],
            "pre15_first_touch": touch["first_touch"],
            "pre15_ambiguous": touch["ambiguous"],
            "control_path": control_path,
            "control_stop_first": failure_control_path(control_path),
            "control_target_first": control_path == "TARGET_FIRST",
            "control_mfe_r": control_mfe,
            "control_mae_r": optional_decimal(source.get("mae_r_4")),
            "favorable_control_path": favorable_control_path(control_path, control_mfe),
            "post15_reference": "FROZEN_T1_OPEN_FOR_PATH_NORMALIZATION_NOT_ENTRY",
            "post15_path": _post15_path(post.get("post_first_touch")),
            "post15_first_touch_timestamp": post.get("post_first_touch_timestamp"),
            "post15_bar_count": post.get("post_confirmation_bar_count"),
            "mfe_post15_r": post.get("mfe_confirm_r"),
            "mae_post15_r": post.get("mae_confirm_r"),
            "price_extension_15m_pct": extension,
            "hypothetical_rr_at_15m": rr15,
            "hypothetical_rr_valid": rr15 is not None,
            "vwap_15m": vwap15,
            "vwap_15m_context": "ABOVE_VWAP" if vwap15 is not None and c3 > vwap15 else "BELOW_VWAP" if vwap15 is not None and c3 < vwap15 else "AT_VWAP" if vwap15 is not None else "VWAP_UNAVAILABLE",
            "daily_gap_pct": optional_decimal(source.get("gap_from_t_close_pct")),
            "daily_gap_band": source.get("gap_category"),
            "unexplained_mismatch_flag": population_row["symbol"] == "SCHAEFFLER" and date(2023, 9, 1) in session_dates,
            "no_hypothetical_entry_assigned": True,
        }
        output.append(record)
        if index % 250 == 0:
            notify(f"Evaluated {index}/{len(population)} causal early-path records")
    return output


def state_profile(
    rows: Sequence[Mapping[str, Any]],
    *,
    field: str,
    states: Sequence[str],
    population: str,
) -> list[dict[str, Any]]:
    selected = list(rows) if population == "SOURCE_OPPORTUNITIES" else [row for row in rows if row["frozen_admitted_flag"]]
    population_failure_rate = _rate(sum(row["control_stop_first"] for row in selected), len(selected))
    population_favorable_rate = _rate(sum(row["favorable_control_path"] for row in selected), len(selected))
    output = []
    for state in states:
        subset = [row for row in selected if row.get(field) == state]
        failures = sum(row["control_stop_first"] for row in subset)
        favorable = sum(row["favorable_control_path"] for row in subset)
        failure_rate = _rate(failures, len(subset))
        favorable_rate = _rate(favorable, len(subset))
        post_counts = Counter(row["post15_path"] for row in subset)
        output.append(
            {
                "population": population,
                "field": field,
                "state": state,
                "count": len(subset),
                "sample_safety": sample_safety(len(subset)),
                "control_stop_first_count": failures,
                "control_stop_first_rate_pct": failure_rate,
                "control_target_first_count": sum(row["control_target_first"] for row in subset),
                "control_target_first_rate_pct": _rate(sum(row["control_target_first"] for row in subset), len(subset)),
                "favorable_count": favorable,
                "favorable_rate_pct": favorable_rate,
                "failure_enrichment_vs_population_pp": failure_rate - population_failure_rate if failure_rate is not None and population_failure_rate is not None else None,
                "favorable_enrichment_vs_population_pp": favorable_rate - population_favorable_rate if favorable_rate is not None and population_favorable_rate is not None else None,
                "median_control_mfe_r": _median(subset, "control_mfe_r"),
                "median_control_mae_r": _median(subset, "control_mae_r"),
                "median_mfe_post15_r": _median(subset, "mfe_post15_r"),
                "median_mae_post15_r": _median(subset, "mae_post15_r"),
                "post15_stop_first_count": post_counts.get("STOP_FIRST", 0),
                "post15_stop_first_rate_pct": _rate(post_counts.get("STOP_FIRST", 0), len(subset)),
                "post15_target_first_count": post_counts.get("TARGET_FIRST", 0),
                "post15_target_first_rate_pct": _rate(post_counts.get("TARGET_FIRST", 0), len(subset)),
                "post15_ambiguous_count": post_counts.get("AMBIGUOUS", 0),
                "post15_neither_count": post_counts.get("NEITHER", 0),
                "mean_price_extension_15m_pct": _mean(subset, "price_extension_15m_pct"),
                "median_price_extension_15m_pct": _median(subset, "price_extension_15m_pct"),
                "p25_price_extension_15m_pct": _percentile(subset, "price_extension_15m_pct", Decimal("0.25")),
                "p75_price_extension_15m_pct": _percentile(subset, "price_extension_15m_pct", Decimal("0.75")),
                "median_hypothetical_rr_at_15m": _median(subset, "hypothetical_rr_at_15m"),
                "mean_hypothetical_rr_at_15m": _mean(subset, "hypothetical_rr_at_15m"),
                "pre15_stop_touch_count": sum(row["pre15_stop_touched"] for row in subset),
                "pre15_target_touch_count": sum(row["pre15_target_touched"] for row in subset),
                "vwap_15m_distribution": dict(sorted(Counter(row["vwap_15m_context"] for row in subset).items())),
                "rule_selection_allowed": False,
            }
        )
    return output


def recovery_value(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    weak = [row for row in rows if row["first5_state"] == "FIRST5_WEAK"]
    recovered = [row for row in weak if row["recovery10_state"] == "RECOVER_BY_10"]
    persistent = [row for row in weak if row["recovery10_state"] == "PERSISTENT_WEAK_TO_10"]
    recovered_failure = _rate(sum(row["control_stop_first"] for row in recovered), len(recovered))
    persistent_failure = _rate(sum(row["control_stop_first"] for row in persistent), len(persistent))
    recovered_favorable = _rate(sum(row["favorable_control_path"] for row in recovered), len(recovered))
    persistent_favorable = _rate(sum(row["favorable_control_path"] for row in persistent), len(persistent))
    return {
        "first5_weak_count": len(weak),
        "recover_by_10_count": len(recovered),
        "persistent_weak_to_10_count": len(persistent),
        "recover_by_10_failure_rate_pct": recovered_failure,
        "persistent_weak_to_10_failure_rate_pct": persistent_failure,
        "persistent_minus_recovered_failure_rate_pp": persistent_failure - recovered_failure if persistent_failure is not None and recovered_failure is not None else None,
        "recover_by_10_favorable_rate_pct": recovered_favorable,
        "persistent_weak_to_10_favorable_rate_pct": persistent_favorable,
        "recovered_minus_persistent_favorable_rate_pp": recovered_favorable - persistent_favorable if recovered_favorable is not None and persistent_favorable is not None else None,
    }


def _profile_map(rows: Sequence[Mapping[str, Any]], field: str, states: Sequence[str]) -> dict[str, dict[str, Any]]:
    return {row["state"]: row for row in state_profile(rows, field=field, states=states, population="SOURCE_OPPORTUNITIES")}


def _yearly(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for year in (2022, 2023, 2024):
        year_rows = [row for row in rows if row["decision_date"].startswith(str(year))]
        profiles = _profile_map(year_rows, "primary_path_state", PRIMARY_PATH_STATES)
        for state in PRIMARY_PATH_STATES:
            output.append({"year": year, **profiles[state]})
    return output


def temporal_consistency(yearly: Sequence[Mapping[str, Any]]) -> str:
    supportive = 0
    inverse = 0
    adequate_years = 0
    for year in (2022, 2023, 2024):
        year_rows = [row for row in yearly if row["year"] == year]
        profile = {row["state"]: row for row in year_rows}
        recovery = profile.get("RECOVERY_STRENGTH_15")
        weakness = profile.get("PERSISTENT_WEAKNESS_15")
        if not recovery or not weakness or min(recovery["count"], weakness["count"]) < 30:
            continue
        adequate_years += 1
        failure_delta = weakness["control_stop_first_rate_pct"] - recovery["control_stop_first_rate_pct"]
        favorable_delta = recovery["favorable_rate_pct"] - weakness["favorable_rate_pct"]
        if failure_delta > 0 and favorable_delta > 0:
            supportive += 1
        elif failure_delta <= 0 and favorable_delta <= 0:
            inverse += 1
    if adequate_years < 2:
        return "INCONCLUSIVE"
    if supportive == 3:
        return "CONSISTENT"
    if supportive >= 2:
        return "MOSTLY_CONSISTENT"
    if inverse >= 2:
        return "INVERSE"
    return "UNSTABLE"


def _result_from_differences(
    *,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    failure_improvement_pp: Decimal,
    favorable_improvement_pp: Decimal,
    strong_minimum: int,
) -> tuple[str, dict[str, Any]]:
    if min(left["count"], right["count"]) < 30:
        return "INCONCLUSIVE", {"reason": "CELL_BELOW_30"}
    failure_delta = Decimal(str(right["control_stop_first_rate_pct"])) - Decimal(str(left["control_stop_first_rate_pct"]))
    favorable_delta = Decimal(str(left["favorable_rate_pct"])) - Decimal(str(right["favorable_rate_pct"]))
    evidence = {
        "left_state": left["state"],
        "right_state": right["state"],
        "left_count": left["count"],
        "right_count": right["count"],
        "failure_improvement_pp": failure_delta,
        "favorable_improvement_pp": favorable_delta,
    }
    if min(left["count"], right["count"]) >= strong_minimum and failure_delta >= failure_improvement_pp and favorable_delta >= favorable_improvement_pp:
        return "PROMISING_FOR_CONTROLLED_TEST", evidence
    if failure_delta >= 3 and favorable_delta >= 3:
        return "WEAK_ASSOCIATION", evidence
    if (failure_delta > 0) != (favorable_delta > 0):
        return "MIXED", evidence
    return "NO_CLEAR_ASSOCIATION", evidence


def classifications(
    rows: Sequence[Mapping[str, Any]],
    state_rows: Sequence[Mapping[str, Any]],
    higher_low_rows: Sequence[Mapping[str, Any]],
    close_rows: Sequence[Mapping[str, Any]],
    yearly: Sequence[Mapping[str, Any]],
    temporal: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    states = {row["state"]: row for row in state_rows if row["population"] == "SOURCE_OPPORTUNITIES"}
    higher = {row["state"]: row for row in higher_low_rows if row["population"] == "SOURCE_OPPORTUNITIES"}
    locations = {row["state"]: row for row in close_rows if row["population"] == "SOURCE_OPPORTUNITIES"}
    population_failure = _rate(sum(row["control_stop_first"] for row in rows), len(rows))
    population_favorable = _rate(sum(row["favorable_control_path"] for row in rows), len(rows))
    weakness = states["PERSISTENT_WEAKNESS_15"]
    year_weak_support = 0
    for year in (2022, 2023, 2024):
        yearly_map = {row["state"]: row for row in yearly if row["year"] == year}
        weak_year = yearly_map["PERSISTENT_WEAKNESS_15"]
        year_source = [row for row in rows if row["decision_date"].startswith(str(year))]
        year_failure = _rate(sum(row["control_stop_first"] for row in year_source), len(year_source))
        year_favorable = _rate(sum(row["favorable_control_path"] for row in year_source), len(year_source))
        if weak_year["count"] >= 30 and weak_year["control_stop_first_rate_pct"] > year_failure and weak_year["favorable_rate_pct"] < year_favorable:
            year_weak_support += 1
    weak_failure_enrichment = weakness["control_stop_first_rate_pct"] - population_failure
    weak_favorable_enrichment = weakness["favorable_rate_pct"] - population_favorable
    if weakness["count"] >= 100 and weak_failure_enrichment >= 10 and weak_favorable_enrichment <= 0 and year_weak_support >= 2:
        weakness_result = "PROMISING_FOR_CONTROLLED_TEST"
    elif weakness["count"] >= 30 and weak_failure_enrichment >= 5 and weak_favorable_enrichment < 0:
        weakness_result = "WEAK_ASSOCIATION"
    elif (weak_failure_enrichment > 0) != (weak_favorable_enrichment < 0):
        weakness_result = "MIXED"
    else:
        weakness_result = "NO_CLEAR_ASSOCIATION"
    recovery_result, recovery_evidence = _result_from_differences(
        left=states["RECOVERY_STRENGTH_15"],
        right=weakness,
        failure_improvement_pp=Decimal("10"),
        favorable_improvement_pp=Decimal("10"),
        strong_minimum=100,
    )
    if recovery_result == "PROMISING_FOR_CONTROLLED_TEST" and temporal not in {"CONSISTENT", "MOSTLY_CONSISTENT"}:
        recovery_result = "WEAK_ASSOCIATION" if temporal != "INVERSE" else "MIXED"
    higher_result, higher_evidence = _result_from_differences(
        left=higher["TWO_STEP_HIGHER_LOW"],
        right=higher["NO_HIGHER_LOW"],
        failure_improvement_pp=Decimal("5"),
        favorable_improvement_pp=Decimal("5"),
        strong_minimum=100,
    )
    close_result, close_evidence = _result_from_differences(
        left=locations["HIGH_QUARTER"],
        right=locations["LOW_QUARTER"],
        failure_improvement_pp=Decimal("5"),
        favorable_improvement_pp=Decimal("5"),
        strong_minimum=100,
    )
    results = {
        "PERSISTENT_WEAKNESS_RESULT": weakness_result,
        "RECOVERY_STATE_RESULT": recovery_result,
        "HIGHER_LOW_RESULT": higher_result,
        "EARLY_CLOSE_LOCATION_RESULT": close_result,
        "EARLY_PATH_TEMPORAL_CONSISTENCY": temporal,
    }
    def yearly_pair_support(field: str, states_for_field: Sequence[str], left_state: str, right_state: str) -> int:
        support = 0
        for year in (2022, 2023, 2024):
            year_rows = [row for row in rows if row["decision_date"].startswith(str(year))]
            profiles = _profile_map(year_rows, field, states_for_field)
            left = profiles[left_state]
            right = profiles[right_state]
            if (
                min(left["count"], right["count"]) >= 30
                and left["control_stop_first_rate_pct"] < right["control_stop_first_rate_pct"]
                and left["favorable_rate_pct"] > right["favorable_rate_pct"]
            ):
                support += 1
        return support

    def context_spread(field: str, state: str) -> bool:
        selected = [row for row in rows if row[field] == state]
        if not selected:
            return False
        for context_field in ("setup_quality", "candidate_stage", "regime_state", "decision_date"):
            values = Counter(
                row[context_field][:4]
                if context_field == "decision_date"
                else str(row.get(context_field) or "UNAVAILABLE")
                for row in selected
            )
            if len(values) < 2 or max(values.values()) == len(selected):
                return False
        return True

    concept_evidence = {
        "persistent_weakness": {
            "result": weakness_result,
            "count": weakness["count"],
            "supportive_year_count": year_weak_support,
            "not_entirely_driven_by_one_subgroup": context_spread("primary_path_state", "PERSISTENT_WEAKNESS_15"),
        },
        "recovery": {
            "result": recovery_result,
            "count": states["RECOVERY_STRENGTH_15"]["count"],
            "supportive_year_count": yearly_pair_support("primary_path_state", PRIMARY_PATH_STATES, "RECOVERY_STRENGTH_15", "PERSISTENT_WEAKNESS_15"),
            "not_entirely_driven_by_one_subgroup": context_spread("primary_path_state", "RECOVERY_STRENGTH_15"),
        },
        "higher_low": {
            "result": higher_result,
            "count": higher["TWO_STEP_HIGHER_LOW"]["count"],
            "supportive_year_count": yearly_pair_support("higher_low_state", HIGHER_LOW_STATES, "TWO_STEP_HIGHER_LOW", "NO_HIGHER_LOW"),
            "not_entirely_driven_by_one_subgroup": context_spread("higher_low_state", "TWO_STEP_HIGHER_LOW"),
        },
        "close_location": {
            "result": close_result,
            "count": locations["HIGH_QUARTER"]["count"],
            "supportive_year_count": yearly_pair_support("early15_close_location_bucket", CLOSE_LOCATION_BUCKETS, "HIGH_QUARTER", "LOW_QUARTER"),
            "not_entirely_driven_by_one_subgroup": context_spread("early15_close_location_bucket", "HIGH_QUARTER"),
        },
    }
    promising_states = []
    if weakness_result == "PROMISING_FOR_CONTROLLED_TEST":
        promising_states.append(weakness)
    if recovery_result == "PROMISING_FOR_CONTROLLED_TEST":
        promising_states.append(states["RECOVERY_STRENGTH_15"])
    if higher_result == "PROMISING_FOR_CONTROLLED_TEST":
        promising_states.append(higher["TWO_STEP_HIGHER_LOW"])
    if close_result == "PROMISING_FOR_CONTROLLED_TEST":
        promising_states.append(locations["HIGH_QUARTER"])
    eligible_concepts = [
        value
        for value in concept_evidence.values()
        if value["result"] == "PROMISING_FOR_CONTROLLED_TEST"
        and value["count"] >= 300
        and value["supportive_year_count"] >= 2
        and value["not_entirely_driven_by_one_subgroup"]
    ]
    later = bool(eligible_concepts)
    individual = (weakness_result, recovery_result, higher_result, close_result)
    overall = (
        "SUPPORTED_FOR_CONTROLLED_TEST"
        if later
        else "WEAKLY_SUPPORTED"
        if "PROMISING_FOR_CONTROLLED_TEST" in individual
        else "MIXED"
        if "MIXED" in individual or "WEAK_ASSOCIATION" in individual
        else "NOT_SUPPORTED"
        if all(value == "NO_CLEAR_ASSOCIATION" for value in individual)
        else "INCONCLUSIVE"
    )
    results["EARLY_PATH_RECOVERY_DIAGNOSTIC_RESULT"] = overall
    results["EARLY_PATH_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING"] = "YES" if later else "NO"
    evidence = {
        "population_failure_rate_pct": population_failure,
        "population_favorable_rate_pct": population_favorable,
        "persistent_weakness": {
            "count": weakness["count"],
            "failure_enrichment_pp": weak_failure_enrichment,
            "favorable_enrichment_pp": weak_favorable_enrichment,
            "supportive_year_count": year_weak_support,
        },
        "recovery": recovery_evidence,
        "higher_low": higher_evidence,
        "close_location": close_evidence,
        "later_gate": {
            "promising_concept_count": len(promising_states),
            "adequate_candidate_state": any(row["count"] >= 300 for row in promising_states),
            "supportive_more_than_one_year": any(value["supportive_year_count"] >= 2 for value in concept_evidence.values() if value["result"] == "PROMISING_FOR_CONTROLLED_TEST"),
            "not_entirely_driven_by_one_subgroup": any(value["not_entirely_driven_by_one_subgroup"] for value in concept_evidence.values() if value["result"] == "PROMISING_FOR_CONTROLLED_TEST"),
            "eligible_concept_count": len(eligible_concepts),
            "concepts": concept_evidence,
            "depends_on_vwap_or_opening_range": False,
            "threshold_optimization_performed": False,
            "equivalent_to_10m_close_ge_open_rule": False,
        },
    }
    return results, evidence


def _context_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    dimensions = (
        ("score", lambda row: "SCORE_80_85" if 80 <= int(row["score"]) <= 85 else "OTHER_FROZEN_SCORE"),
        ("setup", lambda row: str(row.get("setup_quality") or "UNAVAILABLE")),
        ("candidate_stage", lambda row: str(row.get("candidate_stage") or "UNAVAILABLE")),
        ("regime", lambda row: str(row.get("regime_state") or "UNAVAILABLE")),
        ("frozen_rr", lambda row: "RR_LT_2" if Decimal(str(row["frozen_rr"])) < 2 else "RR_2_TO_LT_2_5" if Decimal(str(row["frozen_rr"])) < Decimal("2.5") else "RR_GE_2_5"),
        ("gap", lambda row: str(row.get("daily_gap_band") or "UNAVAILABLE")),
        ("year", lambda row: row["decision_date"][:4]),
    )
    output = []
    for dimension, resolver in dimensions:
        groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[(resolver(row), row["primary_path_state"])].append(row)
        for (value, state), selected in sorted(groups.items()):
            output.append(
                {
                    "dimension": dimension,
                    "value": value,
                    "state": state,
                    "count": len(selected),
                    "sample_safety": sample_safety(len(selected)),
                    "failure_rate_pct": _rate(sum(row["control_stop_first"] for row in selected), len(selected)),
                    "favorable_rate_pct": _rate(sum(row["favorable_control_path"] for row in selected), len(selected)),
                    "median_mfe_post15_r": _median(selected, "mfe_post15_r"),
                    "median_mae_post15_r": _median(selected, "mae_post15_r"),
                    "rule_selection_allowed": False,
                }
            )
    return output


def _pilot(rows: Sequence[Mapping[str, Any]], state_counts: Mapping[str, int]) -> dict[str, Any]:
    categories = (
        ("FIRST5_STRONG", lambda row: row["first5_state"] == "FIRST5_STRONG"),
        ("FIRST5_WEAK", lambda row: row["first5_state"] == "FIRST5_WEAK"),
        ("DIP_AND_RECLAIM_BY_10", lambda row: row["open_reclaim_state"] == "DIP_AND_RECLAIM_BY_10"),
        ("DIP_AND_RECLAIM_BY_15", lambda row: row["open_reclaim_state"] == "DIP_AND_RECLAIM_BY_15"),
        ("PERSISTENT_WEAKNESS_15", lambda row: row["primary_path_state"] == "PERSISTENT_WEAKNESS_15"),
        ("PERSISTENT_STRENGTH_15", lambda row: row["primary_path_state"] == "PERSISTENT_STRENGTH_15"),
        ("TWO_STEP_HIGHER_LOW", lambda row: row["higher_low_state"] == "TWO_STEP_HIGHER_LOW"),
        ("LOWER_LOW_PROGRESSION", lambda row: row["lower_low_10"] and row["lower_low_15"]),
        ("HIGH_QUARTER_CLOSE_LOCATION", lambda row: row["early15_close_location_bucket"] == "HIGH_QUARTER"),
        ("LOW_QUARTER_CLOSE_LOCATION", lambda row: row["early15_close_location_bucket"] == "LOW_QUARTER"),
        ("RECOVERED_FAVORABLE_CONTROL", lambda row: row["primary_path_state"] == "RECOVERY_STRENGTH_15" and row["favorable_control_path"]),
        ("RECOVERED_STOP_FIRST", lambda row: row["primary_path_state"] == "RECOVERY_STRENGTH_15" and row["control_stop_first"]),
        ("PERSISTENT_WEAKNESS_STOP_FIRST", lambda row: row["primary_path_state"] == "PERSISTENT_WEAKNESS_15" and row["control_stop_first"]),
        ("PERSISTENT_WEAKNESS_FAVORABLE", lambda row: row["primary_path_state"] == "PERSISTENT_WEAKNESS_15" and row["favorable_control_path"]),
    )
    ordered = sorted(rows, key=lambda row: row["opportunity_id"])
    cases = []
    for category, predicate in categories:
        selected = next((row for row in ordered if predicate(row)), None)
        if selected is None:
            cases.append({"category": category, "availability": "NOT_AVAILABLE", "validation_result": "NOT_AVAILABLE"})
            continue
        bars = selected["first_15m_bars"]
        checks = {
            "development_only": "2022-01-01" <= selected["decision_date"] <= "2024-12-31",
            "open_present": selected.get("open_0") is not None,
            "three_causal_bars": len(bars) == 3 and selected["causal_source_bar_count"] == 3,
            "ohlc_present": all(all(bar.get(field) is not None for field in ("high", "low", "close")) for bar in bars),
            "state_assignment_reproducible": selected["primary_path_state"] == primary_path_state(Decimal(str(selected["c1"])), Decimal(str(selected["c2"])), Decimal(str(selected["c3"])), Decimal(str(selected["open_0"]))),
            "reclaim_present": selected["reclaim_time_bucket"] in RECLAIM_TIME_BUCKETS,
            "higher_low_present": selected["higher_low_state"] in HIGHER_LOW_STATES,
            "close_location_present": selected["early15_close_location_bucket"] in CLOSE_LOCATION_BUCKETS,
            "control_path_present": selected["control_path"] in POST15_PATHS,
            "post15_path_present": selected["post15_path"] in POST15_PATHS,
            "mfe_mae_present": selected["control_mfe_r"] is not None and selected["control_mae_r"] is not None and selected["mfe_post15_r"] is not None and selected["mae_post15_r"] is not None,
            "year_present": selected["decision_date"][:4] in {"2022", "2023", "2024"},
            "sample_bucket_reproducible": sample_safety(state_counts[selected["primary_path_state"]]) in {"VERY_SMALL", "SMALL", "LIMITED", "ADEQUATE_FOR_DESCRIPTION"},
        }
        cases.append(
            {
                "category": category,
                "availability": "AVAILABLE",
                "opportunity_id": selected["opportunity_id"],
                "symbol": selected["symbol"],
                "decision_date": selected["decision_date"],
                "entry_date": selected["entry_date"],
                "open_0": selected["open_0"],
                "c1": selected["c1"],
                "c2": selected["c2"],
                "c3": selected["c3"],
                "h1": selected["h1"],
                "h2": selected["h2"],
                "h3": selected["h3"],
                "l1": selected["l1"],
                "l2": selected["l2"],
                "l3": selected["l3"],
                "primary_path_state": selected["primary_path_state"],
                "reclaim_time_bucket": selected["reclaim_time_bucket"],
                "higher_low_state": selected["higher_low_state"],
                "early15_close_location": selected["early15_close_location"],
                "early15_close_location_bucket": selected["early15_close_location_bucket"],
                "control_path": selected["control_path"],
                "post15_path": selected["post15_path"],
                "control_mfe_r": selected["control_mfe_r"],
                "control_mae_r": selected["control_mae_r"],
                "mfe_post15_r": selected["mfe_post15_r"],
                "mae_post15_r": selected["mae_post15_r"],
                "year": int(selected["decision_date"][:4]),
                "sample_bucket": sample_safety(state_counts[selected["primary_path_state"]]),
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
    return root / "data/research/diagnostics/intraday/v1/early_path_command_03"


def run_early_path_recovery_diagnostic(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    root = Path(repo_root)
    notify = progress or (lambda _message: None)
    notify("Verifying frozen foundations through Command 02")
    before = baseline_snapshot(root)
    population, sources, context, bars = build_population(root)
    population_hash = freeze_population(population)
    artifact_root = _artifact_root(root)
    report_root = root / "data/reports"
    population_manifest = {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "early_path_population_hash": population_hash,
        "row_count": len(population),
        "rows": population,
    }
    population_path = artifact_root / "population_manifest_v1.json"
    _write_json(population_path, population_manifest)
    prereg = build_preregistration(population_hash, preregistration_dependencies(before))
    prereg_path = artifact_root / "registry/early_path_recovery_registry_v1_preregistered.json"
    _write_json(prereg_path, prereg)
    notify("Population and all early-path state definitions frozen before outcome computation")

    records = _evaluate_records(population, sources, bars, notify)
    profiles: dict[str, list[dict[str, Any]]] = {}
    specs = {
        "first5": ("first5_state", FIRST5_STATES),
        "recovery10": ("recovery10_state", RECOVERY10_STATES),
        "recovery15": ("recovery15_state", RECOVERY15_STATES),
        "reclaim": ("open_reclaim_state", RECLAIM_STATES),
        "higher_low": ("higher_low_state", HIGHER_LOW_STATES),
        "close_location": ("early15_close_location_bucket", CLOSE_LOCATION_BUCKETS),
        "states": ("primary_path_state", PRIMARY_PATH_STATES),
    }
    for name, (field, states) in specs.items():
        profiles[name] = [
            profile
            for population_name in POPULATIONS
            for profile in state_profile(records, field=field, states=states, population=population_name)
        ]
    source_states = [row for row in profiles["states"] if row["population"] == "SOURCE_OPPORTUNITIES"]
    state_counts = {row["state"]: row["count"] for row in source_states}
    yearly = _yearly(records)
    temporal = temporal_consistency(yearly)
    class_results, class_evidence = classifications(
        records,
        profiles["states"],
        profiles["higher_low"],
        profiles["close_location"],
        yearly,
        temporal,
    )
    central_recovery = recovery_value(records)
    contexts = _context_rows(records)
    pilot = _pilot(records, state_counts)
    if not pilot["passed"]:
        raise ValueError("Early-path real-case pilot validation failed")

    mismatch_rows = [row for row in records if row["unexplained_mismatch_flag"]]
    mismatch_sensitivity = {
        "known_session": "SCHAEFFLER|2023-09-01",
        "entered_population": bool(mismatch_rows),
        "affected_opportunity_ids": [row["opportunity_id"] for row in mismatch_rows],
        "with_observation": recovery_value(records),
        "without_observation": recovery_value([row for row in records if not row["unexplained_mismatch_flag"]]),
        "classification_tuned_around_observation": False,
    }
    source_vs_admitted = [
        {
            "state": source["state"],
            "source_count": source["count"],
            "admitted_count": admitted["count"],
            "source_failure_rate_pct": source["control_stop_first_rate_pct"],
            "admitted_failure_rate_pct": admitted["control_stop_first_rate_pct"],
            "source_favorable_rate_pct": source["favorable_rate_pct"],
            "admitted_favorable_rate_pct": admitted["favorable_rate_pct"],
        }
        for source, admitted in zip(
            [row for row in profiles["states"] if row["population"] == "SOURCE_OPPORTUNITIES"],
            [row for row in profiles["states"] if row["population"] == "FROZEN_ADMITTED_SUBSET"],
            strict=True,
        )
    ]

    baseline_profile = {
        "source_count": len(records),
        "admitted_count": sum(row["frozen_admitted_flag"] for row in records),
        "year_counts": dict(sorted(Counter(row["decision_date"][:4] for row in records).items())),
        "first5_distribution": dict(sorted(Counter(row["first5_state"] for row in records).items())),
        "primary_state_distribution": dict(sorted(Counter(row["primary_path_state"] for row in records).items())),
        "score_distribution": dict(sorted(Counter(str(row["score"]) for row in records).items())),
        "setup_distribution": dict(sorted(Counter(str(row["setup_quality"]) for row in records).items())),
        "candidate_stage_distribution": dict(sorted(Counter(str(row["candidate_stage"]) for row in records).items())),
        "regime_distribution": dict(sorted(Counter(str(row["regime_state"]) for row in records).items())),
        "control_path_distribution": dict(sorted(Counter(row["control_path"] for row in records).items())),
    }
    experiment_results = {
        "EXP-EARLYPATH-001": baseline_profile,
        "EXP-EARLYPATH-002": profiles["first5"],
        "EXP-EARLYPATH-003": {"profiles": profiles["recovery10"], "recovery_value": central_recovery},
        "EXP-EARLYPATH-004": profiles["recovery15"],
        "EXP-EARLYPATH-005": profiles["reclaim"],
        "EXP-EARLYPATH-006": profiles["higher_low"],
        "EXP-EARLYPATH-007": profiles["close_location"],
        "EXP-EARLYPATH-008": profiles["states"],
        "EXP-EARLYPATH-009": {"persistent_weakness": next(row for row in source_states if row["state"] == "PERSISTENT_WEAKNESS_15"), "classification": class_results["PERSISTENT_WEAKNESS_RESULT"]},
        "EXP-EARLYPATH-010": contexts,
    }
    result_paths: list[Path] = [population_path, prereg_path]
    for experiment_id in EXPERIMENT_IDS:
        path = artifact_root / f"runs/{experiment_id}/result.json"
        result = experiment_results[experiment_id]
        _write_json(
            path,
            {
                "experiment_id": experiment_id,
                "diagnostic_only": True,
                "promotion_allowed": False,
                "population_hash": population_hash,
                "result": result,
                "result_fingerprint": canonical_hash(result),
                "status": "COMPLETE",
            },
        )
        result_paths.append(path)
    registry = {
        **prereg,
        "experiments": [
            {
                **row,
                "status": "COMPLETE",
                "result_fingerprint": canonical_hash(experiment_results[row["experiment_id"]]),
            }
            for row in prereg["experiments"]
        ],
    }
    registry_path = artifact_root / "registry/early_path_recovery_registry_v1.json"
    _write_json(registry_path, registry)
    result_paths.append(registry_path)

    report_payloads: dict[str, Iterable[Mapping[str, Any]]] = {
        REPORT_FILENAMES[1]: population,
        REPORT_FILENAMES[2]: profiles["first5"],
        REPORT_FILENAMES[3]: profiles["recovery10"],
        REPORT_FILENAMES[4]: profiles["recovery15"],
        REPORT_FILENAMES[5]: profiles["reclaim"],
        REPORT_FILENAMES[6]: profiles["higher_low"],
        REPORT_FILENAMES[7]: profiles["close_location"],
        REPORT_FILENAMES[8]: profiles["states"],
        REPORT_FILENAMES[9]: contexts,
        REPORT_FILENAMES[10]: yearly,
        REPORT_FILENAMES[11]: pilot["cases"],
    }
    report_paths = []
    for name, payload in report_payloads.items():
        path = report_root / name
        _write_csv(path, payload)
        report_paths.append(path)

    after = baseline_snapshot(root)
    mutation_violations = sum(before.get(key) != after.get(key) for key in before)
    governance = {
        "rule_created": False,
        "winner_selected": False,
        "optimization_performed": False,
        "portfolio_rerun_performed": False,
        "validation_state": SEALED,
        "validation_authorized": False,
        "validation_run_count": 0,
        "validation_rows_accessed": 0,
        "holdout_performance_exposed": False,
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
        "diagnostic_registry": _git_ignored(root, registry_path.relative_to(root).as_posix()),
        "diagnostic_summary": _git_ignored(root, f"data/reports/{REPORT_FILENAMES[0]}"),
        "diagnostic_csv": _git_ignored(root, f"data/reports/{REPORT_FILENAMES[8]}"),
    }
    summary = {
        "phase": "Step 02 — Controlled Intraday Research",
        "command": COMMAND,
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "profile": PROFILE,
        "family": FAMILY,
        "real_data_source": "GROWW_OFFICIAL_API",
        "population": {
            "early_path_population_hash": population_hash,
            "source_count": len(population),
            "admitted_count": sum(row["frozen_admitted_flag"] for row in population),
            "development_start": DEFAULT_TEMPORAL_CONFIG.development_start,
            "development_end": DEFAULT_TEMPORAL_CONFIG.development_end,
            "selected_symbol_count": len(context["selected_symbols"]),
            "total_development_opportunities": context["total_development_opportunities"],
            "selected_scope_coverage_pct": Decimal(len(population)) * 100 / Decimal(context["total_development_opportunities"]),
            "exclusions": context["command_03_exclusions"],
        },
        "pre_registration": {
            "early_path_preregistration_hash": prereg["early_path_preregistration_hash"],
            "experiment_count": len(EXPERIMENT_IDS),
            "experiment_ids": EXPERIMENT_IDS,
            "path": str(prereg_path),
        },
        "baseline_profile": baseline_profile,
        "profiles": profiles,
        "recovery_value": central_recovery,
        "yearly": yearly,
        "contexts": contexts,
        "source_vs_admitted": source_vs_admitted,
        "mismatch_sensitivity": mismatch_sensitivity,
        "classifications": class_results,
        "classification_evidence": class_evidence,
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
            "order_apis_used": False,
        },
        "paths": {
            "registry": str(registry_path),
            "preregistration_registry": str(prereg_path),
            "reports": [str(report_root / name) for name in REPORT_FILENAMES],
            "documentation": str(root / "docs/early-path-recovery-diagnostic-v1.md"),
        },
        "tests": {"backend_passed": tests_passed},
        "frontend": {"build_passed": frontend_build_passed, "tile_added": False},
        "runtime_seconds": Decimal(str(time.perf_counter() - started)),
        "storage": {},
        "known_limitations": [
            "The frozen 100-symbol scope covers exactly 53.2398% of the current 2,068-row DEVELOPMENT opportunity denominator (previous planning language rounded this to about 53.7%) and is not whole-universe proof.",
            "All empirical associations are DEVELOPMENT-only and have no holdout confirmation.",
            "Post15 MFE/MAE use the frozen T+1-open risk denominator to characterize remaining path; no delayed entry is assigned.",
            "Intrabar stop/target ordering ambiguity is preserved.",
            "The known SCHAEFFLER daily mismatch is flagged and evaluated through deterministic omit-one sensitivity.",
            "Context cells can be small and are descriptive only; no subgroup rule may be selected.",
        ],
        "recommended_next_action": "Review whether any path-shape concept merits a separately preregistered isolated controlled test. Do not create a rule or unseal validation from this diagnostic.",
    }
    summary["ready_for_review"] = (
        tests_passed
        and frontend_build_passed
        and len(population) == 1101
        and len(EXPERIMENT_IDS) == 10
        and pilot["passed"]
        and mutation_violations == 0
        and all(ignore_checks.values())
        and governance["validation_state"] == SEALED
        and governance["validation_run_count"] == 0
    )
    summary_path = report_root / REPORT_FILENAMES[0]
    _write_json(summary_path, summary)
    report_paths.insert(0, summary_path)
    summary["storage"] = _storage([*result_paths, *report_paths])
    summary["runtime_seconds"] = Decimal(str(time.perf_counter() - started))
    _write_json(summary_path, summary)
    run_manifest_path = artifact_root / "run_manifest_v1.json"
    _write_json(
        run_manifest_path,
        {
            "diagnostic_version": DIAGNOSTIC_VERSION,
            "profile": PROFILE,
            "early_path_population_hash": population_hash,
            "early_path_preregistration_hash": prereg["early_path_preregistration_hash"],
            "experiment_count": len(EXPERIMENT_IDS),
            "experiment_ids": EXPERIMENT_IDS,
            "result_fingerprints": {
                experiment_id: canonical_hash(experiment_results[experiment_id])
                for experiment_id in EXPERIMENT_IDS
            },
            "report_hashes": {path.name: _file_sha256(path) for path in report_paths},
            "baseline_mutation_violations": mutation_violations,
            "validation_state": SEALED,
            "validation_run_count": 0,
            "ready_for_review": summary["ready_for_review"],
        },
    )
    notify(
        f"Completed early-path diagnostic in {summary['runtime_seconds']:.2f}s; no rule, portfolio, validation, or live path was created"
    )
    return summary


__all__ = [
    "CLOSE_LOCATION_BUCKETS",
    "DIAGNOSTIC_VERSION",
    "EXPERIMENT_IDS",
    "EXPERIMENTS",
    "FAMILY",
    "FIRST5_STATES",
    "HIGHER_LOW_STATES",
    "PRIMARY_PATH_STATES",
    "PROFILE",
    "RECOVERY10_STATES",
    "RECOVERY15_STATES",
    "RECLAIM_STATES",
    "RECLAIM_TIME_BUCKETS",
    "RECLAIM_TIME_DEFINITIONS",
    "REPORT_FILENAMES",
    "STATE_DEFINITIONS",
    "build_preregistration",
    "classifications",
    "close_location",
    "close_location_bucket",
    "favorable_control_path",
    "failure_control_path",
    "first5_state",
    "freeze_population",
    "higher_low_state",
    "open_reclaim_state",
    "primary_path_state",
    "reclaim_time_bucket",
    "recovery10_state",
    "recovery15_state",
    "recovery_value",
    "run_early_path_recovery_diagnostic",
    "state_profile",
    "temporal_consistency",
]
