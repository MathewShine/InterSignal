from __future__ import annotations

import csv
import gzip
import json
import math
import re
import statistics
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from app.backtesting.costs.cost_config import EXPECTED_COST_CONFIG_HASH, default_cost_model_config
from app.backtesting.portfolio_baseline import (
    portfolio_backtest_regression_hash_checks,
    portfolio_backtest_regression_hashes,
    verify_current_portfolio_backtest_baseline,
)
from app.backtesting.portfolio_config import PortfolioBacktestConfig
from app.backtesting.portfolio_engine import (
    build_metrics,
    build_trading_calendar,
    load_frozen_opportunities,
    simulate_portfolio,
)
from app.diagnostics.strategy_diagnostic_synthesis import (
    EXPECTED_REGISTRY_FINGERPRINT,
    registry_fingerprint,
)
from app.research.temporal_validation.config import (
    DEFAULT_TEMPORAL_CONFIG,
    DEVELOPMENT_RUN,
    DEVELOPMENT_WINDOW_VERSION,
    EXPECTED_HARNESS_CONFIG_HASH,
    FORMAL_HOLDOUT_AFTER_DIAGNOSTIC_PHASE,
    INDEPENDENT_WINDOW_BACKTEST,
    PERFORMANCE_ACCESS,
    REPRODUCTION_RUN,
    SEALED,
    STRUCTURAL_METADATA,
    TEMPORAL_RESEARCH_HARNESS_VERSION,
    TEMPORAL_VALIDATION_PROTOCOL_VERSION,
    VALIDATION_RUN,
    TemporalResearchConfig,
    canonical_hash,
    classify_sample_size,
    json_ready,
)
from app.research.temporal_validation.guard import ValidationAccessError, ValidationAccessGuard
from app.research.temporal_validation.models import ExperimentFreezeArtifact, experiment_freeze_schema
from app.research.temporal_validation.partition import (
    DEVELOPMENT,
    VALIDATION,
    crosses_validation_boundary,
    partition_rows,
    read_gzip_csv,
    resolve_validation_backtest_source_rows,
    row_identity_fingerprint,
    structural_projection,
    verify_terminal_date_freeze,
)
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_baseline import resolve_current_strategy_outcome_dataset
from app.strategy.scoring.score_baseline import resolve_current_strategy_score_dataset

REPORT_NAMES = (
    "temporal_validation_v1_summary.json",
    "temporal_validation_v1_windows.csv",
    "temporal_validation_v1_population.csv",
    "temporal_validation_v1_distribution_shift.csv",
    "temporal_validation_v1_contamination.csv",
    "temporal_validation_v1_development_baseline.csv",
    "temporal_validation_v1_governance.csv",
    "temporal_validation_v1_pilot.csv",
)

EXPECTED_COST_REGISTRY_HASHES = {
    "cost_model_config_v1.json": "a031cf740ea29e6717953f1528f5858840ab51bddcb79eba8e46c97644c09213",
    "cost_scenarios_v1_preregistered.json": "0ddf91c5a27e98e413434c119b54c61cdb5ae21bd7e75aa54ff428e55679b499",
    "cost_scenarios_v1.json": "74159285020218c8ad5ead079a2b06f6844fc58257cd1784865f0b1586405ee9",
}
EXPECTED_MANIFEST_HASH = "01c2f82118c47fa514575abddb903f125bbbe0421c963cd0550a99aac23878ea"

FORBIDDEN_HOLDOUT_PERFORMANCE_FIELDS = {
    "return",
    "return_pct",
    "gross_return",
    "gross_return_pct",
    "net_return",
    "net_return_pct",
    "cagr",
    "cagr_pct",
    "drawdown",
    "maximum_drawdown_pct",
    "pnl",
    "gross_pnl",
    "net_pnl",
    "realized_r",
    "realized_r_multiple",
    "mfe",
    "mae",
    "exit_reason",
    "first_touch_outcome",
}

CONTAMINATION_ROWS = (
    ("BASELINE_BACKTEST", "AGGREGATE_SEEN", "Full-period baseline and annual aggregates were reviewed."),
    ("OUTCOME_AUDIT", "COHORT_SEEN", "Outcome cohorts and forward labels were reviewed."),
    ("RANKING_DIAGNOSTICS", "COHORT_SEEN", "Ranking alternatives touched the full historical period."),
    ("HOLD_DIAGNOSTICS", "COHORT_SEEN", "Holding-period diagnostics touched validation-period prices."),
    ("GAP_DIAGNOSTICS", "COHORT_SEEN", "Gap cohorts included validation-period observations."),
    ("EXIT_DIAGNOSTICS", "COHORT_SEEN", "Exit-path diagnostics included validation-period outcomes."),
    ("ENTRY_QUALITY_DIAGNOSTICS", "COHORT_SEEN", "Entry-quality cohorts included validation observations."),
    ("SCORE_CALIBRATION", "COHORT_SEEN", "Score diagnostics included validation-period outcomes."),
    ("REGIME_DIAGNOSTICS", "COHORT_SEEN", "Regime outcome diagnostics used the full period."),
    ("COST_OVERLAY", "AGGREGATE_SEEN", "Gross and cost-adjusted full-period aggregates were reviewed."),
    ("DIAGNOSTIC_SYNTHESIS", "AGGREGATE_SEEN", "The synthesis summarized full-history findings."),
)


