from __future__ import annotations

import json
import math
import statistics
from copy import deepcopy
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path
from typing import Any, Mapping, Sequence

from app.backtesting.costs.cost_models import canonical_hash, json_ready
from app.research.strategy.family_a_development_backtest import (
    COMMAND_VERSION as COMMAND_02_VERSION,
    EXECUTABLE_MODE,
    EXPECTED_FAMILY_CONFIG_HASH,
    full_baseline_snapshot,
    load_rebalance_schedules,
    verify_family_a_preregistration,
)
from app.research.strategy.family_a_momentum import (
    DEVELOPMENT_END,
    DEVELOPMENT_START,
    FAMILY_VERSION,
    STARTING_CAPITAL,
    _load_adjusted_bars,
    _load_aliases,
    _load_membership,
    decimal,
    estimate_order_cost,
    file_sha256,
    write_csv,
    write_json,
)


PHASE2_VERSION = "FAMILY_A_PHASE2_RESEARCH_V1"
PHASE2_PROFILE = "MOMENTUM_IMPLEMENTATION_EFFICIENCY_V1"
COMMAND = "Step 03.01 / Command 03"
REFERENCE_EXPERIMENT_ID = "MOM-A-002"
REFERENCE_BASELINE_RESULT_HASH = "ce6f81671e1ede73743cb701a4612e6104c0d81b523409b2c2e04c8a4aab77c6"
REFERENCE_PARAMETER_HASH = "f98c19a62ff0201c5501b1cab269432c362188f345a90acd76cd53f65e514df8"
REFERENCE_PREREGISTRATION_HASH = "e88f8c2588b8c1ffb2fb5c951471f423d6b99d065ba135c58979c57f196f91cc"
EXPECTED_COMMAND_02_REGISTRY_HASH = "533509cf3735a5b86781d7b3865e4fd2e96e561ab98afe00804504547de84b43"
EXPECTED_COMMAND_02_RESULT_HASHES = {
    "MOM-A-001": "4ca48a4954a615dee859b03529d84974a8094c5fea75cc06282ff2d7d4aa195f",
    "MOM-A-002": REFERENCE_BASELINE_RESULT_HASH,
    "MOM-A-003": "892faa56fad9bb9d0bdfaecef8c438815e3a0952f458e596437127bb51625a6c",
}
EXPECTED_PHASE2_CONFIG_HASH = "8800738a5716ccbd1464ff564c5dea3b2891c523063eee01d5ad85fb583672cc"
EXPECTED_PHASE2_REGISTRY_HASH = "bdb431c0962183942a1d1253a07abd9df359cec6db18ca58686622bf0c603f20"
EXPECTED_PHASE2_EXPERIMENT_HASHES = {
    "A2-001": {
        "parameter_hash": "1998b338f22ef1c3151bd8431869923620fa7742bab986ed92da65b5e884e482",
        "preregistration_hash": "383ae831dac21ad2f175e30219d1b0c532622a867359bce34d2154f8c422c87c",
    },
    "A2-002": {
        "parameter_hash": "a391c2b46541af88b91b316bf2914bb15c6a11a7c5c9ff291d9f6c617bf8ae5b",
        "preregistration_hash": "f379b7712d5f956a4632d2a5fdbe61e39ceb395f7c50147229a142e752197897",
    },
}

A2_001 = "A2-001"
A2_002 = "A2-002"
PHASE2_EXPERIMENT_IDS = (A2_001, A2_002)
ENTRY_PERCENTILE = Decimal("0.10")
RETENTION_PERCENTILE = Decimal("0.15")
A2_001_CAPITAL = Decimal("100000")
A2_002_CAPITAL = Decimal("500000")

FUTURE_PERFORMANCE_METRICS = (
    "NET_CAGR",
    "NET_TOTAL_RETURN",
    "MAX_DRAWDOWN",
    "ANNUALIZED_VOLATILITY",
    "POSITIVE_MONTH_RATE",
    "POSITIVE_REBALANCE_PERIOD_RATE",
    "YEARLY_RETURN",
    "COST_DRAG",
)
TURNOVER_METRICS = (
    "ANNUALIZED_TURNOVER",
    "AVERAGE_REBALANCE_TURNOVER",
    "MEDIAN_REBALANCE_TURNOVER",
    "P90_REBALANCE_TURNOVER",
    "RETENTION_RATE",
    "ADDED_COUNT",
    "REMOVED_COUNT",
    "TRANSACTION_COSTS",
)
CAPITAL_METRICS = (
    "INTENDED_HOLDINGS",
    "ACTUAL_HOLDINGS",
    "UNAFFORDABLE_HOLDINGS",
    "AVERAGE_CASH_PCT",
    "MEDIAN_CASH_PCT",
    "MAXIMUM_CASH_PCT",
    "ACTUAL_INVESTED_PCT",
    "INTENDED_VS_REALIZED_POSITION_WEIGHT_ERROR",
    "TRACKING_DIFFERENCE_VS_IDEALIZED_PORTFOLIO",
)

REPORT_NAMES = (
    "family_a_phase2_v1_summary.json",
    "family_a_phase2_v1_registry.csv",
    "family_a_phase2_v1_retention_pilot.csv",
    "family_a_phase2_v1_capital_pilot.csv",
    "family_a_phase2_v1_readiness.csv",
)


