from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
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
    FAMILY_VERSION,
    HOLDING_SESSIONS,
    MAX_CONCURRENT_POSITIONS,
    STARTING_CAPITAL,
    TARGET_NOTIONAL_FRACTION,
    _load_adjusted_bars,
    _load_aliases,
    _load_membership,
    _load_sessions,
)
from app.research.strategy.family_c_c001_attribution_audit import (
    EXPECTED_C001_RESULT_HASH,
    EXPECTED_DEVELOPMENT_REGISTRY_HASH,
    build_event_cohort,
    cohort_metrics,
    metric_difference,
)
from app.research.strategy.family_c_c001_implementation_research import (
    EXPECTED_ATTRIBUTION_HASH,
    EXPERIMENT_ID,
    EXPERIMENT_NAME,
    ORIGINAL_RANKING,
    REFERENCE_EXPERIMENT_ID,
    TREATMENT_RANKING,
    build_c001_signal_set,
    verify_signal_set_identity,
)
from app.research.strategy.family_c_development_evaluation import (
    COMPRESSION_PRIORITY_CAPACITY_RANKING,
    EXECUTABLE_MODE,
    _load_signal_rows,
    order_capacity_candidates,
    simulate_strategy,
    summarize_simulation,
)


COMMAND = "Step 03.03 / Command 05"
COMMAND_VERSION = "C1_IMP_001_DEVELOPMENT_EVALUATION_V1"
COMMAND_PROFILE = "COMPRESSION_PRIORITY_CAPACITY_EVALUATION_V1"

EXPECTED_IMPLEMENTATION_CONFIG_HASH = (
    "d9de8dbbf0e288066565fcf9a4ef2b4cd494ed3f07760529298669226a119662"
)
EXPECTED_PARAMETER_HASH = (
    "6a5b49423e3fb30c708c9e1ae6a7cf5a5c0cf7306666d4f35f7428123d36915c"
)
EXPECTED_PREREGISTRATION_HASH = (
    "a5939b4d11282d0c8e40a2e1d9cebde79d8b62bf5d4a315adfcb8f853c366c7a"
)
EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH = (
    "90365ad9e45328a918bb714e03df78dfc049c0e335e9c6893216594c690978c0"
)
EXPECTED_SIGNAL_SET_HASH = (
    "096a11a85a72138176fb02b28efec52030e00c819c1bc67bca6fd8ae41abce9f"
)

EXPECTANCY_THRESHOLD = Decimal("0.002451889062206648204628463672")
PROFIT_FACTOR_THRESHOLD = Decimal("1.139795625568447941013450018")
WIN_RATE_THRESHOLD = Decimal("0.5282905982905982905982905983")
NET_CAGR_FLOOR = Decimal("0.0285576287541669630")
MAX_DRAWDOWN_CAP = Decimal("0.2429287610199157994929078367")
NORMALIZED_COST_DRAG_CAP = Decimal("0.2619728640")

REPORT_NAMES = (
    "family_c_imp001_dev_v1_summary.json",
    "family_c_imp001_dev_v1_treatment.csv",
    "family_c_imp001_dev_v1_yearly.csv",
    "family_c_imp001_dev_v1_criteria.csv",
    "family_c_imp001_dev_v1_admitted_quality.csv",
    "family_c_imp001_dev_v1_rejected_quality.csv",
    "family_c_imp001_dev_v1_admission_changes.csv",
    "family_c_imp001_dev_v1_same_day.csv",
    "family_c_imp001_dev_v1_capacity.csv",
    "family_c_imp001_dev_v1_comparison.csv",
)


class C1Imp001FreezeMismatch(RuntimeError):
    pass


class C1Imp001ResultImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return (
        root
        / "data/research/strategy_families/family_c/v1/implementation_research"
        / "development_evaluation"
    )


def implementation_root(root: Path) -> Path:
    return root / "data/research/strategy_families/family_c/v1/implementation_research"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _without_hash(document: Mapping[str, Any], field: str) -> dict[str, Any]:
    return {key: value for key, value in document.items() if key != field}


def _hash_matches(document: Mapping[str, Any], field: str, expected: str) -> bool:
    return document.get(field) == expected and canonical_hash(
        _without_hash(document, field)
    ) == expected


def command_04_snapshot(root: Path) -> dict[str, Any]:
    frozen_root = implementation_root(root)
    evaluation_root = output_root(root)
    paths = [
        path
        for path in frozen_root.rglob("*")
        if path.is_file() and evaluation_root not in path.parents
    ]
    paths.extend(sorted((root / "data/reports").glob("family_c_imp001_v1_*")))
    paths.extend(
        root / relative
        for relative in (
            "backend/app/research/strategy/family_c_c001_implementation_research.py",
            "backend/scripts/run_family_c_c001_implementation_research.py",
            "backend/tests/test_family_c_c001_implementation_research.py",
            "docs/strategy-family-c-c001-implementation-research-v1.md",
        )
    )
    hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(paths))
        if path.is_file()
    }
    return {"artifact_hashes": hashes, "snapshot_hash": canonical_hash(hashes)}