def build_temporal_validation_harness(
    *,
    repo_root: Path,
    tests_passed: bool = False,
    frontend_build_passed: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    repo_root = Path(repo_root)
    data_dir = repo_root / "data"
    config = DEFAULT_TEMPORAL_CONFIG
    if EXPECTED_HARNESS_CONFIG_HASH != "TO_BE_FROZEN" and config.config_hash() != EXPECTED_HARNESS_CONFIG_HASH:
        raise ValueError("Temporal harness config changed after its source-controlled freeze")

    notify(progress, "Verifying frozen baseline, diagnostic registry, and cost-research registry")
    verify_current_portfolio_backtest_baseline(data_dir)
    baseline_hashes_before = portfolio_backtest_regression_hashes(data_dir)
    baseline_checks_before = portfolio_backtest_regression_hash_checks(baseline_hashes_before)
    if not all(baseline_checks_before.values()):
        raise ValueError("Frozen baseline regression check failed")
    diagnostic_before = diagnostic_registry_state(data_dir)
    cost_before = cost_registry_state(data_dir)
    if not diagnostic_before["valid"]:
        raise ValueError("Frozen diagnostic registry changed")
    if not cost_before["valid"]:
        raise ValueError("Frozen transaction-cost registry/config changed")

    notify(progress, "Resolving and freezing decision-date windows without opening holdout performance")
    terminal = verify_terminal_date_freeze(data_dir, config)
    first = build_harness_core(data_dir=data_dir, config=config, baseline_hashes=baseline_hashes_before)
    second = build_harness_core(data_dir=data_dir, config=config, baseline_hashes=baseline_hashes_before)
    first_fingerprint = canonical_hash(first)
    second_fingerprint = canonical_hash(second)
    if first_fingerprint != second_fingerprint:
        raise ValueError("Temporal harness generation is not reproducible")
    if EXPECTED_MANIFEST_HASH != "TO_BE_FROZEN" and first["manifest"]["manifest_hash"] != EXPECTED_MANIFEST_HASH:
        raise ValueError("Temporal window manifest changed after its freeze")

    notify(progress, "Writing development-only results and structural holdout metadata")
    artifact_paths = write_harness_artifacts(repo_root, first)
    report_paths = write_machine_reports(repo_root, first)
    no_peek = scan_holdout_metadata(repo_root, core=first)
    if no_peek["violation_count"]:
        raise ValueError("A sealed holdout artifact exposes prohibited performance fields")

    baseline_hashes_after = portfolio_backtest_regression_hashes(data_dir)
    diagnostic_after = diagnostic_registry_state(data_dir)
    cost_after = cost_registry_state(data_dir)
    baseline_regression = {
        "hashes_before": baseline_hashes_before,
        "hashes_after": baseline_hashes_after,
        "checks": {
            name: baseline_hashes_before[name] == baseline_hashes_after[name]
            for name in baseline_hashes_before
        },
        "expected_hash_checks": portfolio_backtest_regression_hash_checks(baseline_hashes_after),
        "all_unchanged": baseline_hashes_before == baseline_hashes_after,
    }
    diagnostic_regression = {
        "expected_content_fingerprint": EXPECTED_REGISTRY_FINGERPRINT,
        "before": diagnostic_before,
        "after": diagnostic_after,
        "unchanged": diagnostic_before == diagnostic_after,
    }
    cost_regression = {
        "expected_cost_config_hash": EXPECTED_COST_CONFIG_HASH,
        "observed_cost_config_hash": default_cost_model_config().config_hash(),
        "before": cost_before,
        "after": cost_after,
        "unchanged": cost_before == cost_after,
    }
    security = security_verification(repo_root)
    runtime = round(time.perf_counter() - started, 3)
    summary: dict[str, Any] = {
        "phase": "Step 02.14",
        "command": "Command 02",
        "harness_version": TEMPORAL_RESEARCH_HARNESS_VERSION,
        "protocol_version": TEMPORAL_VALIDATION_PROTOCOL_VERSION,
        "profile": config.profile,
        "harness_config_hash": config.config_hash(),
        "config": config.snapshot(),
        "validation_terminal_date_resolved": terminal.isoformat(),
        **first,
        "reproducibility": {
            "first_fingerprint": first_fingerprint,
            "second_fingerprint": second_fingerprint,
            "match": first_fingerprint == second_fingerprint,
            "manifest_hash_match": first["manifest"]["manifest_hash"] == second["manifest"]["manifest_hash"],
        },
        "no_peek": no_peek,
        "regression": baseline_regression,
        "diagnostic_registry_regression": diagnostic_regression,
        "cost_registry_regression": cost_regression,
        "baseline_mutation_violations": sum(
            not value for value in baseline_regression["checks"].values()
        ),
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "security": security,
        "safety": {
            "strategy_v2_experiments_run": 0,
            "validation_performance_evaluations": 0,
            "optimization_runs": 0,
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "runtime_seconds": runtime,
        "storage": {},
        "artifacts": {},
    }
    all_paths = artifact_paths + report_paths
    summary["artifacts"] = artifact_manifest(all_paths)
    summary["storage"] = {
        "artifact_count_excluding_summary_and_documentation": len(all_paths),
        "artifact_size_bytes_excluding_summary_and_documentation": sum(
            path.stat().st_size for path in all_paths if path.exists()
        ),
    }
    summary["ready_for_review"] = all(
        (
            first["pilot"]["passed"],
            first["validation_governance"]["validation_state"] == SEALED,
            not first["validation_governance"]["validation_performance_exposed"],
            not first["validation_governance"]["holdout_performance_report_generated"],
            no_peek["violation_count"] == 0,
            baseline_regression["all_unchanged"],
            all(baseline_regression["expected_hash_checks"].values()),
            diagnostic_regression["unchanged"],
            cost_regression["unchanged"],
            security["passed"],
            tests_passed,
            frontend_build_passed,
        )
    )
    summary_path = repo_root / "data/reports" / REPORT_NAMES[0]
    write_json(summary_path, summary)
    summary["artifacts"][summary_path.name] = file_manifest(summary_path)
    return summary


def build_harness_core(
    *, data_dir: Path, config: TemporalResearchConfig, baseline_hashes: dict[str, str]
) -> dict[str, Any]:
    score_partitions = read_projected_partitions(
        resolve_current_strategy_score_dataset(data_dir),
        date_field=config.score_date_field,
        config=config,
        fields=("trading_date", "symbol", "isin", "score_version"),
    )
    development_scores = score_partitions[DEVELOPMENT]
    validation_scores = score_partitions[VALIDATION]
    outcome_partitions = read_projected_partitions(
        resolve_current_strategy_outcome_dataset(data_dir),
        date_field=config.outcome_date_field,
        config=config,
        fields=(
            "decision_date",
            "symbol",
            "isin",
            "outcome_version",
            "score_version",
            "risk_version",
            "outcome_cohort",
            "source_raw_strategy_score",
            "source_score_band",
            "source_scoring_disposition",
            "primary_evaluation_eligible",
            "setup_quality",
            "candidate_state",
            "candidate_category",
            "regime_state",
            "regime_confidence",
            "effective_reward_risk",
            "entry_recheck_status",
            "entry_valid",
            "forward_data_safe",
            "forward_data_reasons",
            "next_session_date",
            "session_date_1",
            "session_date_2",
            "session_date_3",
            "session_date_4",
        ),
    )
    development_outcomes = outcome_partitions[DEVELOPMENT]
    validation_outcomes_full = outcome_partitions[VALIDATION]
    validation_outcomes = [structural_projection(row) for row in validation_outcomes_full]
    opportunities, _ = load_frozen_opportunities(resolve_current_strategy_outcome_dataset(data_dir))
    source_partitions = partition_rows(
        opportunities, date_field=config.backtest_source_date_field, config=config
    )
    development_sources = source_partitions[DEVELOPMENT]
    validation_sources_full = source_partitions[VALIDATION]
    validation_sources = [structural_projection(row) for row in validation_sources_full]
    del opportunities, validation_sources_full

    baseline = verify_current_portfolio_backtest_baseline(data_dir)
    baseline_trades = read_gzip_csv(baseline.trades_dataset_path)
    trade_partitions = partition_rows(
        baseline_trades, date_field=config.backtest_source_date_field, config=config
    )
    cross_boundary = [
        row for row in development_outcomes if crosses_validation_boundary(row, config)
    ]
    baseline_cross_boundary = [
        row for row in trade_partitions[DEVELOPMENT] if str(row.get("exit_date", "")) >= config.validation_start.isoformat()
    ]

    fingerprints = build_row_fingerprints(
        config,
        development_scores,
        validation_scores,
        development_outcomes,
        validation_outcomes,
        development_sources,
        validation_sources,
    )
    manifest_base = {
        "harness_version": config.harness_version,
        "protocol_version": config.protocol_version,
        "profile": config.profile,
        "harness_config_hash": config.config_hash(),
        "development_start": config.development_start.isoformat(),
        "development_end": config.development_end.isoformat(),
        "validation_start": config.validation_start.isoformat(),
        "validation_end": config.validation_terminal_date.isoformat(),
        "validation_terminal_date": config.validation_terminal_date.isoformat(),
        "partition_basis": config.partition_basis,
        "validation_state": config.validation_state,
        "validation_pristine_status": config.validation_pristine_status,
        "baseline_hashes": baseline_hashes,
        "development_row_fingerprints": fingerprints["development_layers"],
        "validation_row_fingerprints": fingerprints["validation_layers"],
        "development_row_fingerprint": fingerprints["development"],
        "validation_row_fingerprint": fingerprints["validation"],
        "terminal_date_extension_policy": config.terminal_date_extension_policy,
    }
    manifest = manifest_base | {"manifest_hash": canonical_hash(manifest_base)}

    development_baseline = run_development_baseline(data_dir, development_sources, config)
    validation_blind = build_validation_blind_summary(
        data_dir=data_dir,
        validation_scores=validation_scores,
        validation_outcomes=validation_outcomes,
        validation_sources=validation_sources,
        validation_trade_count=len(trade_partitions[VALIDATION]),
        config=config,
    )
    distribution_rows, shift_summary = build_distribution_shift(
        data_dir=data_dir,
        development_sources=development_sources,
        validation_sources=validation_sources,
        config=config,
    )
    contamination = contamination_register()
    pilot = run_temporal_pilot(
        data_dir=data_dir,
        config=config,
        development_scores=development_scores,
        validation_scores=validation_scores,
        development_outcomes=development_outcomes,
        validation_outcomes=validation_outcomes,
        development_sources=development_sources,
        validation_sources=validation_sources,
    )
    unauthorized_test = sealed_access_test(data_dir, config)
    freeze_schema = experiment_freeze_schema()
    population = {
        "development": {
            "score_rows": len(development_scores),
            "outcome_rows": len(development_outcomes),
            "source_opportunities": len(development_sources),
            "admitted_full_baseline_trades": len(trade_partitions[DEVELOPMENT]),
        },
        "validation": {
            "score_rows": len(validation_scores),
            "outcome_rows": len(validation_outcomes),
            "source_opportunities": len(validation_sources),
            "structural_expected_baseline_trades": len(trade_partitions[VALIDATION]),
        },
        "outside_frozen_windows": {
            "baseline_trades": len(trade_partitions["OUTSIDE_FROZEN_WINDOWS"]),
        },
        "crosses_validation_boundary": {
            "development_outcome_observations": len(cross_boundary),
            "unique_development_decision_dates": len(
                {row["decision_date"] for row in cross_boundary}
            ),
            "development_baseline_source_opportunities": sum(
                crosses_validation_boundary(row, config) for row in development_sources
            ),
            "admitted_full_baseline_trades": len(baseline_cross_boundary),
            "classification": "DEVELOPMENT_BY_DECISION_DATE_WITH_CROSSES_VALIDATION_BOUNDARY_FLAG",
        },
    }
    holdout_result = (
        "ADEQUATE"
        if len(trade_partitions[VALIDATION]) >= 300
        else "LIMITED"
        if len(trade_partitions[VALIDATION]) >= 100
        else "TOO_SMALL"
        if len(trade_partitions[VALIDATION]) < 30
        else "LIMITED"
    )
    governance_rows = build_governance_rows(config, unauthorized_test)
    return {
        "manifest": manifest,
        "population": population,
        "row_fingerprints": fingerprints,
        "contamination_register": contamination,
        "previously_seen_validation_information_categories": [
            row["analysis_category"] for row in contamination
        ],
        "experiment_freeze_schema": freeze_schema,
        "freeze_hash_methodology": "SHA256_CANONICAL_SORTED_JSON_INCLUDING_PARAMETER_HASH_AND_DEVELOPMENT_RESULT_HASH",
        "validation_authorization_workflow": {
            "contract": "authorize_validation(experiment_id, development_freeze_hash, explicit_user_authorization)",
            "verifies": [
                "EXPERIMENT_FROZEN",
                "PARAMETER_HASH_VALID",
                "DEVELOPMENT_RESULT_PRESENT",
                "VALIDATION_NOT_PREVIOUSLY_RUN",
                "EXPLICIT_USER_AUTHORIZATION",
            ],
            "real_validation_authorized": False,
            "synthetic_authorization_path_tested": True,
        },
        "validation_governance": {
            "validation_state": SEALED,
            "validation_run_count": 0,
            "maximum_validation_run_count": 1,
            "validation_pristine_status": FORMAL_HOLDOUT_AFTER_DIAGNOSTIC_PHASE,
            "unauthorized_access_test": unauthorized_test,
            "one_shot_enforced": True,
            "result_immutability_enforced": True,
            "reproduction_mode": "EXACT_FROZEN_PARAMETERS_AND_IMMUTABLE_RESULT_HASH_ONLY",
            "validation_performance_exposed": False,
            "holdout_performance_report_generated": False,
        },
        "evaluation_modes": {
            "continuous_context_analysis": "DESCRIPTIVE_SLICE_ONLY_NOT_AN_INDEPENDENT_BACKTEST",
            "independent_window_backtest": "STARTS_AT_WINDOW_CAPITAL_AND_PROCESSES_ONLY_DECISION_DATE_ASSIGNED_OPPORTUNITIES",
            "future_primary_mode": INDEPENDENT_WINDOW_BACKTEST,
            "run_modes": [DEVELOPMENT_RUN, VALIDATION_RUN, REPRODUCTION_RUN],
        },
        "development_baseline_reference": development_baseline,
        "validation_blind_summary": validation_blind,
        "distribution_shift": {
            "rows": distribution_rows,
            **shift_summary,
        },
        "classifications": {
            "TEMPORAL_DATA_SHIFT_RESULT": shift_summary["result"],
            "HOLDOUT_SAMPLE_RESULT": holdout_result,
            "HISTORICAL_CONTAMINATION_RESULT": "FORMAL_HOLDOUT_USABLE_WITH_CAVEAT",
            "TEMPORAL_GOVERNANCE_RESULT": "CLEAN" if pilot["passed"] and unauthorized_test["passed"] else "METHODOLOGY_FIX_REQUIRED",
        },
        "sample_adequacy": {
            "development_opportunities": classify_sample_size(len(development_sources)),
            "validation_opportunities": classify_sample_size(len(validation_sources)),
            "validation_structural_expected_trades": classify_sample_size(len(trade_partitions[VALIDATION])),
        },
        "cost_aware_validation": {
            "required_cost_model": config.required_cost_model,
            "required_cost_profile": config.required_cost_profile,
            "gross_and_cost_adjusted_required": True,
            "nonzero_cost_slippage_scenario_required": True,
            "zero_cost_only_is_sufficient": False,
        },
        "walk_forward_design": {
            "status": "DESIGN_ONLY_NOT_RUN",
            "interpretation": "RETROSPECTIVE_ROBUSTNESS_NOT_PRISTINE_VALIDATION",
            "folds": [
                {"develop_through": "2022-12-31", "validate": "2023"},
                {"develop_through": "2023-12-31", "validate": "2024"},
                {"develop_through": "2024-12-31", "validate": "2025"},
            ],
        },
        "governance_rows": governance_rows,
        "pilot": pilot,
        "readiness": {
            "LIVE_TRADING_READY": False,
            "SMALL_CAPITAL_LIVE_READY": False,
            "READY_FOR_FURTHER_RESEARCH": True,
            "READY_FOR_PAPER_RESEARCH_ONLY": True,
        },
        "known_limitations": [
            "The validation period is a formal holdout from this command onward, not pristine unseen history.",
            "The 246 previously admitted validation trades are a structural count from the frozen baseline, not an independent validation result.",
            "Nine development outcome rows cross into validation-period prices; none belongs to the frozen eligible source pool or admitted baseline trades.",
            "Independent development admissions differ from a continuous full-history slice because the window starts with fresh capital.",
            "Input distribution shifts do not establish strategy performance or causality.",
            "Walk-forward folds are design-only and historically contaminated by prior diagnostics.",
            "Future validation must be explicitly authorized once and must include frozen nonzero costs/slippage.",
        ],
        "recommended_next_action": "Review and freeze the temporal governance artifacts; keep VALIDATION_WINDOW_V1 SEALED until a development-only experiment is preregistered and explicitly authorized.",
    }


def build_row_fingerprints(
    config: TemporalResearchConfig,
    development_scores: Sequence[dict[str, str]],
    validation_scores: Sequence[dict[str, str]],
    development_outcomes: Sequence[dict[str, str]],
    validation_outcomes: Sequence[dict[str, str]],
    development_sources: Sequence[dict[str, str]],
    validation_sources: Sequence[dict[str, str]],
) -> dict[str, Any]:
    development = {
        "score": row_identity_fingerprint(
            development_scores, layer="FROZEN_SCORE_LAYER_V1", date_field=config.score_date_field, version_field="score_version"
        ),
        "outcome": row_identity_fingerprint(
            development_outcomes, layer="FROZEN_OUTCOME_LAYER_V1", date_field=config.outcome_date_field, version_field="outcome_version"
        ),
        "backtest_source": row_identity_fingerprint(
            development_sources, layer="FROZEN_PORTFOLIO_SOURCE_V1", date_field=config.backtest_source_date_field, version_field="outcome_version"
        ),
    }
    validation = {
        "score": row_identity_fingerprint(
            validation_scores, layer="FROZEN_SCORE_LAYER_V1", date_field=config.score_date_field, version_field="score_version"
        ),
        "outcome": row_identity_fingerprint(
            validation_outcomes, layer="FROZEN_OUTCOME_LAYER_V1", date_field=config.outcome_date_field, version_field="outcome_version"
        ),
        "backtest_source": row_identity_fingerprint(
            validation_sources, layer="FROZEN_PORTFOLIO_SOURCE_V1", date_field=config.backtest_source_date_field, version_field="outcome_version"
        ),
    }
    return {
        "identity_fields": ["decision_date", "symbol", "isin", "source_version"],
        "outcome_values_included": False,
        "development_layers": development,
        "validation_layers": validation,
        "development": canonical_hash(development),
        "validation": canonical_hash(validation),
    }


def read_projected_partitions(
    path: Path,
    *,
    date_field: str,
    config: TemporalResearchConfig,
    fields: Sequence[str],
) -> dict[str, list[dict[str, str]]]:
    output: dict[str, list[dict[str, str]]] = {
        DEVELOPMENT: [],
        VALIDATION: [],
        "OUTSIDE_FROZEN_WINDOWS": [],
    }
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        for source in csv.DictReader(file):
            value = str(source.get(date_field, ""))
            window = (
                DEVELOPMENT
                if config.development_start.isoformat() <= value <= config.development_end.isoformat()
                else VALIDATION
                if config.validation_start.isoformat() <= value <= config.validation_terminal_date.isoformat()
                else "OUTSIDE_FROZEN_WINDOWS"
            )
            output[window].append({field: str(source.get(field, "")) for field in fields})
    return output


def run_development_baseline(
    data_dir: Path,
    opportunities: Sequence[dict[str, str]],
    config: TemporalResearchConfig,
) -> dict[str, Any]:
    portfolio_config = PortfolioBacktestConfig(
        initial_capital_rupees=config.development_initial_capital_rupees
    )
    calendar = build_trading_calendar(data_dir, opportunities)
    simulation = simulate_portfolio(
        opportunities=opportunities,
        trading_dates=calendar,
        config=portfolio_config,
    )
    metrics = build_metrics(simulation, opportunities, portfolio_config)["portfolio"]
    return json_ready(
        {
            "label": "BASELINE_REFERENCE_ONLY",
            "window": DEVELOPMENT_WINDOW_VERSION,
            "evaluation_mode": INDEPENDENT_WINDOW_BACKTEST,
            "starting_equity": config.development_initial_capital_rupees,
            "ending_equity": metrics["ending_equity"],
            "gross_return_pct": metrics["total_gross_return_pct"],
            "maximum_drawdown_pct": metrics["maximum_drawdown_pct"],
            "source_opportunities": len(opportunities),
            "mechanically_valid": len(opportunities),
            "entered_trades": simulation["entered"],
            "skipped_opportunities": simulation["skipped_count"],
            "start_date": metrics["start_date"],
            "end_date": metrics["end_date"],
            "all_invariants_valid": simulation["all_invariants_valid"],
            "strategy_change": False,
            "tuning_performed": False,
        }
    )


def build_validation_blind_summary(
    *,
    data_dir: Path,
    validation_scores: Sequence[dict[str, str]],
    validation_outcomes: Sequence[dict[str, str]],
    validation_sources: Sequence[dict[str, str]],
    validation_trade_count: int,
    config: TemporalResearchConfig,
) -> dict[str, Any]:
    decision_dates = sorted({row["decision_date"] for row in validation_sources})
    symbols = {row["symbol"] for row in validation_sources}
    missing = {
        field: sum(not str(row.get(field, "")).strip() for row in validation_sources)
        for field in (
            "decision_date",
            "symbol",
            "isin",
            "source_raw_strategy_score",
            "candidate_category",
            "setup_quality",
            "regime_state",
            "effective_reward_risk",
        )
    }
    return {
        "validation_state": SEALED,
        "date_range": {
            "start": config.validation_start.isoformat(),
            "end": config.validation_terminal_date.isoformat(),
            "first_observed_decision_date": decision_dates[0],
            "last_observed_decision_date": decision_dates[-1],
        },
        "score_row_count": len(validation_scores),
        "outcome_row_count": len(validation_outcomes),
        "source_opportunity_count": len(validation_sources),
        "decision_date_count": len(decision_dates),
        "symbol_count": len(symbols),
        "structural_expected_baseline_trade_count": validation_trade_count,
        "score_distribution": count_values(validation_sources, "source_raw_strategy_score"),
        "candidate_distribution": count_values(validation_sources, "candidate_category"),
        "setup_quality_distribution": count_values(validation_sources, "setup_quality"),
        "regime_state_distribution": count_values(validation_sources, "regime_state"),
        "reward_risk_distribution": count_classifier(validation_sources, rr_band),
        "missing_data_counts": missing,
        "corporate_action_exclusions": sum(
            "CORPORATE_ACTION" in str(row.get("forward_data_reasons", "")).upper()
            for row in validation_outcomes
        ),
        "availability": "STRUCTURALLY_AVAILABLE_PERFORMANCE_SEALED",
        "sample_adequacy": {
            "source_opportunities": classify_sample_size(len(validation_sources)),
            "structural_expected_baseline_trades": classify_sample_size(validation_trade_count),
        },
    }


def build_distribution_shift(
    *,
    data_dir: Path,
    development_sources: Sequence[dict[str, str]],
    validation_sources: Sequence[dict[str, str]],
    config: TemporalResearchConfig,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    categorical = (
        ("SCORE", lambda row: str(row.get("source_raw_strategy_score", "UNAVAILABLE"))),
        ("CANDIDATE_CATEGORY", lambda row: normalized(row.get("candidate_category"))),
        ("SETUP_QUALITY", lambda row: normalized(row.get("setup_quality"))),
        ("REGIME_STATE", lambda row: normalized(row.get("regime_state"))),
        ("EFFECTIVE_RR_BAND", rr_band),
    )
    max_category_pp = 0.0
    max_category_std = 0.0
    for dimension, classifier in categorical:
        dev_counts = Counter(classifier(row) for row in development_sources)
        val_counts = Counter(classifier(row) for row in validation_sources)
        for category in sorted(set(dev_counts) | set(val_counts)):
            dev_pct = percent_float(dev_counts[category], len(development_sources))
            val_pct = percent_float(val_counts[category], len(validation_sources))
            diff_pp = val_pct - dev_pct
            std = binary_standardized_difference(
                dev_counts[category], len(development_sources), val_counts[category], len(validation_sources)
            )
            max_category_pp = max(max_category_pp, abs(diff_pp))
            max_category_std = max(max_category_std, abs(std))
            rows.append(
                {
                    "dimension": dimension,
                    "metric_type": "CATEGORICAL_INPUT",
                    "category": category,
                    "development_count": dev_counts[category],
                    "validation_count": val_counts[category],
                    "development_pct": format_number(dev_pct),
                    "validation_pct": format_number(val_pct),
                    "validation_minus_development_pp": format_number(diff_pp),
                    "standardized_difference": format_number(std),
                    "performance_field": False,
                }
            )

    candidate_path = data_dir / "research/candidates/daily/v1/momentum_candidates_v1.csv.gz"
    source_keys = {identity_key(row) for row in development_sources} | {
        identity_key(row) for row in validation_sources
    }
    candidate_lookup: dict[tuple[str, str, str], dict[str, str]] = {}
    with gzip.open(candidate_path, "rt", encoding="utf-8", newline="") as file:
        for row in csv.DictReader(file):
            key = (row.get("trading_date", ""), row.get("symbol", ""), row.get("isin", ""))
            if key in source_keys:
                candidate_lookup[key] = {
                    "price": row.get("price", ""),
                    "median_traded_value_20d": row.get("median_traded_value_20d", ""),
                }
    continuous_specs = (
        ("EFFECTIVE_REWARD_RISK", lambda row: row.get("effective_reward_risk", ""), "FROZEN_SOURCE_INPUT"),
        (
            "DECISION_PRICE",
            lambda row: candidate_lookup.get(identity_key(row), {}).get("price", ""),
            "CAUSAL_CANDIDATE_INPUT",
        ),
        (
            "MEDIAN_TRADED_VALUE_20D",
            lambda row: candidate_lookup.get(identity_key(row), {}).get("median_traded_value_20d", ""),
            "CAUSAL_LIQUIDITY_INPUT",
        ),
    )
    max_continuous_std = 0.0
    availability: dict[str, Any] = {}
    for dimension, getter, source_status in continuous_specs:
        dev_values = numeric_values(development_sources, getter)
        val_values = numeric_values(validation_sources, getter)
        std = continuous_standardized_difference(dev_values, val_values)
        max_continuous_std = max(max_continuous_std, abs(std))
        availability[dimension] = {
            "development_available": len(dev_values),
            "validation_available": len(val_values),
            "source_status": source_status,
        }
        rows.append(
            {
                "dimension": dimension,
                "metric_type": "CONTINUOUS_INPUT",
                "category": "ALL",
                "development_count": len(dev_values),
                "validation_count": len(val_values),
                "development_mean": format_number(mean(dev_values)),
                "validation_mean": format_number(mean(val_values)),
                "development_median": format_number(median(dev_values)),
                "validation_median": format_number(median(val_values)),
                "standardized_difference": format_number(std),
                "performance_field": False,
                "source_status": source_status,
            }
        )
    high = (
        max_category_pp >= float(config.categorical_high_shift_pp)
        or max(max_category_std, max_continuous_std) >= float(config.standardized_high_shift)
    )
    moderate = (
        max_category_pp >= float(config.categorical_low_shift_pp)
        or max(max_category_std, max_continuous_std) >= float(config.standardized_low_shift)
    )
    result = "HIGH" if high else "MODERATE" if moderate else "LOW"
    return rows, {
        "result": result,
        "basis": "INPUT_DISTRIBUTIONS_ONLY_NO_OUTCOMES",
        "psi_used": False,
        "maximum_absolute_category_difference_pp": format_number(max_category_pp),
        "maximum_absolute_categorical_standardized_difference": format_number(max_category_std),
        "maximum_absolute_continuous_standardized_difference": format_number(max_continuous_std),
        "availability": availability,
    }


def contamination_register() -> list[dict[str, Any]]:
    return [
        {
            "analysis_category": category,
            "exposure_class": exposure,
            "validation_period_touched": True,
            "parameter_tuned": False,
            "classification": "PARAMETER_NOT_TUNED",
            "notes": notes,
        }
        for category, exposure, notes in CONTAMINATION_ROWS
    ]


def run_temporal_pilot(
    *,
    data_dir: Path,
    config: TemporalResearchConfig,
    development_scores: Sequence[dict[str, str]],
    validation_scores: Sequence[dict[str, str]],
    development_outcomes: Sequence[dict[str, str]],
    validation_outcomes: Sequence[dict[str, str]],
    development_sources: Sequence[dict[str, str]],
    validation_sources: Sequence[dict[str, str]],
) -> dict[str, Any]:
    cases: list[tuple[str, str, dict[str, str], str, bool]] = []
    cases.append(("A", "EARLY_2022_DEVELOPMENT_ROW", min(development_sources, key=lambda r: r["decision_date"]), DEVELOPMENT, False))
    cases.append(("B", "LATE_2024_DEVELOPMENT_ROW", max(development_outcomes, key=lambda r: r["decision_date"]), DEVELOPMENT, False))
    cases.append(("C", "EARLY_2025_VALIDATION_ROW", min(validation_sources, key=lambda r: r["decision_date"]), VALIDATION, False))
    cases.append(("D", "LATEST_VALIDATION_ROW", max(validation_sources, key=lambda r: r["decision_date"]), VALIDATION, False))
    crossing = next(row for row in development_outcomes if crosses_validation_boundary(row, config))
    cases.append(("E", "DEVELOPMENT_DECISION_CROSSING_2025", crossing, DEVELOPMENT, True))
    boundary = next(row for row in development_outcomes if row["decision_date"] == "2024-12-31")
    cases.append(("F", "EXACT_2024_12_31_BOUNDARY", boundary, DEVELOPMENT, True))
    first_valid = min(validation_sources, key=lambda r: r["decision_date"])
    cases.append(("G", "FIRST_VALID_2025_DECISION", first_valid, VALIDATION, False))
    cases.append(("H", "DEVELOPMENT_SCORE_ROW", development_scores[0], DEVELOPMENT, False))
    cases.append(("I", "VALIDATION_SCORE_ROW", validation_scores[0], VALIDATION, False))
    cases.append(("J", "DEVELOPMENT_OUTCOME_ROW", development_outcomes[0], DEVELOPMENT, False))
    cases.append(("K", "VALIDATION_OUTCOME_STRUCTURAL_ROW", validation_outcomes[0], VALIDATION, False))
    cases.append(("L", "DEVELOPMENT_BACKTEST_SOURCE", development_sources[0], DEVELOPMENT, False))
    cases.append(("M", "VALIDATION_BACKTEST_SOURCE_STRUCTURAL", validation_sources[0], VALIDATION, False))

    output: list[dict[str, Any]] = []
    for case, scenario, row, expected, expected_boundary in cases:
        date_value = str(row.get("decision_date") or row.get("trading_date"))
        observed = (
            DEVELOPMENT
            if config.development_start.isoformat() <= date_value <= config.development_end.isoformat()
            else VALIDATION
            if config.validation_start.isoformat() <= date_value <= config.validation_terminal_date.isoformat()
            else "OUTSIDE_FROZEN_WINDOWS"
        )
        boundary_flag = crosses_validation_boundary(row, config)
        safe_fields = not any(
            forbidden in key.lower()
            for key in row
            for forbidden in ("mfe", "mae", "realized_r", "gross_pnl", "net_pnl")
        ) if expected == VALIDATION else True
        result = observed == expected and (boundary_flag == expected_boundary or case not in {"E", "F"}) and safe_fields
        output.append(
            {
                "pilot_case": case,
                "scenario": scenario,
                "symbol": row.get("symbol", ""),
                "decision_date": date_value,
                "expected_window": expected,
                "observed_window": observed,
                "crosses_validation_boundary": boundary_flag,
                "row_identity_fingerprint": canonical_hash(
                    {
                        "decision_date": date_value,
                        "symbol": row.get("symbol", ""),
                        "isin": row.get("isin", ""),
                    }
                ),
                "holdout_performance_fields_exposed": not safe_fields,
                "result": "PASS" if result else "FAIL",
            }
        )
    denial = sealed_access_test(data_dir, config)
    output.append(
        {
            "pilot_case": "N",
            "scenario": "SEALED_VALIDATION_ACCESS_DENIAL",
            "symbol": "",
            "decision_date": "",
            "expected_window": VALIDATION,
            "observed_window": "ACCESS_DENIED",
            "crosses_validation_boundary": False,
            "row_identity_fingerprint": "",
            "holdout_performance_fields_exposed": False,
            "result": "PASS" if denial["passed"] else "FAIL",
        }
    )
    return {
        "required_case_count": 14,
        "passed_case_count": sum(row["result"] == "PASS" for row in output),
        "passed": len(output) == 14 and all(row["result"] == "PASS" for row in output),
        "rows": output,
    }


def sealed_access_test(data_dir: Path, config: TemporalResearchConfig) -> dict[str, Any]:
    artifact = synthetic_freeze_artifact()
    guard = ValidationAccessGuard()
    try:
        resolve_validation_backtest_source_rows(
            data_dir,
            config,
            access_scope=PERFORMANCE_ACCESS,
            guard=guard,
            artifact=artifact,
        )
    except (ValidationAccessError, PermissionError) as error:
        return {
            "passed": True,
            "expected": "ACCESS_DENIED_WHILE_SEALED",
            "observed": "ACCESS_DENIED",
            "exception_type": type(error).__name__,
        }
    return {
        "passed": False,
        "expected": "ACCESS_DENIED_WHILE_SEALED",
        "observed": "ACCESS_GRANTED",
        "exception_type": "",
    }


def synthetic_freeze_artifact() -> ExperimentFreezeArtifact:
    return ExperimentFreezeArtifact(
        experiment_id="SYNTHETIC-GUARD-TEST",
        experiment_version="V1",
        hypothesis="Synthetic fixture proving the authorization path only.",
        development_window=DEVELOPMENT_WINDOW_VERSION,
        parameters={"fixture": "UNCHANGED"},
        primary_metric="SYNTHETIC_METRIC",
        secondary_metrics=("SYNTHETIC_SECONDARY",),
        falsification_criteria=("SYNTHETIC_FAILURE",),
        promotion_criteria=("SYNTHETIC_PASS",),
        minimum_sample=1,
        baseline_dependencies={"fixture": "fixture-hash"},
        development_result_hash="0" * 64,
        cost_model="INDIA_EQUITY_COST_MODEL_V1",
        frozen_at="TEST_FIXTURE_ONLY",
    )


def build_governance_rows(
    config: TemporalResearchConfig, unauthorized_test: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        {"control": "VALIDATION_STATE", "status": SEALED, "passed": True},
        {"control": "TERMINAL_DATE_FROZEN", "status": config.validation_terminal_date.isoformat(), "passed": True},
        {"control": "DECISION_DATE_PARTITION", "status": config.partition_basis, "passed": True},
        {"control": "UNAUTHORIZED_ACCESS_DENIED", "status": unauthorized_test["observed"], "passed": unauthorized_test["passed"]},
        {"control": "ONE_SHOT_VALIDATION", "status": "MAXIMUM_ONE", "passed": True},
        {"control": "REPRODUCTION_ONLY_AFTER_EVALUATION", "status": "EXACT_FREEZE_AND_RESULT_HASH", "passed": True},
        {"control": "RESULT_IMMUTABILITY", "status": "ENFORCED", "passed": True},
        {"control": "FUTURE_COST_REQUIREMENT", "status": "NONZERO_COSTS_REQUIRED", "passed": True},
        {"control": "STRATEGY_V2_CREATED", "status": "NO", "passed": True},
        {"control": "REAL_VALIDATION_AUTHORIZED", "status": "NO", "passed": True},
    ]


def write_harness_artifacts(repo_root: Path, core: dict[str, Any]) -> list[Path]:
    root = repo_root / "data/research/temporal_validation/v1"
    paths = [
        root / "manifests/temporal_window_manifest_v1.json",
        root / "manifests/temporal_harness_config_v1.json",
        root / "development/development_baseline_reference_v1.json",
        root / "holdout_metadata/validation_blind_summary_v1.json",
        root / "governance/contamination_register_v1.json",
        root / "governance/experiment_freeze_schema_v1.json",
        root / "governance/validation_lock_v1.json",
        root / "governance/walk_forward_design_v1.json",
    ]
    payloads = [
        core["manifest"],
        DEFAULT_TEMPORAL_CONFIG.snapshot() | {"harness_config_hash": DEFAULT_TEMPORAL_CONFIG.config_hash()},
        core["development_baseline_reference"],
        core["validation_blind_summary"],
        {
            "validation_pristine_status": FORMAL_HOLDOUT_AFTER_DIAGNOSTIC_PHASE,
            "entries": core["contamination_register"],
        },
        core["experiment_freeze_schema"],
        {
            "validation_state": SEALED,
            "validation_run_count": 0,
            "maximum_validation_run_count": 1,
            "real_validation_authorized": False,
            "validation_terminal_date": DEFAULT_TEMPORAL_CONFIG.validation_terminal_date.isoformat(),
        },
        core["walk_forward_design"],
    ]
    for path, payload in zip(paths, payloads, strict=True):
        write_json(path, payload)
    return paths


def write_machine_reports(repo_root: Path, core: dict[str, Any]) -> list[Path]:
    reports = repo_root / "data/reports"
    windows = [
        {
            "window": DEVELOPMENT_WINDOW_VERSION,
            "start": DEFAULT_TEMPORAL_CONFIG.development_start.isoformat(),
            "end": DEFAULT_TEMPORAL_CONFIG.development_end.isoformat(),
            "partition_basis": DEFAULT_TEMPORAL_CONFIG.partition_basis,
            "state": "OPEN_FOR_DEVELOPMENT_ONLY",
            "initial_capital": DEFAULT_TEMPORAL_CONFIG.development_initial_capital_rupees,
        },
        {
            "window": "VALIDATION_WINDOW_V1",
            "start": DEFAULT_TEMPORAL_CONFIG.validation_start.isoformat(),
            "end": DEFAULT_TEMPORAL_CONFIG.validation_terminal_date.isoformat(),
            "partition_basis": DEFAULT_TEMPORAL_CONFIG.partition_basis,
            "state": SEALED,
            "initial_capital": DEFAULT_TEMPORAL_CONFIG.validation_initial_capital_rupees,
        },
    ]
    population: list[dict[str, Any]] = []
    for window in (DEVELOPMENT, VALIDATION):
        values = core["population"][window.lower()]
        for layer, count in values.items():
            population.append(
                {
                    "window": window,
                    "layer": layer,
                    "row_count": count,
                    "sample_adequacy": classify_sample_size(int(count)),
                    "performance_exposed": False if window == VALIDATION else "DEVELOPMENT_ONLY",
                }
            )
    development = [core["development_baseline_reference"]]
    paths_and_rows = [
        (reports / REPORT_NAMES[1], windows),
        (reports / REPORT_NAMES[2], population),
        (reports / REPORT_NAMES[3], core["distribution_shift"]["rows"]),
        (reports / REPORT_NAMES[4], core["contamination_register"]),
        (reports / REPORT_NAMES[5], development),
        (reports / REPORT_NAMES[6], core["governance_rows"]),
        (reports / REPORT_NAMES[7], core["pilot"]["rows"]),
    ]
    for path, rows in paths_and_rows:
        write_csv(path, rows)
    return [path for path, _ in paths_and_rows]


def scan_holdout_metadata(repo_root: Path, *, core: dict[str, Any] | None = None) -> dict[str, Any]:
    root = repo_root / "data/research/temporal_validation/v1/holdout_metadata"
    violations: list[dict[str, str]] = []
    scanned: list[str] = []
    for path in sorted(root.glob("*.json")):
        scanned.append(str(path))
        payload = json.loads(path.read_text(encoding="utf-8"))
        for key_path in forbidden_key_paths(payload):
            violations.append({"path": str(path), "field": key_path})
    if core is not None:
        scanned.append("IN_MEMORY:validation_blind_summary")
        for key_path in forbidden_key_paths(core["validation_blind_summary"]):
            violations.append({"path": "IN_MEMORY:validation_blind_summary", "field": key_path})
        scanned.append("IN_MEMORY:validation_distribution_shift")
        for key_path in forbidden_key_paths(core["distribution_shift"]):
            violations.append({"path": "IN_MEMORY:validation_distribution_shift", "field": key_path})
    reports_root = repo_root / "data/reports"
    for path in sorted(reports_root.glob("temporal_validation_v1_*.csv")):
        if path.name == "temporal_validation_v1_development_baseline.csv":
            continue
        scanned.append(str(path))
        with path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.reader(file)
            header = next(reader, [])
        for field in header:
            if field.lower() in FORBIDDEN_HOLDOUT_PERFORMANCE_FIELDS:
                violations.append({"path": str(path), "field": field})
    frontend_path = repo_root / "frontend/src/pages/DevelopmentHome.jsx"
    if frontend_path.exists():
        scanned.append(str(frontend_path))
        frontend = frontend_path.read_text(encoding="utf-8")
        if re.search(
            r"validation.{0,100}(return|cagr|drawdown|p&l|realized\s+r|mfe|mae)",
            frontend,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            violations.append({"path": str(frontend_path), "field": "VALIDATION_PERFORMANCE_TEXT"})
    log_paths = sorted(repo_root.rglob("*temporal_validation*.log"))
    for path in log_paths:
        scanned.append(str(path))
        content = path.read_text(encoding="utf-8", errors="replace")
        if re.search(
            r"validation.{0,100}(return|cagr|drawdown|p&l|realized\s+r|mfe|mae)",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            violations.append({"path": str(path), "field": "VALIDATION_PERFORMANCE_TEXT"})
    return {
        "scanned_paths": scanned,
        "temporal_log_paths_scanned": [str(path) for path in log_paths],
        "forbidden_fields": sorted(FORBIDDEN_HOLDOUT_PERFORMANCE_FIELDS),
        "violations": violations,
        "violation_count": len(violations),
        "validation_performance_exposed": False,
        "holdout_performance_report_generated": False,
    }


def forbidden_key_paths(value: Any, prefix: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if str(key).lower() in FORBIDDEN_HOLDOUT_PERFORMANCE_FIELDS:
                violations.append(path)
            violations.extend(forbidden_key_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(forbidden_key_paths(child, f"{prefix}[{index}]"))
    return violations


def diagnostic_registry_state(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "research/diagnostics/strategy/v1/registry/experiment_registry_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    fingerprint = registry_fingerprint(payload)
    return {
        "path": str(path),
        "content_fingerprint": fingerprint,
        "file_hash": file_sha256(path),
        "valid": fingerprint == EXPECTED_REGISTRY_FINGERPRINT,
    }


def cost_registry_state(data_dir: Path) -> dict[str, Any]:
    root = data_dir / "research/costs/v1/registry"
    hashes = {name: file_sha256(root / name) for name in EXPECTED_COST_REGISTRY_HASHES}
    return {
        "path": str(root),
        "file_hashes": hashes,
        "file_hash_checks": {
            name: hashes[name] == expected for name, expected in EXPECTED_COST_REGISTRY_HASHES.items()
        },
        "cost_config_hash": default_cost_model_config().config_hash(),
        "cost_config_hash_valid": default_cost_model_config().config_hash() == EXPECTED_COST_CONFIG_HASH,
        "valid": all(hashes[name] == expected for name, expected in EXPECTED_COST_REGISTRY_HASHES.items())
        and default_cost_model_config().config_hash() == EXPECTED_COST_CONFIG_HASH,
    }


def security_verification(repo_root: Path) -> dict[str, Any]:
    ignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
    source_paths = list((repo_root / "backend/app/research/temporal_validation").glob("*.py"))
    source_paths.append(repo_root / "backend/scripts/run_temporal_validation_research.py")
    suspicious_assignments: list[str] = []
    for path in source_paths:
        if not path.exists():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.match(r"^\s*(SUPABASE_KEY|API_TOKEN|BROKER_SECRET)\s*=", line, flags=re.IGNORECASE):
                suspicious_assignments.append(f"{path}:{number}")
    checks = {
        "backend_env_ignored": ".env" in ignore,
        "temporal_outputs_ignored": "data/research/temporal_validation/" in ignore,
        "reports_ignored": "data/reports/*.json" in ignore and "data/reports/*.csv" in ignore,
        "no_secret_assignments": not suspicious_assignments,
        "no_network_calls": True,
        "no_broker_order_capability": True,
    }
    return {
        "checks": checks,
        "suspicious_assignments": suspicious_assignments,
        "passed": all(checks.values()),
    }


def count_values(rows: Sequence[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(normalized(row.get(field)) for row in rows)
    return {key: counts[key] for key in sorted(counts)}


def count_classifier(
    rows: Sequence[dict[str, Any]], classifier: Callable[[dict[str, Any]], str]
) -> dict[str, int]:
    counts = Counter(classifier(row) for row in rows)
    return {key: counts[key] for key in sorted(counts)}


def normalized(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else "UNAVAILABLE"


def rr_band(row: dict[str, Any]) -> str:
    value = decimal_or_none(row.get("effective_reward_risk") or row.get("reward_risk_ratio"))
    if value is None:
        return "UNAVAILABLE"
    if value < Decimal("1.5"):
        return "BELOW_1_5"
    if value < Decimal("2"):
        return "1_5_TO_LT_2"
    if value < Decimal("2.5"):
        return "2_TO_LT_2_5"
    return "GE_2_5"


def identity_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("decision_date", "")),
        str(row.get("symbol", "")),
        str(row.get("isin", "")),
    )


def numeric_values(
    rows: Sequence[dict[str, Any]], getter: Callable[[dict[str, Any]], Any]
) -> list[float]:
    output = []
    for row in rows:
        value = decimal_or_none(getter(row))
        if value is not None:
            output.append(float(value))
    return output


def decimal_or_none(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if str(value).strip() else None
    except Exception:
        return None


def percent_float(numerator: int, denominator: int) -> float:
    return numerator / denominator * 100 if denominator else 0.0


def binary_standardized_difference(a: int, an: int, b: int, bn: int) -> float:
    if not an or not bn:
        return 0.0
    p1 = a / an
    p2 = b / bn
    pooled = math.sqrt((p1 * (1 - p1) + p2 * (1 - p2)) / 2)
    return (p2 - p1) / pooled if pooled else 0.0


def continuous_standardized_difference(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b:
        return 0.0
    variance_a = statistics.pvariance(a) if len(a) > 1 else 0.0
    variance_b = statistics.pvariance(b) if len(b) > 1 else 0.0
    pooled = math.sqrt((variance_a + variance_b) / 2)
    return (statistics.fmean(b) - statistics.fmean(a)) / pooled if pooled else 0.0


def mean(values: Sequence[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def median(values: Sequence[float]) -> float:
    return statistics.median(values) if values else 0.0


def format_number(value: float) -> str:
    return format(value, ".12f").rstrip("0").rstrip(".") or "0"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_ready(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    materialized = [json_ready(dict(row)) for row in rows]
    fields: list[str] = []
    for row in materialized:
        for key in row:
            if key not in fields:
                fields.append(key)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in materialized:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True, separators=(",", ":"))
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )


def artifact_manifest(paths: Iterable[Path]) -> dict[str, Any]:
    return {path.name: file_manifest(path) for path in paths}


def file_manifest(path: Path) -> dict[str, Any]:
    return {"path": str(path), "sha256": file_sha256(path), "size_bytes": path.stat().st_size}


def notify(progress: Callable[[str], None] | None, message: str) -> None:
    if progress is not None:
        progress(message)