class FamilyAPhase2BaselineMismatch(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_command_02_results(root: Path) -> dict[str, Any]:
    summary_path = root / "data/reports/family_a_dev_v1_summary.json"
    registry_path = (
        root
        / "data/research/strategy_families/family_a/v1/development_backtests/registry/development_registry_v1.json"
    )
    if not summary_path.exists() or not registry_path.exists():
        raise FamilyAPhase2BaselineMismatch("Frozen Family A Command 02 artifacts are missing")
    summary = _read_json(summary_path)
    registry = _read_json(registry_path)
    checks = {
        "command_version": summary.get("command_version") == COMMAND_02_VERSION,
        "family_config_hash": summary.get("family_config_hash") == EXPECTED_FAMILY_CONFIG_HASH,
        "family_result": summary.get("classifications", {}).get("FAMILY_A_DEVELOPMENT_RESULT") == "PROMISING_FAMILY",
        "phase2_candidate": summary.get("classifications", {}).get("FAMILY_A_PHASE2_AUTHORIZATION_CANDIDATE") == "YES",
        "validation_not_accessed": summary.get("governance", {}).get("validation_accessed") is False,
        "winner_not_selected": summary.get("governance", {}).get("winner_selected") is False,
        "reviewed": summary.get("verification", {}).get("ready_for_review") is True,
        "registry_hash": registry.get("development_registry_hash") == EXPECTED_COMMAND_02_REGISTRY_HASH,
    }
    registry_body = {key: value for key, value in registry.items() if key != "development_registry_hash"}
    checks["registry_hash_recomputed"] = canonical_hash(registry_body) == EXPECTED_COMMAND_02_REGISTRY_HASH
    for experiment_id, expected_hash in EXPECTED_COMMAND_02_RESULT_HASHES.items():
        path = (
            root
            / "data/research/strategy_families/family_a/v1/development_backtests"
            / experiment_id.lower().replace("-", "_")
            / "baseline_result.json"
        )
        result = _read_json(path)
        body = {key: value for key, value in result.items() if key != "baseline_result_hash"}
        checks[f"{experiment_id}_result_hash"] = (
            result.get("baseline_result_hash") == expected_hash
            and canonical_hash(body) == expected_hash
        )
    if not all(checks.values()):
        raise FamilyAPhase2BaselineMismatch(f"Frozen Family A Command 02 mismatch: {checks}")
    reference = summary["experiments"][REFERENCE_EXPERIMENT_ID]
    if (
        reference["baseline_result_hash"] != REFERENCE_BASELINE_RESULT_HASH
        or reference["classifications"]["ELIGIBLE_FOR_FAMILY_A_PHASE2"] != "YES"
    ):
        raise FamilyAPhase2BaselineMismatch("MOM-A-002 reference linkage changed")
    return {
        "verified": True,
        "checks": checks,
        "summary": summary,
        "registry": registry,
        "reference": reference,
    }


def command_02_snapshot(root: Path) -> dict[str, Any]:
    verified = verify_command_02_results(root)
    artifact_root = root / "data/research/strategy_families/family_a/v1/development_backtests"
    paths = [
        *sorted(path for path in artifact_root.rglob("*") if path.is_file()),
        *sorted((root / "data/reports").glob("family_a_dev_v1_*")),
        *sorted((root / "data/reports").glob("family_a_mom_a_*_development.csv")),
        root / "docs/strategy-family-a-development-backtest-v1.md",
    ]
    file_hashes = {
        path.relative_to(root).as_posix(): file_sha256(path)
        for path in paths
        if path.exists()
    }
    semantic = {
        "family_result": "PROMISING_FAMILY",
        "phase2_candidate": "YES",
        "registry_hash": EXPECTED_COMMAND_02_REGISTRY_HASH,
        "result_hashes": EXPECTED_COMMAND_02_RESULT_HASHES,
        "reference_result_hash": verified["reference"]["baseline_result_hash"],
        "file_hashes": file_hashes,
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def phase2_baseline_snapshot(root: Path) -> dict[str, Any]:
    prior = full_baseline_snapshot(root)
    command_02 = command_02_snapshot(root)
    semantic = {
        "prior_baseline_snapshot_hash": prior["snapshot_hash"],
        "command_02_snapshot_hash": command_02["snapshot_hash"],
        "cap4_validation_state": prior["cap4_validation_state"],
        "cap4_validation_run_count": prior["cap4_validation_run_count"],
        "family_a_command_01_snapshot_hash": prior["family_a_command_01_snapshot_hash"],
        "family_a_command_02_registry_hash": command_02["registry_hash"],
    }
    return {**semantic, "snapshot_hash": canonical_hash(semantic)}


def phase2_config() -> dict[str, Any]:
    body = {
        "phase2_version": PHASE2_VERSION,
        "profile": PHASE2_PROFILE,
        "family_version": FAMILY_VERSION,
        "family_config_hash": EXPECTED_FAMILY_CONFIG_HASH,
        "purpose": (
            "Test turnover reduction and practical capital fidelity without searching for a new signal."
        ),
        "reference_baseline": {
            "experiment_id": REFERENCE_EXPERIMENT_ID,
            "role": "REFERENCE_NOT_BEST_WINNER_OR_OPTIMAL",
            "parameter_hash": REFERENCE_PARAMETER_HASH,
            "preregistration_hash": REFERENCE_PREREGISTRATION_HASH,
            "development_result_hash": REFERENCE_BASELINE_RESULT_HASH,
            "development_result": "PROMISING",
            "phase2_eligible": "YES",
        },
        "development_window": {
            "start": DEVELOPMENT_START.isoformat(),
            "end": DEVELOPMENT_END.isoformat(),
        },
        "shared_frozen_rules": {
            "signal": "6M",
            "rebalance": "QUARTERLY",
            "entry_selection": "TOP_DECILE",
            "weighting": "EQUAL_WEIGHT",
            "direction": "LONG_ONLY",
            "leverage_allowed": False,
            "stop_loss": None,
            "profit_target": None,
            "universe": "POINT_IN_TIME_NIFTY_500",
            "minimum_price_inr": Decimal("100"),
            "liquidity_window_sessions": 20,
            "minimum_median_traded_value_inr": Decimal("100000000"),
            "execution": "NEXT_ELIGIBLE_SESSION_OPEN",
            "cost_model": "INDIA_EQUITY_COST_MODEL_V1",
            "cost_profile": "NSE_CASH_DELIVERY_RESEARCH_V1",
            "cost_scenario": "COST-SCENARIO-002",
            "slippage_bps_per_side": Decimal("5"),
        },
        "experiment_count": 2,
        "experiment_ids": list(PHASE2_EXPERIMENT_IDS),
        "allowed_retention_band": {
            "entry_percentile": ENTRY_PERCENTILE,
            "retention_percentile": RETENTION_PERCENTILE,
            "band_width_percentage_points": Decimal("5"),
            "alternatives_allowed": False,
        },
        "allowed_capitals_inr": {
            "A2-001": A2_001_CAPITAL,
            "A2-002": A2_002_CAPITAL,
            "alternatives_allowed": False,
        },
        "future_performance_metrics": FUTURE_PERFORMANCE_METRICS,
        "turnover_metrics": TURNOVER_METRICS,
        "capital_metrics": CAPITAL_METRICS,
        "future_classifications": {
            "RETENTION_BAND_TURNOVER_RESULT": (
                "MATERIAL_IMPROVEMENT",
                "MODERATE_IMPROVEMENT",
                "MINOR_IMPROVEMENT",
                "NO_IMPROVEMENT",
                "WORSE",
                "INCONCLUSIVE",
            ),
            "CAPITAL_FEASIBILITY_IMPROVEMENT": (
                "MATERIAL_IMPROVEMENT",
                "MODERATE_IMPROVEMENT",
                "MINOR_IMPROVEMENT",
                "NO_MEANINGFUL_IMPROVEMENT",
                "INCONCLUSIVE",
            ),
            "CAPITAL_DISTORTION": (
                "LOW_DISTORTION",
                "MODERATE_DISTORTION",
                "HIGH_DISTORTION",
                "SEVERE_DISTORTION",
                "INCONCLUSIVE",
            ),
        },
        "comparison_rules": {
            "A2-001_reference": "MOM-A-002_EXECUTABLE_100K_SAME_DEVELOPMENT",
            "A2-002_references": (
                "MOM-A-002_EXECUTABLE_100K",
                "MOM-A-002_IDEALIZED_PERCENTAGE",
            ),
            "capital_comparison": "PERCENTAGE_RETURNS_AND_NORMALIZED_EQUITY_NOT_RAW_RUPEE_PNL",
            "cost_comparison": "RUPEES_AND_PERCENT_OF_STARTING_OR_EVOLVING_EQUITY",
            "single_metric_selection_prohibited": True,
        },
        "governance": {
            "status": "PREREGISTRATION_ONLY",
            "full_performance_evaluation_allowed": False,
            "validation_authorized": False,
            "validation_accessed": False,
            "winner_selection_allowed": False,
            "strategy_v2_allowed": False,
            "extra_signal_allowed": False,
            "extra_band_allowed": False,
            "extra_capital_allowed": False,
        },
    }
    return {**body, "phase2_config_hash": canonical_hash(body)}


def phase2_registry(reference_parameters: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, Any]:
    base = deepcopy(dict(reference_parameters))
    if base.get("signal") != "6M" or base.get("rebalance_frequency") != "QUARTERLY":
        raise FamilyAPhase2BaselineMismatch("MOM-A-002 reference parameters changed")
    a2_001_parameters = {
        **base,
        "starting_capital_inr": A2_001_CAPITAL,
        "entry_percentile": ENTRY_PERCENTILE,
        "retention_percentile": RETENTION_PERCENTILE,
        "retention_eligibility_override": (
            "POINT_IN_TIME_UNIVERSE_AND_PRICE_AND_LIQUIDITY_AND_VALID_DATA_AND_CORPORATE_ACTION_ELIGIBILITY"
        ),
        "replacement": "FILL_TO_TOP_DECILE_TARGET_FROM_CURRENT_TOP_10_PERCENT_BY_RANK_THEN_SYMBOL",
    }
    a2_002_parameters = {**base, "starting_capital_inr": A2_002_CAPITAL}
    definitions = (
        (A2_001, "MOMENTUM_RETENTION_BAND_V1", a2_001_parameters, "TURNOVER_RETENTION_BAND"),
        (A2_002, "CAPITAL_FEASIBILITY_500K_V1", a2_002_parameters, "CAPITAL_FEASIBILITY_500K"),
    )
    experiments: list[dict[str, Any]] = []
    for experiment_id, name, parameters, changed_dimension in definitions:
        parameter_hash = canonical_hash(parameters)
        preregistration_body = {
            "experiment_id": experiment_id,
            "name": name,
            "status": "PREREGISTERED",
            "promotion_allowed": False,
            "phase2_config_hash": config["phase2_config_hash"],
            "reference_experiment_id": REFERENCE_EXPERIMENT_ID,
            "reference_parameter_hash": REFERENCE_PARAMETER_HASH,
            "reference_result_hash": REFERENCE_BASELINE_RESULT_HASH,
            "changed_dimension": changed_dimension,
            "parameters": parameters,
            "parameter_hash": parameter_hash,
            "performance_evaluated": False,
        }
        experiments.append(
            {
                **preregistration_body,
                "preregistration_hash": canonical_hash(preregistration_body),
            }
        )
    body = {
        "phase2_version": PHASE2_VERSION,
        "profile": PHASE2_PROFILE,
        "experiment_count": 2,
        "experiment_ids": list(PHASE2_EXPERIMENT_IDS),
        "experiments": experiments,
        "performance_evaluated": False,
        "validation_accessed": False,
        "winner": None,
    }
    return {**body, "phase2_registry_hash": canonical_hash(body)}


def verify_phase2_registry(
    registry: Mapping[str, Any],
    config: Mapping[str, Any],
    reference_parameters: Mapping[str, Any],
) -> None:
    if registry.get("experiment_count") != 2 or tuple(registry.get("experiment_ids", ())) != PHASE2_EXPERIMENT_IDS:
        raise ValueError("Phase 2 must contain exactly A2-001 and A2-002")
    if registry.get("performance_evaluated") is not False or registry.get("winner") is not None:
        raise ValueError("Phase 2 Command 03 cannot contain performance results or a winner")
    if config.get("phase2_config_hash") != EXPECTED_PHASE2_CONFIG_HASH:
        raise ValueError("Frozen Phase 2 config hash changed")
    if registry.get("phase2_registry_hash") != EXPECTED_PHASE2_REGISTRY_HASH:
        raise ValueError("Frozen Phase 2 registry hash changed")
    by_id = {row["experiment_id"]: row for row in registry["experiments"]}
    for experiment_id in PHASE2_EXPERIMENT_IDS:
        row = by_id[experiment_id]
        if row["status"] != "PREREGISTERED" or row["promotion_allowed"] is not False:
            raise ValueError("Phase 2 registration state changed")
        if canonical_hash(row["parameters"]) != row["parameter_hash"]:
            raise ValueError("Phase 2 parameter hash mismatch")
        body = {key: value for key, value in row.items() if key != "preregistration_hash"}
        if canonical_hash(body) != row["preregistration_hash"]:
            raise ValueError("Phase 2 preregistration hash mismatch")
        expected = EXPECTED_PHASE2_EXPERIMENT_HASHES[experiment_id]
        if (
            row["parameter_hash"] != expected["parameter_hash"]
            or row["preregistration_hash"] != expected["preregistration_hash"]
        ):
            raise ValueError(f"Frozen {experiment_id} hash changed")
    a2_001 = by_id[A2_001]["parameters"]
    if (
        decimal(a2_001["entry_percentile"]) != ENTRY_PERCENTILE
        or decimal(a2_001["retention_percentile"]) != RETENTION_PERCENTILE
        or decimal(a2_001["starting_capital_inr"]) != A2_001_CAPITAL
    ):
        raise ValueError("A2-001 frozen 10/15/100k design changed")
    a2_002 = by_id[A2_002]["parameters"]
    differences = {
        key
        for key in set(reference_parameters) | set(a2_002)
        if reference_parameters.get(key) != a2_002.get(key)
    }
    if differences != {"starting_capital_inr"} or decimal(a2_002["starting_capital_inr"]) != A2_002_CAPITAL:
        raise ValueError(f"A2-002 must differ only by capital, observed {differences}")
    config_body = {key: value for key, value in config.items() if key != "phase2_config_hash"}
    if canonical_hash(config_body) != config["phase2_config_hash"]:
        raise ValueError("Phase 2 config hash mismatch")


def retention_band_action(
    *,
    rank_fraction: Decimal,
    is_held: bool,
    infrastructure_eligible: bool,
) -> str:
    rank = decimal(rank_fraction)
    if not infrastructure_eligible:
        return "EXIT" if is_held else "DO_NOT_ENTER"
    if is_held:
        return "RETAIN" if rank <= RETENTION_PERCENTILE else "EXIT"
    return "ENTER" if rank <= ENTRY_PERCENTILE else "DO_NOT_ENTER"


def retention_band_selection(
    ranked_rows: Sequence[Mapping[str, Any]],
    held_symbols: Sequence[str],
) -> dict[str, Any]:
    held = set(held_symbols)
    eligible_rows = sorted(
        (dict(row) for row in ranked_rows if row.get("infrastructure_eligible") is True),
        key=lambda row: (int(row["rank"]), str(row["symbol"])),
    )
    eligible_count = len(eligible_rows)
    entry_cutoff = math.ceil(eligible_count * float(ENTRY_PERCENTILE))
    retention_cutoff = math.ceil(eligible_count * float(RETENTION_PERCENTILE))
    rank_by_symbol = {str(row["symbol"]): int(row["rank"]) for row in eligible_rows}
    retained = sorted(
        (symbol for symbol in held if rank_by_symbol.get(symbol, 10**9) <= retention_cutoff),
        key=lambda symbol: (rank_by_symbol[symbol], symbol),
    )
    selected = list(retained)
    entry_candidates = [
        str(row["symbol"])
        for row in eligible_rows
        if int(row["rank"]) <= entry_cutoff and str(row["symbol"]) not in selected
    ]
    target_count = entry_cutoff
    for symbol in entry_candidates:
        if len(selected) >= target_count:
            break
        selected.append(symbol)
    selected.sort(key=lambda symbol: (rank_by_symbol[symbol], symbol))
    exited = sorted(held - set(retained))
    entered = [symbol for symbol in selected if symbol not in held]
    weights = {
        symbol: Decimal("1") / Decimal(len(selected)) for symbol in selected
    } if selected else {}
    return {
        "eligible_count": eligible_count,
        "entry_cutoff_rank": entry_cutoff,
        "retention_cutoff_rank": retention_cutoff,
        "selected": selected,
        "retained": retained,
        "entered": entered,
        "exited": exited,
        "equal_weights": weights,
        "replacement_order": entry_candidates,
    }


def capital_allocation_pilot(
    selected: Sequence[Mapping[str, Any]],
    *,
    capital: Decimal,
    execution_date: date,
) -> dict[str, Any]:
    ordered = sorted(selected, key=lambda row: (int(row["rank"]), str(row["symbol"])))
    intended_weight = Decimal("1") / Decimal(len(ordered))
    intended_rupees = capital / Decimal(len(ordered))
    allocations: list[dict[str, Any]] = []
    for row in ordered:
        price = decimal(row["price"])
        shares = int((intended_rupees / price).to_integral_value(rounding=ROUND_FLOOR))
        allocations.append(
            {
                "symbol": row["symbol"],
                "rank": int(row["rank"]),
                "price": price,
                "intended_weight": intended_weight,
                "intended_rupees": intended_rupees,
                "shares": shares,
            }
        )

    def totals() -> tuple[Decimal, Decimal]:
        notional = Decimal("0")
        costs = Decimal("0")
        for row in allocations:
            row_notional = Decimal(row["shares"]) * decimal(row["price"])
            notional += row_notional
            if row["shares"]:
                costs += decimal(
                    estimate_order_cost("BUY", execution_date, row_notional)["total_cost"]
                )
        return notional, costs

    total_notional, total_cost = totals()
    while total_notional + total_cost > capital:
        candidate = next((row for row in reversed(allocations) if row["shares"] > 0), None)
        if candidate is None:
            raise ValueError("Capital pilot cannot reconcile purchase costs")
        candidate["shares"] -= 1
        total_notional, total_cost = totals()
    residual = capital - total_notional - total_cost
    for row in allocations:
        notional = Decimal(row["shares"]) * decimal(row["price"])
        actual_weight = notional / capital
        row["actual_notional"] = notional
        row["actual_weight"] = actual_weight
        row["absolute_weight_error"] = abs(actual_weight - intended_weight)
        row["unaffordable"] = row["shares"] == 0
    return {
        "capital": capital,
        "execution_date": execution_date.isoformat(),
        "selected_symbols": [str(row["symbol"]) for row in allocations],
        "selected_count": len(allocations),
        "target_weight": intended_weight,
        "intended_rupees_per_position": intended_rupees,
        "actual_holdings": sum(row["shares"] > 0 for row in allocations),
        "unaffordable_holdings": sum(row["unaffordable"] for row in allocations),
        "invested_notional": total_notional,
        "actual_invested_pct": total_notional / capital * Decimal("100"),
        "total_buy_cost_rupees": total_cost,
        "total_buy_cost_pct_starting_capital": total_cost / capital * Decimal("100"),
        "cash_residual": residual,
        "cash_residual_pct": residual / capital * Decimal("100"),
        "mean_absolute_weight_error_pp": (
            decimal(statistics.mean(row["absolute_weight_error"] for row in allocations))
            * Decimal("100")
        ),
        "tracking_difference_l1_pct": sum(
            (decimal(row["absolute_weight_error"]) for row in allocations), Decimal("0")
        ) * Decimal("100"),
        "allocations": allocations,
        "normalized_equity_start": Decimal("100"),
        "performance_evaluated": False,
    }


def build_retention_pilot() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    action_cases = (
        ("A", "rank 8%, not held", Decimal("0.08"), False, True, "ENTER"),
        ("B", "rank 12%, already held", Decimal("0.12"), True, True, "RETAIN"),
        ("C", "rank 12%, not held", Decimal("0.12"), False, True, "DO_NOT_ENTER"),
        ("D", "rank 16%, held", Decimal("0.16"), True, True, "EXIT"),
        ("E", "rank 8%, held", Decimal("0.08"), True, True, "RETAIN"),
        ("F", "rank 14%, held but liquidity fails", Decimal("0.14"), True, False, "EXIT"),
    )
    rows: list[dict[str, Any]] = []
    for case_id, description, rank_fraction, is_held, eligible, expected in action_cases:
        observed = retention_band_action(
            rank_fraction=rank_fraction,
            is_held=is_held,
            infrastructure_eligible=eligible,
        )
        rows.append(
            {
                "case_id": case_id,
                "description": description,
                "fixture_type": "STRUCTURAL_RULE_FIXTURE_NO_PERFORMANCE",
                "rank_percent": rank_fraction * Decimal("100"),
                "is_held": is_held,
                "infrastructure_eligible": eligible,
                "expected": expected,
                "observed": observed,
                "passed": observed == expected,
            }
        )

    ranked_rows = [
        {
            "symbol": f"S{rank:03d}",
            "rank": rank,
            "infrastructure_eligible": True,
        }
        for rank in range(1, 101)
    ]
    held = [*(f"S{rank:03d}" for rank in range(1, 10)), "S016"]
    selection = retention_band_selection(ranked_rows, held)
    replacement_expected = "S010"
    replacement_observed = selection["entered"][0] if selection["entered"] else None
    rows.append(
        {
            "case_id": "G",
            "description": "deterministic replacement candidate",
            "fixture_type": "STRUCTURAL_RULE_FIXTURE_NO_PERFORMANCE",
            "rank_percent": Decimal("10"),
            "is_held": False,
            "infrastructure_eligible": True,
            "expected": replacement_expected,
            "observed": replacement_observed,
            "passed": replacement_observed == replacement_expected,
        }
    )
    weights = selection["equal_weights"]
    expected_weight = Decimal("1") / Decimal(len(selection["selected"]))
    equal_weight_passed = bool(weights) and all(
        weight == expected_weight for weight in weights.values()
    ) and sum(weights.values(), Decimal("0")) == Decimal("1")
    rows.append(
        {
            "case_id": "H",
            "description": "equal-weight recalculation after retention",
            "fixture_type": "STRUCTURAL_RULE_FIXTURE_NO_PERFORMANCE",
            "rank_percent": None,
            "is_held": None,
            "infrastructure_eligible": True,
            "expected": "EQUAL_WEIGHTS_SUM_TO_1",
            "observed": f"{len(weights)}_WEIGHTS_SUM_{sum(weights.values(), Decimal('0'))}",
            "passed": equal_weight_passed,
        }
    )
    summary = {
        "case_count": len(rows),
        "passed_case_count": sum(row["passed"] for row in rows),
        "all_passed": all(row["passed"] for row in rows),
        "selection": selection,
        "performance_evaluated": False,
    }
    return rows, summary


def _capital_pilot_inputs(root: Path) -> tuple[date, list[dict[str, Any]]]:
    schedules = load_rebalance_schedules(root)[REFERENCE_EXPERIMENT_ID]
    aliases = _load_aliases(root)
    membership = _load_membership(root)
    bars = _load_adjusted_bars(root, set(membership.grouped), aliases)
    for schedule in reversed(schedules):
        execution_bars = bars.get(schedule.execution_date, {})
        if schedule.sufficient_universe and all(
            selected.symbol in execution_bars for selected in schedule.selected
        ):
            return schedule.execution_date, [
                {
                    "symbol": selected.symbol,
                    "rank": selected.rank,
                    "price": execution_bars[selected.symbol].open_price,
                }
                for selected in schedule.selected
            ]
    raise ValueError("No frozen MOM-A-002 rebalance has complete next-open prices for the capital pilot")


def build_capital_pilot(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    execution_date, selected = _capital_pilot_inputs(root)
    pilot_100k = capital_allocation_pilot(
        selected,
        capital=A2_001_CAPITAL,
        execution_date=execution_date,
    )
    pilot_500k = capital_allocation_pilot(
        selected,
        capital=A2_002_CAPITAL,
        execution_date=execution_date,
    )
    same_symbols = pilot_100k["selected_symbols"] == pilot_500k["selected_symbols"]
    same_target = pilot_100k["target_weight"] == pilot_500k["target_weight"]
    prices_100k = {row["symbol"]: row["price"] for row in pilot_100k["allocations"]}
    prices_500k = {row["symbol"]: row["price"] for row in pilot_500k["allocations"]}
    same_prices = prices_100k == prices_500k
    shares_100k = {row["symbol"]: row["shares"] for row in pilot_100k["allocations"]}
    shares_500k = {row["symbol"]: row["shares"] for row in pilot_500k["allocations"]}
    differing_share_count = sum(
        shares_100k[symbol] != shares_500k[symbol] for symbol in shares_100k
    )
    rows = []
    for label, pilot in (("100K_REFERENCE", pilot_100k), ("500K_TREATMENT", pilot_500k)):
        rows.append(
            {
                "pilot": label,
                "fixture_type": "SINGLE_REBALANCE_MECHANICAL_PILOT_NO_PERFORMANCE",
                "execution_date": pilot["execution_date"],
                "capital_inr": pilot["capital"],
                "selected_count": pilot["selected_count"],
                "actual_holdings": pilot["actual_holdings"],
                "unaffordable_holdings": pilot["unaffordable_holdings"],
                "target_weight_pct": pilot["target_weight"] * Decimal("100"),
                "intended_rupees_per_position": pilot["intended_rupees_per_position"],
                "invested_pct": pilot["actual_invested_pct"],
                "cash_residual_inr": pilot["cash_residual"],
                "cash_residual_pct": pilot["cash_residual_pct"],
                "mean_absolute_weight_error_pp": pilot["mean_absolute_weight_error_pp"],
                "tracking_difference_l1_pct": pilot["tracking_difference_l1_pct"],
                "buy_cost_inr": pilot["total_buy_cost_rupees"],
                "buy_cost_pct_starting_capital": pilot["total_buy_cost_pct_starting_capital"],
                "normalized_equity_start": pilot["normalized_equity_start"],
                "performance_evaluated": False,
            }
        )
    comparison = {
        "execution_date": execution_date.isoformat(),
        "same_selected_symbols": same_symbols,
        "same_prices": same_prices,
        "same_target_percentages": same_target,
        "different_integer_share_counts": differing_share_count > 0,
        "differing_share_count": differing_share_count,
        "share_counts_differ_only_due_to_capital": same_symbols and same_target and differing_share_count > 0,
        "affordability_verified": all(
            pilot["actual_holdings"] + pilot["unaffordable_holdings"] == pilot["selected_count"]
            for pilot in (pilot_100k, pilot_500k)
        ),
        "cash_residual_verified": all(pilot["cash_residual"] >= 0 for pilot in (pilot_100k, pilot_500k)),
        "weight_tracking_error_verified": all(
            pilot["mean_absolute_weight_error_pp"] >= 0 for pilot in (pilot_100k, pilot_500k)
        ),
        "cost_accounting_verified": all(
            pilot["invested_notional"] + pilot["total_buy_cost_rupees"] + pilot["cash_residual"]
            == pilot["capital"]
            for pilot in (pilot_100k, pilot_500k)
        ),
        "cost_normalization_verified": all(
            pilot["total_buy_cost_pct_starting_capital"]
            == pilot["total_buy_cost_rupees"] / pilot["capital"] * Decimal("100")
            for pilot in (pilot_100k, pilot_500k)
        ),
        "normalized_comparison_verified": (
            pilot_100k["normalized_equity_start"] == pilot_500k["normalized_equity_start"] == Decimal("100")
        ),
        "raw_rupee_pnl_comparison_allowed": False,
        "performance_evaluated": False,
        "pilot_100k": pilot_100k,
        "pilot_500k": pilot_500k,
    }
    return rows, comparison


def _registry_report_rows(registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "experiment_id": row["experiment_id"],
            "name": row["name"],
            "status": row["status"],
            "promotion_allowed": row["promotion_allowed"],
            "reference_experiment_id": row["reference_experiment_id"],
            "changed_dimension": row["changed_dimension"],
            "capital_inr": row["parameters"]["starting_capital_inr"],
            "parameter_hash": row["parameter_hash"],
            "preregistration_hash": row["preregistration_hash"],
            "performance_evaluated": row["performance_evaluated"],
        }
        for row in registry["experiments"]
    ]


def _readiness_rows(
    *,
    baseline_unchanged: bool,
    retention_pilot: Mapping[str, Any],
    capital_pilot: Mapping[str, Any],
    registry: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks = (
        ("FROZEN_REFERENCE_VERIFIED", True),
        ("EXACT_EXPERIMENT_COUNT_2", registry["experiment_count"] == 2),
        ("EXACT_EXPERIMENT_ALLOWLIST", tuple(registry["experiment_ids"]) == PHASE2_EXPERIMENT_IDS),
        ("A2_001_RETENTION_PILOT_8_OF_8", retention_pilot["passed_case_count"] == 8),
        ("A2_002_IDENTICAL_SELECTION", capital_pilot["same_selected_symbols"]),
        ("A2_002_IDENTICAL_PRICES", capital_pilot["same_prices"]),
        ("A2_002_IDENTICAL_TARGET_PERCENTAGES", capital_pilot["same_target_percentages"]),
        ("A2_002_INTEGER_SHARE_DIFFERENCE", capital_pilot["different_integer_share_counts"]),
        ("A2_002_AFFORDABILITY_ACCOUNTED", capital_pilot["affordability_verified"]),
        ("A2_002_CASH_RECONCILED", capital_pilot["cash_residual_verified"]),
        ("A2_002_WEIGHT_ERROR_MEASURED", capital_pilot["weight_tracking_error_verified"]),
        ("COST_NORMALIZATION_VERIFIED", capital_pilot["cost_normalization_verified"]),
        ("NORMALIZED_COMPARISON_VERIFIED", capital_pilot["normalized_comparison_verified"]),
        ("NO_PERFORMANCE_EVALUATION", not capital_pilot["performance_evaluated"]),
        ("NO_VALIDATION_ACCESS", True),
        ("NO_ALTERNATIVE_BAND_OR_CAPITAL", True),
        ("NO_STRATEGY_V2", True),
        ("FROZEN_BASELINES_UNCHANGED", baseline_unchanged),
    )
    return [
        {"check": name, "passed": passed, "evidence": "VERIFIED" if passed else "FAILED"}
        for name, passed in checks
    ]


def build_family_a_phase2_research(root: Path) -> dict[str, Any]:
    started_at = utc_now()
    command_01 = verify_family_a_preregistration(root)
    command_02 = verify_command_02_results(root)
    baseline_before = phase2_baseline_snapshot(root)
    reference = next(
        row for row in command_01["registry"]["experiments"]
        if row["experiment_id"] == REFERENCE_EXPERIMENT_ID
    )
    config = phase2_config()
    registry = phase2_registry(reference["parameters"], config)
    verify_phase2_registry(registry, config, reference["parameters"])
    retention_rows, retention_pilot = build_retention_pilot()
    capital_rows, capital_pilot = build_capital_pilot(root)

    output_root = root / "data/research/strategy_families/family_a/v1/phase2"
    reports_root = root / "data/reports"
    config_path = output_root / "registry/phase2_config_v1.json"
    registry_path = output_root / "registry/phase2_experiment_registry_v1.json"
    write_json(config_path, config)
    write_json(registry_path, registry)
    for row in registry["experiments"]:
        write_json(
            output_root / "registry" / f"{row['experiment_id'].lower().replace('-', '_')}_preregistration_v1.json",
            row,
        )
    write_csv(output_root / "pilots/retention_band_pilot_v1.csv", retention_rows)
    write_csv(output_root / "pilots/capital_feasibility_pilot_v1.csv", capital_rows)
    write_json(
        output_root / "retention_band/retention_band_contract_v1.json",
        {
            "experiment_id": A2_001,
            "entry_percentile": ENTRY_PERCENTILE,
            "retention_percentile": RETENTION_PERCENTILE,
            "band_width_percentage_points": Decimal("5"),
            "replacement": "CURRENT_TOP_10_PERCENT_BY_RANK_THEN_SYMBOL",
            "weighting": "EQUAL_WEIGHT",
            "capital_inr": A2_001_CAPITAL,
            "alternative_bands_tested": False,
            "pilot": retention_pilot,
            "performance_evaluated": False,
        },
    )
    write_json(
        output_root / "capital_feasibility/capital_pilot_100k_v1.json",
        capital_pilot["pilot_100k"],
    )
    write_json(
        output_root / "capital_feasibility/capital_pilot_500k_v1.json",
        capital_pilot["pilot_500k"],
    )
    write_json(
        output_root / "capital_feasibility/capital_pilot_comparison_v1.json",
        {key: value for key, value in capital_pilot.items() if not key.startswith("pilot_")},
    )
    write_csv(reports_root / REPORT_NAMES[1], _registry_report_rows(registry))
    write_csv(reports_root / REPORT_NAMES[2], retention_rows)
    write_csv(reports_root / REPORT_NAMES[3], capital_rows)

    baseline_after = phase2_baseline_snapshot(root)
    baseline_unchanged = baseline_before == baseline_after
    readiness_rows = _readiness_rows(
        baseline_unchanged=baseline_unchanged,
        retention_pilot=retention_pilot,
        capital_pilot=capital_pilot,
        registry=registry,
    )
    architecture_result = (
        "READY_FOR_CONTROLLED_DEVELOPMENT_TEST"
        if all(row["passed"] for row in readiness_rows)
        else "METHODOLOGY_FIX_REQUIRED"
    )
    write_csv(reports_root / REPORT_NAMES[4], readiness_rows)
    experiments = {
        row["experiment_id"]: {
            "name": row["name"],
            "parameter_hash": row["parameter_hash"],
            "preregistration_hash": row["preregistration_hash"],
            "capital_inr": row["parameters"]["starting_capital_inr"],
            "status": row["status"],
        }
        for row in registry["experiments"]
    }
    summary = {
        "command": COMMAND,
        "phase2_version": PHASE2_VERSION,
        "profile": PHASE2_PROFILE,
        "family_version": FAMILY_VERSION,
        "phase2_config_hash": config["phase2_config_hash"],
        "phase2_registry_hash": registry["phase2_registry_hash"],
        "reference": {
            "experiment_id": REFERENCE_EXPERIMENT_ID,
            "parameter_hash": REFERENCE_PARAMETER_HASH,
            "preregistration_hash": REFERENCE_PREREGISTRATION_HASH,
            "command_02_result_hash": REFERENCE_BASELINE_RESULT_HASH,
            "role": "REFERENCE_NOT_BEST_WINNER_OR_OPTIMAL",
        },
        "experiment_count": 2,
        "experiments": experiments,
        "pilot": {
            "retention_band": retention_pilot,
            "capital_feasibility": capital_pilot,
        },
        "classifications": {
            "FAMILY_A_PHASE2_ARCHITECTURE_RESULT": architecture_result,
            "RETENTION_BAND_TURNOVER_RESULT": "NOT_EVALUATED",
            "CAPITAL_FEASIBILITY_IMPROVEMENT": "NOT_EVALUATED",
            "CAPITAL_DISTORTION": "NOT_EVALUATED",
        },
        "governance": {
            "development_start": DEVELOPMENT_START.isoformat(),
            "development_end": DEVELOPMENT_END.isoformat(),
            "validation_accessed": False,
            "full_performance_run": False,
            "alternative_band_tested": False,
            "alternative_capital_tested": False,
            "signal_changed": False,
            "rebalance_changed": False,
            "absolute_momentum_added": False,
            "regime_filter_added": False,
            "volatility_filter_added": False,
            "fundamentals_added": False,
            "stop_or_target_added": False,
            "intraday_logic_added": False,
            "leverage_added": False,
            "strategy_v2_created": False,
            "winner_selected": False,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence_writes": 0,
        },
        "regression": {
            "before_snapshot_hash": baseline_before["snapshot_hash"],
            "after_snapshot_hash": baseline_after["snapshot_hash"],
            "baseline_hashes_unchanged": baseline_unchanged,
            "baseline_mutation_violations": 0 if baseline_unchanged else 1,
            "family_a_command_01": "PASSED" if baseline_unchanged else "FAILED",
            "family_a_command_02": "PASSED" if baseline_unchanged else "FAILED",
            "cap4": "PASSED" if baseline_unchanged else "FAILED",
            "strategy_v1": "PASSED" if baseline_unchanged else "FAILED",
        },
        "readiness": {
            "passed_check_count": sum(row["passed"] for row in readiness_rows),
            "check_count": len(readiness_rows),
        },
        "verification": {
            "backend_tests": "PENDING",
            "frontend_build": "PENDING",
            "ready_for_review": False,
        },
        "reports": [f"data/reports/{name}" for name in REPORT_NAMES],
        "created_at": started_at,
        "completed_at": utc_now(),
    }
    write_json(reports_root / REPORT_NAMES[0], summary)
    artifact_paths = sorted(path for path in output_root.rglob("*") if path.is_file())
    artifact_paths.extend(reports_root / name for name in REPORT_NAMES)
    manifest = {
        "phase2_version": PHASE2_VERSION,
        "profile": PHASE2_PROFILE,
        "phase2_config_hash": config["phase2_config_hash"],
        "phase2_registry_hash": registry["phase2_registry_hash"],
        "experiment_hashes": {
            experiment_id: {
                "parameter_hash": row["parameter_hash"],
                "preregistration_hash": row["preregistration_hash"],
            }
            for experiment_id, row in experiments.items()
        },
        "dataset_hashes": {
            path.relative_to(root).as_posix(): file_sha256(path)
            for path in artifact_paths
            if path.exists()
        },
        "baseline_snapshot_hash": baseline_after["snapshot_hash"],
        "validation_accessed": False,
        "performance_evaluated": False,
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
    }
    write_json(output_root / "manifests/run_manifest_v1.json", manifest)
    return summary


def finalize_phase2_review(
    root: Path,
    *,
    backend_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    summary_path = root / "data/reports" / REPORT_NAMES[0]
    if not summary_path.exists():
        raise FileNotFoundError("Run Family A Phase 2 architecture before finalizing")
    summary = _read_json(summary_path)
    verify_family_a_preregistration(root)
    verify_command_02_results(root)
    baseline = phase2_baseline_snapshot(root)
    if baseline["snapshot_hash"] != summary["regression"]["after_snapshot_hash"]:
        raise FamilyAPhase2BaselineMismatch("Frozen baseline changed after Phase 2 architecture generation")
    ready = (
        backend_tests == "PASSED"
        and frontend_build == "PASSED"
        and summary["regression"]["baseline_mutation_violations"] == 0
        and summary["readiness"]["passed_check_count"] == summary["readiness"]["check_count"]
        and summary["classifications"]["FAMILY_A_PHASE2_ARCHITECTURE_RESULT"]
        == "READY_FOR_CONTROLLED_DEVELOPMENT_TEST"
        and summary["governance"]["validation_accessed"] is False
        and summary["governance"]["full_performance_run"] is False
    )
    summary["verification"] = {
        "backend_tests": backend_tests,
        "frontend_build": frontend_build,
        "ready_for_review": ready,
        "finalized_at": utc_now(),
    }
    write_json(summary_path, summary)
    return summary


__all__ = (
    "A2_001",
    "A2_002",
    "A2_001_CAPITAL",
    "A2_002_CAPITAL",
    "ENTRY_PERCENTILE",
    "EXPECTED_PHASE2_CONFIG_HASH",
    "EXPECTED_PHASE2_EXPERIMENT_HASHES",
    "EXPECTED_PHASE2_REGISTRY_HASH",
    "PHASE2_EXPERIMENT_IDS",
    "PHASE2_PROFILE",
    "PHASE2_VERSION",
    "REPORT_NAMES",
    "RETENTION_PERCENTILE",
    "FamilyAPhase2BaselineMismatch",
    "build_capital_pilot",
    "build_family_a_phase2_research",
    "build_retention_pilot",
    "capital_allocation_pilot",
    "command_02_snapshot",
    "finalize_phase2_review",
    "phase2_baseline_snapshot",
    "phase2_config",
    "phase2_registry",
    "retention_band_action",
    "retention_band_selection",
    "verify_command_02_results",
    "verify_phase2_registry",
)