def verify_freeze_gate(root: Path) -> dict[str, Any]:
    frozen_root = implementation_root(root)
    reports_root = root / "data/reports"
    config = _read_json(frozen_root / "registry/implementation_research_config_v1.json")
    prereg = _read_json(frozen_root / "registry/c1_imp_001_preregistration_v1.json")
    registry = _read_json(frozen_root / "registry/implementation_research_registry_v1.json")
    criteria = _read_json(
        frozen_root / "governance/implementation_success_criteria_v1.json"
    )
    signal_set = _read_json(frozen_root / "ranking/c001_signal_set_v1.json")
    implementation_summary_path = reports_root / "family_c_imp001_v1_summary.json"
    implementation_summary = _read_json(implementation_summary_path)
    implementation_manifest = _read_json(
        frozen_root / "manifests/implementation_research_manifest_v1.json"
    )
    attribution = _read_json(
        root
        / "data/research/strategy_families/family_c/v1/c001_attribution_audit"
        / "manifests/family_c_c001_attribution_result_v1.json"
    )
    control_result = _read_json(
        root
        / "data/research/strategy_families/family_c/v1/development_evaluation"
        / "brk_c_001/brk_c_001_development_result_v1.json"
    )
    family_config = _read_json(
        root
        / "data/research/strategy_families/family_c/v1/registry"
        / "family_c_config_v1.json"
    )
    development_registry = _read_json(
        root
        / "data/research/strategy_families/family_c/v1/development_evaluation"
        / "comparison/family_c_development_registry_v1.json"
    )
    manifest_field = "implementation_research_manifest_hash"
    checks = {
        "implementation_config_hash": _hash_matches(
            config,
            "implementation_research_config_hash",
            EXPECTED_IMPLEMENTATION_CONFIG_HASH,
        ),
        "parameter_hash": _hash_matches(
            implementation_summary["parameters"],
            "parameter_hash",
            EXPECTED_PARAMETER_HASH,
        ),
        "preregistration_hash": _hash_matches(
            prereg, "preregistration_hash", EXPECTED_PREREGISTRATION_HASH
        ),
        "implementation_success_criteria_hash": _hash_matches(
            criteria,
            "implementation_success_criteria_hash",
            EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH,
        ),
        "c001_signal_set_hash": _hash_matches(
            signal_set, "c001_signal_set_hash", EXPECTED_SIGNAL_SET_HASH
        ),
        "c001_attribution_hash": _hash_matches(
            attribution, "family_c_c001_attribution_hash", EXPECTED_ATTRIBUTION_HASH
        ),
        "brk_c_001_result_hash": _hash_matches(
            control_result, "brk_c_001_result_hash", EXPECTED_C001_RESULT_HASH
        ),
        "family_c_config_hash": _hash_matches(
            family_config, "family_c_config_hash", EXPECTED_FAMILY_C_CONFIG_HASH
        ),
        "family_c_development_registry_hash": _hash_matches(
            development_registry,
            "family_c_development_registry_hash",
            EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        ),
        "implementation_manifest_hash": canonical_hash(
            _without_hash(implementation_manifest, manifest_field)
        )
        == implementation_manifest.get(manifest_field),
        "implementation_manifest_summary_hash": implementation_manifest.get(
            "summary_hash"
        )
        == file_sha256(implementation_summary_path),
        "one_preregistered_experiment": (
            registry.get("experiment_count") == 1
            and len(registry.get("experiments", ())) == 1
            and registry["experiments"][0]["experiment_id"] == EXPERIMENT_ID
            and registry["experiments"][0]["status"] == "PREREGISTERED"
        ),
        "architecture_ready": implementation_summary["classifications"][
            "C1_IMP_001_ARCHITECTURE_RESULT"
        ]
        == "READY_FOR_CONTROLLED_DEVELOPMENT_TEST",
        "development_only": (
            prereg["development_partition"]["start"]
            == DEVELOPMENT_START.isoformat()
            and prereg["development_partition"]["end"]
            == DEVELOPMENT_END.isoformat()
            and prereg["validation_accessed"] is False
        ),
        "frozen_ranking": (
            tuple(config["original_ranking"]) == ORIGINAL_RANKING
            and tuple(config["treatment_ranking"]) == TREATMENT_RANKING
        ),
        "frozen_mechanics": (
            config["only_experimental_change"] == "SAME_DAY_CAPACITY_RANKING"
            and prereg["parameter_hash"] == EXPECTED_PARAMETER_HASH
            and prereg["implementation_success_criteria_hash"]
            == EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH
            and prereg["c001_signal_set_hash"] == EXPECTED_SIGNAL_SET_HASH
        ),
    }
    artifact_mismatches = [
        relative
        for relative, expected in implementation_manifest["artifact_hashes"].items()
        if not (root / relative).is_file()
        or file_sha256(root / relative) != expected
    ]
    checks["implementation_artifact_hashes"] = not artifact_mismatches
    if not all(checks.values()):
        raise C1Imp001FreezeMismatch(
            "C1_IMP_001_FREEZE_MISMATCH: "
            f"checks={checks}; artifacts={artifact_mismatches}"
        )
    return {
        "status": "VERIFIED",
        "checks": checks,
        "config": config,
        "preregistration": prereg,
        "criteria": criteria,
        "signal_set": signal_set,
        "implementation_summary": implementation_summary,
        "attribution": attribution,
        "control_result": control_result,
        "development_registry": development_registry,
    }


def rank_treatment_candidates(
    rows: Sequence[Mapping[str, Any]], available_slots: int
) -> dict[str, list[Mapping[str, Any]]]:
    ordered = order_capacity_candidates(
        rows, COMPRESSION_PRIORITY_CAPACITY_RANKING
    )
    slots = max(0, int(available_slots))
    return {
        "ranked": ordered,
        "selected": ordered[:slots],
        "rejected": ordered[slots:],
    }


def _event_key(formation_date: str, symbol: str) -> str:
    return f"{formation_date}|{symbol}"


def reconstruct_treatment_admissions(
    signal_set: Sequence[Mapping[str, Any]],
    events: Sequence[Mapping[str, Any]],
    simulation: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    positions = simulation["positions"]
    admitted_keys = {
        _event_key(str(row["formation_date"]), str(row["symbol"]))
        for row in positions
    }
    event_map = {str(row["event_key"]): row for row in events}
    rows_by_date: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in signal_set:
        rows_by_date[str(row["formation_date"])].append(row)
    records: list[dict[str, Any]] = []
    for formation_date, candidates in sorted(rows_by_date.items()):
        entry_date = str(candidates[0]["entry_date"])
        occupied_before = {
            str(row["symbol"])
            for row in positions
            if str(row["entry_date"]) < entry_date < str(row["exit_date"])
        }
        open_symbols = set(occupied_before)
        open_before = len(open_symbols)
        nonoverlapping = [
            row for row in candidates if str(row["symbol"]) not in occupied_before
        ]
        ordered = rank_treatment_candidates(nonoverlapping, len(nonoverlapping))[
            "ranked"
        ]
        rank_by_key = {
            _event_key(formation_date, str(row["symbol"])): rank
            for rank, row in enumerate(ordered, 1)
        }
        already_open = sorted(
            (
                row
                for row in candidates
                if str(row["symbol"]) in occupied_before
            ),
            key=lambda row: str(row["symbol"]),
        )
        for row in [*already_open, *ordered]:
            symbol = str(row["symbol"])
            key = _event_key(formation_date, symbol)
            if symbol in occupied_before:
                status = "ALREADY_OPEN"
                explanation = "SYMBOL_OCCUPIED_BEFORE_ENTRY_PROCESSING"
            elif key in admitted_keys:
                status = "ADMITTED"
                explanation = "C1_IMP_001_POSITION_MATCH"
                open_symbols.add(symbol)
            elif len(open_symbols) >= MAX_CONCURRENT_POSITIONS:
                status = "CAPACITY_REJECTED"
                explanation = "FROZEN_20_POSITION_CAP"
            else:
                status = "AFFORDABILITY_REJECTED"
                explanation = "FROZEN_INTEGER_SHARE_CASH_CHECK"
            event = event_map[key]
            records.append(
                {
                    "event_key": key,
                    "formation_date": formation_date,
                    "entry_date": entry_date,
                    "symbol": symbol,
                    "compression_range_pct": row["compression_range_pct"],
                    "breakout_strength_pct": row["breakout_strength_pct"],
                    "admission_status": status,
                    "explanation": explanation,
                    "open_positions_before_entry": open_before,
                    "available_slots_before_entry": MAX_CONCURRENT_POSITIONS
                    - open_before,
                    "same_day_rank": rank_by_key.get(key, ""),
                    "same_day_ranked_candidates": len(ordered),
                    "gross_10session_return": event["gross_10session_return"],
                    "estimated_normalized_net_return": event[
                        "estimated_normalized_net_return"
                    ],
                    "MFE_pct": event["MFE_pct"],
                    "MAE_pct": event["MAE_pct"],
                    "year": event["year"],
                }
            )
    records.sort(key=lambda row: (row["formation_date"], row["symbol"]))
    counts = Counter(str(row["admission_status"]) for row in records)
    expected = {
        "ADMITTED": int(simulation["admitted_signals"]),
        "CAPACITY_REJECTED": int(simulation["capacity_rejected_signals"]),
        "ALREADY_OPEN": int(simulation["already_open_rejections"]),
        "AFFORDABILITY_REJECTED": int(simulation["affordability_rejections"]),
    }
    reconciliation = {
        "signal_count": len(signal_set),
        "classification_counts": dict(sorted(counts.items())),
        "simulation_expected_counts": expected,
        "all_signals_classified": len(records) == len(signal_set),
        "primary_counts_match": all(counts[key] == value for key, value in expected.items()),
        "admitted_keys_match": {
            row["event_key"]
            for row in records
            if row["admission_status"] == "ADMITTED"
        }
        == admitted_keys,
    }
    if not all(
        reconciliation[key]
        for key in (
            "all_signals_classified",
            "primary_counts_match",
            "admitted_keys_match",
        )
    ):
        raise ValueError(f"Treatment admission reconciliation failed: {reconciliation}")
    return records, reconciliation


def _metrics_for_keys(
    keys: set[str], event_map: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    return cohort_metrics([event_map[key] for key in sorted(keys)])


def admission_comparison(
    old_records: Sequence[Mapping[str, Any]],
    new_records: Sequence[Mapping[str, Any]],
    event_map: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    old_admitted = {
        str(row["event_key"])
        for row in old_records
        if row["admission_status"] == "ADMITTED"
    }
    new_admitted = {
        str(row["event_key"])
        for row in new_records
        if row["admission_status"] == "ADMITTED"
    }
    intersection = old_admitted & new_admitted
    old_only = old_admitted - new_admitted
    new_only = new_admitted - old_admitted
    union = old_admitted | new_admitted
    return {
        "intersection_count": len(intersection),
        "old_only_admitted_count": len(old_only),
        "new_only_admitted_count": len(new_only),
        "union_count": len(union),
        "jaccard": Decimal(len(intersection)) / Decimal(len(union))
        if union
        else Decimal("1"),
        "changed_admission_count": len(old_only) + len(new_only),
        "old_only_keys": sorted(old_only),
        "new_only_keys": sorted(new_only),
        "old_only_quality": _metrics_for_keys(old_only, event_map),
        "new_only_quality": _metrics_for_keys(new_only, event_map),
    }


def classify_replacement_quality(
    old_only: Mapping[str, Any], new_only: Mapping[str, Any]
) -> str:
    if not old_only["event_count"] or not new_only["event_count"]:
        return "INCONCLUSIVE"
    fields = ("win_rate", "median_return", "net_expectancy", "net_profit_factor")
    if any(old_only[field] is None or new_only[field] is None for field in fields):
        return "INCONCLUSIVE"
    differences = [decimal(new_only[field]) - decimal(old_only[field]) for field in fields]
    if all(value > 0 for value in differences):
        return "BETTER"
    if all(value < 0 for value in differences):
        return "WORSE"
    if all(value == 0 for value in differences):
        return "SIMILAR"
    return "MIXED"


def same_day_analysis(
    comparison: Mapping[str, Any], event_map: Mapping[str, Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    old_by_date: dict[str, set[str]] = defaultdict(set)
    new_by_date: dict[str, set[str]] = defaultdict(set)
    for key in comparison["old_only_keys"]:
        old_by_date[key.split("|", 1)[0]].add(key)
    for key in comparison["new_only_keys"]:
        new_by_date[key.split("|", 1)[0]].add(key)
    dates = sorted(set(old_by_date) | set(new_by_date))
    rows: list[dict[str, Any]] = []
    pooled_old: set[str] = set()
    pooled_new: set[str] = set()
    for formation_date in dates:
        old_keys = old_by_date[formation_date]
        new_keys = new_by_date[formation_date]
        pooled_old.update(old_keys)
        pooled_new.update(new_keys)
        old_metrics = _metrics_for_keys(old_keys, event_map)
        new_metrics = _metrics_for_keys(new_keys, event_map)
        difference = metric_difference(
            new_metrics,
            old_metrics,
            ("win_rate", "median_return", "net_expectancy", "net_profit_factor"),
        )
        rows.append(
            {
                "formation_date": formation_date,
                "old_only_count": len(old_keys),
                "new_only_count": len(new_keys),
                "old_only_win_rate": old_metrics["win_rate"],
                "new_only_win_rate": new_metrics["win_rate"],
                "win_rate_difference": difference["win_rate"],
                "old_only_median_return": old_metrics["median_return"],
                "new_only_median_return": new_metrics["median_return"],
                "median_return_difference": difference["median_return"],
                "old_only_expectancy": old_metrics["net_expectancy"],
                "new_only_expectancy": new_metrics["net_expectancy"],
                "expectancy_difference": difference["net_expectancy"],
                "old_only_profit_factor": old_metrics["net_profit_factor"],
                "new_only_profit_factor": new_metrics["net_profit_factor"],
                "profit_factor_difference": difference["net_profit_factor"],
                "diagnostic_only": True,
            }
        )
    old_metrics = _metrics_for_keys(pooled_old, event_map)
    new_metrics = _metrics_for_keys(pooled_new, event_map)
    aggregate = {
        "changed_formation_date_count": len(dates),
        "old_only": old_metrics,
        "new_only": new_metrics,
        "new_minus_old": metric_difference(
            new_metrics,
            old_metrics,
            ("win_rate", "median_return", "net_expectancy", "net_profit_factor"),
        ),
        "aggregation": "POOLED_CHANGED_ADMISSIONS_MATCHED_BY_FORMATION_DATE",
        "diagnostic_only": True,
    }
    return rows, aggregate


def yearly_admission_quality(
    old_records: Sequence[Mapping[str, Any]],
    new_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for year in (2022, 2023, 2024):
        old = [
            row
            for row in old_records
            if row["admission_status"] == "ADMITTED" and int(row["year"]) == year
        ]
        new = [
            row
            for row in new_records
            if row["admission_status"] == "ADMITTED" and int(row["year"]) == year
        ]
        old_metrics = cohort_metrics(old)
        new_metrics = cohort_metrics(new)
        rows.append(
            {
                "year": year,
                "treatment_count": new_metrics["event_count"],
                "treatment_win_rate": new_metrics["win_rate"],
                "treatment_expectancy": new_metrics["net_expectancy"],
                "treatment_profit_factor": new_metrics["net_profit_factor"],
                "frozen_count": old_metrics["event_count"],
                "frozen_win_rate": old_metrics["win_rate"],
                "frozen_expectancy": old_metrics["net_expectancy"],
                "frozen_profit_factor": old_metrics["net_profit_factor"],
            }
        )
    return rows


def _average_open_positions(records: Sequence[Mapping[str, Any]]) -> Decimal:
    by_date: dict[str, int] = {}
    for row in records:
        value = row.get("open_positions_before_entry")
        if value not in (None, ""):
            by_date[str(row["formation_date"])] = int(value)
    return (
        Decimal(sum(by_date.values())) / Decimal(len(by_date))
        if by_date
        else Decimal("0")
    )


def evaluate_criteria(
    treatment: Mapping[str, Any],
    admitted_quality: Mapping[str, Any],
    criteria_config: Mapping[str, Any],
    signal_identity: Mapping[str, Any],
) -> dict[str, Any]:
    reference = criteria_config["reference_values"]
    quality_dimensions = {
        "EXPECTANCY_QUALITY": {
            "observed": admitted_quality["net_expectancy"],
            "reference": reference["admitted_normalized_event_expectancy"],
            "threshold": EXPECTANCY_THRESHOLD,
            "pass": decimal(admitted_quality["net_expectancy"])
            >= EXPECTANCY_THRESHOLD,
        },
        "PF_QUALITY": {
            "observed": admitted_quality["net_profit_factor"],
            "reference": reference["admitted_normalized_event_profit_factor"],
            "threshold": PROFIT_FACTOR_THRESHOLD,
            "pass": admitted_quality["net_profit_factor"] is None
            or decimal(admitted_quality["net_profit_factor"])
            >= PROFIT_FACTOR_THRESHOLD,
        },
        "WIN_RATE_QUALITY": {
            "observed": admitted_quality["win_rate"],
            "reference": reference["admitted_normalized_event_win_rate"],
            "threshold": WIN_RATE_THRESHOLD,
            "pass": decimal(admitted_quality["win_rate"]) >= WIN_RATE_THRESHOLD,
        },
    }
    quality_pass_count = sum(row["pass"] for row in quality_dimensions.values())
    yearly = treatment["yearly_returns"]
    reference_yearly = reference["yearly_returns"]
    underperformance_years = sum(
        decimal(reference_yearly[year]) - decimal(yearly[year]) > Decimal("0.10")
        for year in ("2022", "2023", "2024")
    )
    sample_count = int(treatment["closed_positions"])
    sample_status = (
        "PASS"
        if sample_count >= 500
        else "LIMITED_SAMPLE"
        if sample_count >= 250
        else "FATAL_SAMPLE_FAILURE"
    )
    accounting_checks = {
        **treatment["accounting_data_integrity"]["checks"],
        "exact_signal_set": bool(signal_identity["equal"])
        and signal_identity["c001_signal_set_hash"] == EXPECTED_SIGNAL_SET_HASH,
        "exact_capacity_ranking": TREATMENT_RANKING
        == COMPRESSION_PRIORITY_CAPACITY_RANKING,
        "whole_share_accounting": True,
        "cash_reconciliation": treatment["accounting_data_integrity"]["checks"][
            "cash_reconciliation"
        ],
        "equity_reconciliation": treatment["accounting_data_integrity"]["checks"][
            "equity_reconciliation"
        ],
        "corporate_action_safety": treatment["accounting_data_integrity"]["checks"][
            "corporate_action_safety"
        ],
    }
    criteria = {
        "A_CAPACITY_QUALITY_IMPROVEMENT": quality_pass_count >= 2,
        "B_PORTFOLIO_PROFITABILITY": (
            decimal(treatment["net_expectancy"]) > 0
            and treatment["net_profit_factor"] is not None
            and decimal(treatment["net_profit_factor"]) >= Decimal("1.10")
        ),
        "C_RETURN_NON_DEGRADATION": decimal(treatment["net_CAGR"])
        >= NET_CAGR_FLOOR,
        "D_DRAWDOWN_NON_DEGRADATION": decimal(treatment["max_drawdown"])
        <= MAX_DRAWDOWN_CAP,
        "E_TEMPORAL_SUPPORT": (
            sum(decimal(value) >= 0 for value in yearly.values()) >= 2
            and underperformance_years <= 1
        ),
        "F_COST_NON_DEGRADATION": decimal(treatment["normalized_cost_drag"])
        <= NORMALIZED_COST_DRAG_CAP,
        "G_SAMPLE_ADEQUACY": sample_status == "PASS",
        "H_ACCOUNTING_DATA_INTEGRITY": all(accounting_checks.values()),
    }
    criteria_pass_count = sum(criteria.values())
    clearly_worse = {
        "EXPECTANCY": decimal(admitted_quality["net_expectancy"])
        < decimal(reference["admitted_normalized_event_expectancy"]),
        "PROFIT_FACTOR": admitted_quality["net_profit_factor"] is not None
        and decimal(admitted_quality["net_profit_factor"])
        < decimal(reference["admitted_normalized_event_profit_factor"]),
        "WIN_RATE": decimal(admitted_quality["win_rate"])
        < decimal(reference["admitted_normalized_event_win_rate"]),
    }
    fatal_conditions = {
        "FATAL_SAMPLE_FAILURE": sample_status == "FATAL_SAMPLE_FAILURE",
        "ACCOUNTING_DATA_FAILURE": not criteria["H_ACCOUNTING_DATA_INTEGRITY"],
        "SIGNAL_SET_FAILURE": not signal_identity["equal"],
    }
    fatal_failure = any(fatal_conditions.values())
    worse_count = sum(clearly_worse.values())
    if fatal_failure or criteria_pass_count < 6 or worse_count >= 2:
        classification = "FAILED"
    elif (
        criteria_pass_count == 8
        and quality_pass_count == 3
        and decimal(treatment["net_CAGR"])
        > decimal(reference["portfolio_net_CAGR"])
        and treatment["net_profit_factor"] is not None
        and decimal(treatment["net_profit_factor"]) >= Decimal("1.15")
    ):
        classification = "STRONGLY_SUPPORTED"
    elif criteria_pass_count == 8 and quality_pass_count >= 2:
        classification = "SUPPORTED"
    elif not fatal_failure and criteria_pass_count >= 6 and quality_pass_count >= 1:
        classification = "PARTIALLY_SUPPORTED"
    else:
        classification = "INCONCLUSIVE"
    if classification in {"STRONGLY_SUPPORTED", "SUPPORTED"}:
        next_stage = "FREEZE_C001_IMPLEMENTATION_FOR_VALIDATION_DESIGN"
    elif classification == "PARTIALLY_SUPPORTED":
        next_stage = (
            "CONTINUE_CONTROLLED_DEVELOPMENT"
            if not criteria["H_ACCOUNTING_DATA_INTEGRITY"]
            else "PAUSE_FAMILY_C"
        )
    elif classification == "FAILED":
        next_stage = "CLOSE_IMPLEMENTATION_HYPOTHESIS"
    else:
        next_stage = "INCONCLUSIVE"
    return {
        "quality_dimensions": quality_dimensions,
        "quality_pass_count": quality_pass_count,
        "criteria_A_H": criteria,
        "criteria_pass_count": criteria_pass_count,
        "sample_status": sample_status,
        "underperformance_years_gt_10pp": underperformance_years,
        "accounting_checks": accounting_checks,
        "clearly_worse_dimensions": clearly_worse,
        "clearly_worse_count": worse_count,
        "fatal_conditions": fatal_conditions,
        "fatal_failure": fatal_failure,
        "C1_IMP_001_DEVELOPMENT_RESULT": classification,
        "FAMILY_C_C001_POST_IMPLEMENTATION_STAGE": next_stage,
    }


def criteria_rows(evaluation: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "criterion": name,
            "status": "PASS" if passed else "FAIL",
            "criterion_group": "STANDARD_A_H",
        }
        for name, passed in evaluation["criteria_A_H"].items()
    ]
    rows.extend(
        {
            "criterion": name,
            "status": "PASS" if detail["pass"] else "FAIL",
            "criterion_group": "ADMITTED_QUALITY",
            "observed": detail["observed"],
            "reference": detail["reference"],
            "threshold": detail["threshold"],
        }
        for name, detail in evaluation["quality_dimensions"].items()
    )
    return rows


def _scalar_metrics(metrics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metrics.items()
        if not isinstance(value, (dict, list, tuple))
    }


def _quality_report_rows(
    aggregate_label: str,
    aggregate: Mapping[str, Any],
    yearly_rows: Sequence[Mapping[str, Any]],
    prefix: str,
) -> list[dict[str, Any]]:
    rows = [{"period": aggregate_label, **aggregate}]
    for row in yearly_rows:
        rows.append(
            {
                "period": str(row["year"]),
                "event_count": row[f"{prefix}_count"],
                "win_rate": row[f"{prefix}_win_rate"],
                "net_expectancy": row[f"{prefix}_expectancy"],
                "net_profit_factor": row[f"{prefix}_profit_factor"],
            }
        )
    return rows


def _immutable_json(path: Path, document: Mapping[str, Any], hash_field: str) -> None:
    if path.is_file():
        previous = _read_json(path)
        if previous.get(hash_field) != document.get(hash_field):
            raise C1Imp001ResultImmutabilityError(
                f"Frozen C1-IMP-001 development result would change: {path.name}"
            )
    write_json(path, document)


def _admission_change_rows(
    old_records: Sequence[Mapping[str, Any]],
    new_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    old_map = {str(row["event_key"]): row for row in old_records}
    rows = []
    for new in new_records:
        key = str(new["event_key"])
        old = old_map[key]
        old_admitted = old["admission_status"] == "ADMITTED"
        new_admitted = new["admission_status"] == "ADMITTED"
        rows.append(
            {
                "event_key": key,
                "formation_date": new["formation_date"],
                "symbol": new["symbol"],
                "compression_range_pct": new["compression_range_pct"],
                "breakout_strength_pct": new["breakout_strength_pct"],
                "old_status": old["admission_status"],
                "new_status": new["admission_status"],
                "old_admitted": old_admitted,
                "new_admitted": new_admitted,
                "admission_changed": old_admitted != new_admitted,
                "old_rank": old.get("same_day_rank", ""),
                "new_rank": new.get("same_day_rank", ""),
            }
        )
    return rows


def _capacity_rows(
    control: Mapping[str, Any],
    treatment: Mapping[str, Any],
    old_records: Sequence[Mapping[str, Any]],
    new_records: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "experiment_id": REFERENCE_EXPERIMENT_ID,
            "ranking": " > ".join(ORIGINAL_RANKING),
            "valid_pre_capacity_signals": control["entry_ready_signals"],
            "admitted_signals": control["admitted_signals"],
            "capacity_rejected_signals": control["capacity_rejected_signals"],
            "already_open_rejections": control["already_open_rejections"],
            "affordability_rejections": control["affordability_rejections"],
            "terminal_path_unavailable": control["terminal_path_unavailable"],
            "capacity_rejection_rate": control["capacity_rejection_rate"],
            "constrained_days": control["days_capacity_constrained"],
            "max_signals_per_day": control["max_valid_signals_one_day"],
            "average_open_positions_before_entry": _average_open_positions(
                old_records
            ),
        },
        {
            "experiment_id": EXPERIMENT_ID,
            "ranking": " > ".join(TREATMENT_RANKING),
            "valid_pre_capacity_signals": treatment["entry_ready_signals"],
            "admitted_signals": treatment["admitted_signals"],
            "capacity_rejected_signals": treatment["capacity_rejected_signals"],
            "already_open_rejections": treatment["already_open_rejections"],
            "affordability_rejections": treatment["affordability_rejections"],
            "terminal_path_unavailable": treatment["terminal_path_unavailable"],
            "capacity_rejection_rate": treatment["capacity_rejection_rate"],
            "constrained_days": treatment["days_capacity_constrained"],
            "max_signals_per_day": treatment["max_valid_signals_one_day"],
            "average_open_positions_before_entry": _average_open_positions(
                new_records
            ),
        },
    ]


def _portfolio_comparison_rows(
    control: Mapping[str, Any], treatment: Mapping[str, Any]
) -> list[dict[str, Any]]:
    fields = (
        "net_ending_equity",
        "net_total_return",
        "net_CAGR",
        "max_drawdown",
        "annualized_volatility",
        "sharpe_like_metric",
        "closed_positions",
        "position_win_rate",
        "net_expectancy",
        "net_profit_factor",
        "turnover",
        "transaction_costs",
        "normalized_cost_drag",
        "average_cash",
        "average_concurrent_positions",
        "capacity_rejection_rate",
    )
    rows = []
    for field in fields:
        control_value = control[field]
        treatment_value = treatment[field]
        difference = (
            decimal(treatment_value) - decimal(control_value)
            if control_value is not None and treatment_value is not None
            else None
        )
        rows.append(
            {
                "metric": field,
                "control": control_value,
                "treatment": treatment_value,
                "treatment_minus_control": difference,
            }
        )
    return rows


def build_c1_imp_001_development_evaluation(root: Path) -> dict[str, Any]:
    started_at = utc_now()
    timer = time.perf_counter()
    freeze = verify_freeze_gate(root)
    command_04_before = command_04_snapshot(root)

    signal_rows = _load_signal_rows(root)
    signal_set = build_c001_signal_set(root)
    signal_identity = verify_signal_set_identity(root, signal_set)
    if (
        signal_identity["treatment_count"] != 4247
        or signal_identity["c001_signal_set_hash"] != EXPECTED_SIGNAL_SET_HASH
    ):
        raise C1Imp001FreezeMismatch("C1_IMP_001_FREEZE_MISMATCH: signal set")

    aliases = _load_aliases(root)
    membership = _load_membership(root)
    sessions = _load_sessions(root)
    bars = _load_adjusted_bars(root, set(membership.grouped), aliases)
    if any(session > DEVELOPMENT_END for session in bars):
        raise ValueError("Post-2024 prices were loaded")
    events = [
        row
        for row in build_event_cohort(signal_rows, sessions, bars)
        if bool(row["compression_pass"])
    ]
    event_map = {str(row["event_key"]): row for row in events}
    if set(event_map) != {str(row["event_key"]) for row in signal_set}:
        raise C1Imp001FreezeMismatch(
            "C1_IMP_001_FREEZE_MISMATCH: all-signal event cohort"
        )

    simulation = simulate_strategy(
        experiment_id=EXPERIMENT_ID,
        experiment_name=EXPERIMENT_NAME,
        signal_field="c001_signal",
        mode=EXECUTABLE_MODE,
        signal_rows=signal_rows,
        sessions=sessions,
        bars=bars,
        capacity_ranking=COMPRESSION_PRIORITY_CAPACITY_RANKING,
    )
    treatment = summarize_simulation(simulation)
    new_records, admission_reconciliation = reconstruct_treatment_admissions(
        signal_set, events, simulation
    )
    old_records = read_csv(
        root
        / "data/research/strategy_families/family_c/v1/c001_attribution_audit"
        / "capacity/c001_admission_classification_v1.csv"
    )
    old_complete = [row for row in old_records if str(row["event_key"]) in event_map]
    if len(old_complete) != 4247:
        raise C1Imp001FreezeMismatch(
            "C1_IMP_001_FREEZE_MISMATCH: frozen admission cohort"
        )

    admitted_events = [
        row for row in new_records if row["admission_status"] == "ADMITTED"
    ]
    rejected_events = [
        row
        for row in new_records
        if row["admission_status"] == "CAPACITY_REJECTED"
    ]
    admitted_quality = cohort_metrics(admitted_events)
    rejected_quality = cohort_metrics(rejected_events)
    yearly_quality = yearly_admission_quality(old_complete, new_records)
    comparison = admission_comparison(old_complete, new_records, event_map)
    replacement_quality = classify_replacement_quality(
        comparison["old_only_quality"], comparison["new_only_quality"]
    )
    same_day_rows, same_day = same_day_analysis(comparison, event_map)
    evaluation = evaluate_criteria(
        treatment, admitted_quality, freeze["criteria"], signal_identity
    )
    control = freeze["control_result"]["executable_metrics"]
    capacity = _capacity_rows(control, treatment, old_complete, new_records)
    admission_changes = _admission_change_rows(old_complete, new_records)
    comparison_rows = _portfolio_comparison_rows(control, treatment)

    comparison_public = {
        key: value
        for key, value in comparison.items()
        if key not in {"old_only_keys", "new_only_keys"}
    }
    result_body = {
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "family_version": FAMILY_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "experiment_name": EXPERIMENT_NAME,
        "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
        "frozen_inputs": {
            "implementation_research_config_hash": EXPECTED_IMPLEMENTATION_CONFIG_HASH,
            "parameter_hash": EXPECTED_PARAMETER_HASH,
            "preregistration_hash": EXPECTED_PREREGISTRATION_HASH,
            "implementation_success_criteria_hash": EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH,
            "c001_signal_set_hash": EXPECTED_SIGNAL_SET_HASH,
            "family_c_c001_attribution_hash": EXPECTED_ATTRIBUTION_HASH,
            "brk_c_001_result_hash": EXPECTED_C001_RESULT_HASH,
            "family_c_config_hash": EXPECTED_FAMILY_C_CONFIG_HASH,
            "family_c_development_registry_hash": EXPECTED_DEVELOPMENT_REGISTRY_HASH,
        },
        "signal_set": {
            "equal": signal_identity["equal"],
            "frozen_count": signal_identity["frozen_count"],
            "treatment_count": signal_identity["treatment_count"],
            "missing_count": signal_identity["missing_count"],
            "extra_count": signal_identity["extra_count"],
            "field_mismatch_count": signal_identity["field_mismatch_count"],
            "c001_signal_set_hash": signal_identity["c001_signal_set_hash"],
            "all_signal_compression_pass_cohort_unchanged": True,
        },
        "mechanics": {
            "breakout_window": BREAKOUT_WINDOW,
            "compression_window": COMPRESSION_WINDOW,
            "compression_threshold": COMPRESSION_THRESHOLD,
            "starting_capital": STARTING_CAPITAL,
            "maximum_positions": MAX_CONCURRENT_POSITIONS,
            "target_notional_fraction": TARGET_NOTIONAL_FRACTION,
            "whole_shares": True,
            "one_position_per_symbol": True,
            "leverage": False,
            "entry": "T_PLUS_1_ELIGIBLE_OPEN",
            "holding_completed_sessions": HOLDING_SESSIONS,
            "exit": "NEXT_ELIGIBLE_OPEN_AFTER_T_PLUS_10",
            "stop": None,
            "target": None,
            "cost_model": "INDIA_EQUITY_COST_MODEL_V1",
            "cost_profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "cost_scenario": SCENARIO_BASELINE_SLIPPAGE,
            "cost_config_hash": EXPECTED_COST_CONFIG_HASH,
            "slippage_bps_per_side": Decimal("5"),
        },
        "rankings": {
            "control": ORIGINAL_RANKING,
            "treatment": TREATMENT_RANKING,
            "only_change": "SAME_DAY_CAPACITY_RANKING",
            "ranking_changed_after_result": False,
            "second_ranking_tested": False,
        },
        "development_partition": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
            "post_2024_accessed": False,
            "validation_accessed": False,
        },
        "primary_mode": EXECUTABLE_MODE,
        "treatment_portfolio": treatment,
        "control_reference": control,
        "admitted_event_quality": admitted_quality,
        "capacity_rejected_event_quality": rejected_quality,
        "yearly_admitted_quality": yearly_quality,
        "admission_reconciliation": admission_reconciliation,
        "admission_comparison": comparison_public,
        "COMPRESSION_PRIORITY_REPLACEMENT_QUALITY": replacement_quality,
        "same_day_matched_analysis": same_day,
        "evaluation": evaluation,
        "C1_IMP_001_DEVELOPMENT_RESULT": evaluation[
            "C1_IMP_001_DEVELOPMENT_RESULT"
        ],
        "FAMILY_C_C001_POST_IMPLEMENTATION_STAGE": evaluation[
            "FAMILY_C_C001_POST_IMPLEMENTATION_STAGE"
        ],
        "governance": {
            "parameter_mutations": 0,
            "signal_parameter_changed": False,
            "ranking_changed_after_result": False,
            "second_ranking_tested": False,
            "capacity_changed": False,
            "holding_period_changed": False,
            "position_sizing_changed": False,
            "stop_added": False,
            "target_added": False,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "family_d_started": False,
        },
    }
    result = {
        **result_body,
        "c1_imp_001_result_hash": canonical_hash(result_body),
    }
    registry_body = {
        "registry_version": "C1_IMP_001_IMPLEMENTATION_DEVELOPMENT_REGISTRY_V1",
        "family_version": FAMILY_VERSION,
        "experiment_count": 1,
        "experiments": [
            {
                "experiment_id": EXPERIMENT_ID,
                "experiment_name": EXPERIMENT_NAME,
                "status_before": "PREREGISTERED",
                "status": "DEVELOPMENT_EVALUATED",
                "promotion_allowed": False,
                "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
                "parameter_hash": EXPECTED_PARAMETER_HASH,
                "preregistration_hash": EXPECTED_PREREGISTRATION_HASH,
                "implementation_success_criteria_hash": EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH,
                "c001_signal_set_hash": EXPECTED_SIGNAL_SET_HASH,
                "result_hash": result["c1_imp_001_result_hash"],
                "development_result": evaluation[
                    "C1_IMP_001_DEVELOPMENT_RESULT"
                ],
            }
        ],
        "FAMILY_C_C001_POST_IMPLEMENTATION_STAGE": evaluation[
            "FAMILY_C_C001_POST_IMPLEMENTATION_STAGE"
        ],
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    registry = {
        **registry_body,
        "implementation_development_registry_hash": canonical_hash(registry_body),
    }

    evaluation_root = output_root(root)
    control_root = evaluation_root / "control"
    treatment_root = evaluation_root / "treatment"
    comparison_root = evaluation_root / "comparison"
    admissions_root = evaluation_root / "admissions"
    ledgers_root = evaluation_root / "ledgers"
    diagnostics_root = evaluation_root / "diagnostics"
    manifests_root = evaluation_root / "manifests"
    reports_root = root / "data/reports"
    result_path = treatment_root / "c1_imp_001_development_result_v1.json"
    registry_path = comparison_root / "implementation_development_registry_v1.json"
    manifest_path = manifests_root / "c1_imp_001_development_manifest_v1.json"

    _immutable_json(result_path, result, "c1_imp_001_result_hash")
    _immutable_json(
        registry_path, registry, "implementation_development_registry_hash"
    )
    write_json(
        control_root / "frozen_brk_c_001_reference_v1.json",
        {
            "experiment_id": REFERENCE_EXPERIMENT_ID,
            "result_hash": EXPECTED_C001_RESULT_HASH,
            "metrics": control,
        },
    )
    write_csv(treatment_root / "c1_imp_001_positions_v1.csv", simulation["positions"])
    write_csv(ledgers_root / "c1_imp_001_ledger_v1.csv", simulation["ledger"])
    write_csv(ledgers_root / "c1_imp_001_capacity_daily_v1.csv", simulation["capacity_daily"])
    write_csv(admissions_root / "c1_imp_001_admission_classification_v1.csv", new_records)
    write_csv(admissions_root / "old_new_admission_changes_v1.csv", admission_changes)
    write_json(comparison_root / "old_new_admission_comparison_v1.json", comparison_public)
    write_csv(diagnostics_root / "same_day_matched_v1.csv", same_day_rows)
    write_csv(diagnostics_root / "yearly_admitted_quality_v1.csv", yearly_quality)
    write_csv(diagnostics_root / "capacity_comparison_v1.csv", capacity)
    write_json(diagnostics_root / "criteria_evaluation_v1.json", evaluation)

    yearly_report = []
    portfolio_by_year = {int(row["year"]): row for row in treatment["yearly"]}
    admitted_by_year = {int(row["year"]): row for row in yearly_quality}
    for year in (2022, 2023, 2024):
        yearly_report.append({**portfolio_by_year[year], **admitted_by_year[year]})
    admitted_report = [
        {"period": "ALL_DEVELOPMENT", **admitted_quality},
        *(
            {
                "period": str(row["year"]),
                "event_count": row["treatment_count"],
                "win_rate": row["treatment_win_rate"],
                "net_expectancy": row["treatment_expectancy"],
                "net_profit_factor": row["treatment_profit_factor"],
            }
            for row in yearly_quality
        ),
    ]
    report_map = {
        REPORT_NAMES[1]: [_scalar_metrics(treatment)],
        REPORT_NAMES[2]: yearly_report,
        REPORT_NAMES[3]: criteria_rows(evaluation),
        REPORT_NAMES[4]: admitted_report,
        REPORT_NAMES[5]: [{"period": "ALL_DEVELOPMENT", **rejected_quality}],
        REPORT_NAMES[6]: admission_changes,
        REPORT_NAMES[7]: same_day_rows,
        REPORT_NAMES[8]: capacity,
        REPORT_NAMES[9]: comparison_rows,
    }
    for name, rows in report_map.items():
        write_csv(reports_root / name, rows)

    command_04_after = command_04_snapshot(root)
    if command_04_after != command_04_before:
        raise C1Imp001FreezeMismatch("Command 04 artifacts changed during evaluation")

    artifact_paths = [
        path
        for path in evaluation_root.rglob("*")
        if path.is_file() and path != manifest_path
    ]
    artifact_paths.extend(reports_root / name for name in REPORT_NAMES[1:])
    artifact_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in sorted(set(artifact_paths))
    }
    runtime_seconds = Decimal(str(time.perf_counter() - timer))
    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": started_at,
        "family_version": FAMILY_VERSION,
        "freeze_gate": {
            "status": freeze["status"],
            "checks": freeze["checks"],
        },
        **result,
        "result_hashes": {
            "c1_imp_001_result_hash": result["c1_imp_001_result_hash"],
            "implementation_development_registry_hash": registry[
                "implementation_development_registry_hash"
            ],
        },
        "immutability": {
            "command_04_snapshot_before": command_04_before["snapshot_hash"],
            "command_04_snapshot_after": command_04_after["snapshot_hash"],
            "command_04_unchanged": True,
            "parameter_hash_unchanged": True,
            "preregistration_hash_unchanged": True,
        },
        "runtime": {
            "elapsed_seconds": runtime_seconds,
            "storage_root": evaluation_root.relative_to(root).as_posix(),
        },
        "storage": {"artifact_hashes": artifact_hashes},
        "security": {
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "external_writes": 0,
            "secrets_added": 0,
        },
        "known_limitations": (
            "DEVELOPMENT_PARTITION_ONLY_VALIDATION_NOT_ACCESSED",
            "SAME_DAY_ANALYSIS_IS_DIAGNOSTIC_ONLY",
            "EVENT_QUALITY_USES_NORMALIZED_FIXED_NOTIONAL_ATTRIBUTION",
            "ONE_PREREGISTERED_RANKING_ONLY_NO_PARAMETER_SEARCH",
            "NO_OUT_OF_SAMPLE_CLAIM",
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
    manifest_body = {
        "command_version": COMMAND_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "c1_imp_001_result_hash": result["c1_imp_001_result_hash"],
        "implementation_development_registry_hash": registry[
            "implementation_development_registry_hash"
        ],
        "artifact_hashes": artifact_hashes,
        "summary_hash": file_sha256(summary_path),
        "command_04_snapshot_hash": command_04_after["snapshot_hash"],
        "validation_accessed": False,
        "strategy_v2_created": False,
    }
    manifest = {
        **manifest_body,
        "c1_imp_001_development_manifest_hash": canonical_hash(manifest_body),
    }
    write_json(manifest_path, manifest)
    return summary


def finalize_c1_imp_001_development_review(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    manifest_path = output_root(root) / "manifests/c1_imp_001_development_manifest_v1.json"
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
    field = "c1_imp_001_development_manifest_hash"
    manifest[field] = canonical_hash(_without_hash(manifest, field))
    write_json(manifest_path, manifest)
    return summary


__all__ = [
    "COMMAND_PROFILE",
    "COMMAND_VERSION",
    "EXPECTANCY_THRESHOLD",
    "EXPECTED_ATTRIBUTION_HASH",
    "EXPECTED_IMPLEMENTATION_CONFIG_HASH",
    "EXPECTED_IMPLEMENTATION_SUCCESS_CRITERIA_HASH",
    "EXPECTED_PARAMETER_HASH",
    "EXPECTED_PREREGISTRATION_HASH",
    "EXPECTED_SIGNAL_SET_HASH",
    "MAX_DRAWDOWN_CAP",
    "NET_CAGR_FLOOR",
    "NORMALIZED_COST_DRAG_CAP",
    "PROFIT_FACTOR_THRESHOLD",
    "REPORT_NAMES",
    "WIN_RATE_THRESHOLD",
    "admission_comparison",
    "build_c1_imp_001_development_evaluation",
    "classify_replacement_quality",
    "evaluate_criteria",
    "finalize_c1_imp_001_development_review",
    "rank_treatment_candidates",
    "reconstruct_treatment_admissions",
    "same_day_analysis",
    "verify_freeze_gate",
    "yearly_admission_quality",
]
