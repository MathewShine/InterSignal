from __future__ import annotations

import csv
import gzip
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from app.risk.risk_baseline import UPSTREAM_HASHES
from app.risk.risk_config import (
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_DATASET_HASH,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
    resolve_current_risk_structure_dataset,
    resolve_risk_structure_dataset,
)
from app.strategy.momentum_candidates import file_sha256
from app.strategy.outcomes.outcome_config import (
    STRATEGY_OUTCOME_VERSION,
    SWING_DAILY_OUTCOME_PROFILE,
    StrategyOutcomeConfig,
)
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_CONFIG_HASH,
    CURRENT_STRATEGY_SCORE_PROFILE,
    CURRENT_STRATEGY_SCORE_VERSION,
    STRATEGY_SCORE_V1_DATASET_HASH,
    baseline_hash_checks,
    baseline_input_hashes,
    resolve_current_strategy_score_dataset,
)

CURRENT_STRATEGY_OUTCOME_VERSION = STRATEGY_OUTCOME_VERSION
CURRENT_STRATEGY_OUTCOME_PROFILE = SWING_DAILY_OUTCOME_PROFILE
CURRENT_STRATEGY_OUTCOME_CONFIG_HASH = "2ea683a8f8b5b041"
STRATEGY_OUTCOME_V1_DATASET_HASH = "5c4ec28cb54f6567b04c3444a3f1d0dde5f03ac3c6518743268f9e4fda100538"
STRATEGY_OUTCOME_BASELINE_STATUS = "ACTIVE_HISTORICAL_OUTCOME_BASELINE"
STRATEGY_OUTCOME_AUDIT_VERSION = "STRATEGY_OUTCOME_AUDIT_V1"
APPROVED_FORWARD_SAFETY_RESULT = "CONSERVATIVE_BUT_REASONABLE"
APPROVED_ENTRY_REVALIDATION_RESULT = "CLEAN_AND_USEFUL"
APPROVED_OUTCOME_LABEL_RESULT = "CLEAN"
APPROVED_FOUR_SESSION_HORIZON_RESULT = "LIKELY_TOO_SHORT"
APPROVED_DESCRIPTIVE_PATTERN = "WEAK"
APPROVED_OVERALL_AUDIT_RESULT = "STABLE_WITH_REVIEW_NOTES"
APPROVED_BASELINE_DECISION = "A_FREEZE_UNCHANGED"

_DATASET_PATHS = {
    (SWING_DAILY_OUTCOME_PROFILE, STRATEGY_OUTCOME_VERSION): Path(
        "research/outcomes/swing/daily/v1/strategy_outcomes_v1.csv.gz"
    ),
}
_CURRENT_VERSION_BY_PROFILE = {SWING_DAILY_OUTCOME_PROFILE: STRATEGY_OUTCOME_VERSION}

REFERENCE_CLASSIFICATIONS = (
    "FORWARD_CURRENT",
    "AUDIT_ALLOWED",
    "TEST_FIXTURE_ALLOWED",
    "DOCUMENTATION_ALLOWED",
    "HISTORICAL_ALLOWED",
    "FORWARD_REFERENCE_MUST_CHANGE",
)
REFERENCE_PATTERNS = (
    re.compile(r"\bSTRATEGY_OUTCOME_V1\b"),
    re.compile(r"\bSWING_DAILY_OUTCOME_V1\b"),
    re.compile(r"strategy_outcomes_v1\.csv\.gz"),
    re.compile(r"outcomes[/\\]swing[/\\]daily[/\\]v1"),
)
SOURCE_SUFFIXES = {".py", ".md", ".js", ".jsx", ".json"}
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "dist",
    "data",
    "tmp",
}

EXPECTED_COUNTS = {
    "total_rows": 14251,
    "primary_source_count": 4268,
    "valid_entry_count": 3296,
    "invalid_entry_count": 972,
    "unsafe_count": 700,
    "rr_invalid_count": 260,
    "open_below_stop_count": 12,
    "quantity_zero_count": 0,
    "target_first_count": 115,
    "stop_first_count": 724,
    "ambiguous_count": 1,
    "neither_count": 2456,
}

CANONICAL_OUTCOME_STATES = {
    "TARGET_FIRST",
    "STOP_FIRST",
    "NEITHER_WITHIN_HORIZON",
    "AMBIGUOUS",
    "INVALID_ENTRY",
    "INSUFFICIENT_FORWARD_DATA",
}


@dataclass(frozen=True, slots=True)
class CurrentOutcomeBaseline:
    version: str
    profile: str
    config_hash: str
    dataset_path: Path
    status: str = STRATEGY_OUTCOME_BASELINE_STATUS


def get_current_strategy_outcome_version(profile: str = CURRENT_STRATEGY_OUTCOME_PROFILE) -> str:
    try:
        return _CURRENT_VERSION_BY_PROFILE[profile]
    except KeyError as exc:
        raise ValueError(f"No current outcome baseline registered for profile {profile!r}") from exc


def get_current_strategy_outcome_profile() -> str:
    return CURRENT_STRATEGY_OUTCOME_PROFILE


def get_current_strategy_outcome_config_hash(profile: str = CURRENT_STRATEGY_OUTCOME_PROFILE) -> str:
    if profile != CURRENT_STRATEGY_OUTCOME_PROFILE:
        raise ValueError(f"No current outcome config registered for profile {profile!r}")
    return CURRENT_STRATEGY_OUTCOME_CONFIG_HASH


def resolve_strategy_outcome_dataset(
    data_dir: Path,
    *,
    profile: str,
    version: str,
) -> Path:
    try:
        relative_path = _DATASET_PATHS[(profile, version)]
    except KeyError as exc:
        raise ValueError(f"Unsupported outcome baseline: profile={profile!r}, version={version!r}") from exc
    return Path(data_dir) / relative_path


def resolve_current_strategy_outcome_dataset(
    data_dir: Path,
    *,
    profile: str = CURRENT_STRATEGY_OUTCOME_PROFILE,
) -> Path:
    version = get_current_strategy_outcome_version(profile)
    return resolve_strategy_outcome_dataset(data_dir, profile=profile, version=version)


def get_current_strategy_outcome_baseline(
    data_dir: Path,
    *,
    profile: str = CURRENT_STRATEGY_OUTCOME_PROFILE,
) -> CurrentOutcomeBaseline:
    return CurrentOutcomeBaseline(
        version=get_current_strategy_outcome_version(profile),
        profile=profile,
        config_hash=get_current_strategy_outcome_config_hash(profile),
        dataset_path=resolve_current_strategy_outcome_dataset(data_dir, profile=profile),
    )


def verify_current_strategy_outcome_baseline(data_dir: Path) -> CurrentOutcomeBaseline:
    baseline = get_current_strategy_outcome_baseline(data_dir)
    if not baseline.dataset_path.exists():
        raise FileNotFoundError(f"Current strategy-outcome dataset not found: {baseline.dataset_path}")
    observed_hash = file_sha256(baseline.dataset_path)
    if observed_hash != STRATEGY_OUTCOME_V1_DATASET_HASH:
        raise ValueError(
            "Current strategy-outcome dataset hash mismatch: "
            f"expected {STRATEGY_OUTCOME_V1_DATASET_HASH}, observed {observed_hash}"
        )
    config = StrategyOutcomeConfig()
    if config.outcome_version != baseline.version:
        raise ValueError(f"Current strategy-outcome version mismatch: {config.outcome_version}")
    if config.outcome_profile != baseline.profile:
        raise ValueError(f"Current strategy-outcome profile mismatch: {config.outcome_profile}")
    if config.config_hash() != baseline.config_hash:
        raise ValueError(f"Current strategy-outcome config hash mismatch: {config.config_hash()}")
    return baseline


def validate_outcome_baseline_rows(dataset_path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    identities = {
        "outcome_versions": set(),
        "outcome_profiles": set(),
        "outcome_config_hashes": set(),
        "score_versions": set(),
        "score_profiles": set(),
        "score_config_hashes": set(),
        "risk_versions": set(),
        "risk_config_hashes": set(),
    }
    invariants: Counter[str] = Counter()

    with gzip.open(dataset_path, "rt", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            counts["total_rows"] += 1
            identities["outcome_versions"].add(row.get("outcome_version", ""))
            identities["outcome_profiles"].add(row.get("outcome_profile", ""))
            identities["outcome_config_hashes"].add(row.get("outcome_config_hash", ""))
            identities["score_versions"].add(row.get("score_version", ""))
            identities["score_profiles"].add(row.get("score_profile", ""))
            identities["score_config_hashes"].add(row.get("score_config_hash", ""))
            identities["risk_versions"].add(row.get("risk_version", ""))
            identities["risk_config_hashes"].add(row.get("risk_config_hash", ""))

            outcome = row.get("first_touch_outcome", "")
            same_bar = truthy(row.get("same_bar_ambiguous"))
            right_censored = truthy(row.get("right_censored"))
            forward_safe = truthy(row.get("forward_data_safe"))
            entry_valid = truthy(row.get("entry_valid"))
            primary = row.get("outcome_cohort") == "HISTORICAL_ELIGIBLE_OPPORTUNITY"

            invariants["entry_model_violations"] += row.get("entry_model") != "NEXT_SESSION_OPEN"
            invariants["canonical_outcome_state_violations"] += outcome not in CANONICAL_OUTCOME_STATES
            invariants["same_bar_ambiguity_violations"] += same_bar != (outcome == "AMBIGUOUS")
            invariants["right_censoring_separation_violations"] += right_censored and (
                outcome == "NEITHER_WITHIN_HORIZON" or not forward_safe
            )
            invariants["forward_safety_status_violations"] += (not forward_safe) != (
                row.get("forward_data_status") == "FORWARD_DATA_UNSAFE"
            )
            invariants["transaction_cost_status_violations"] += row.get("transaction_cost_status") != "NOT_MODELED"
            invariants["slippage_status_violations"] += row.get("slippage_status") != "NOT_MODELED"
            invariants["historical_execution_status_violations"] += row.get("historical_execution_status") != "NOT_EXECUTED"
            invariants["trade_signal_status_violations"] += row.get("trade_signal_status") != "SOURCE_FROZEN_RESEARCH_ONLY"
            invariants["frozen_stop_violations"] += row.get("stop_price") != row.get("original_stop_price")
            invariants["frozen_target_violations"] += row.get("target_price") != row.get("selected_target_price")
            invariants["horizon_range_violations"] += int(row.get("forward_sessions_available") or 0) not in range(0, 5)
            invariants["no_leverage_violations"] += row.get("no_leverage_status") != "NO_LEVERAGE"

            if not primary:
                continue
            counts["primary_source_count"] += 1
            counts["valid_entry_count" if entry_valid else "invalid_entry_count"] += 1
            counts["unsafe_count"] += not forward_safe
            status = row.get("entry_recheck_status")
            counts["rr_invalid_count"] += status in {"ENTRY_INVALID_GAP", "ENTRY_INVALID_RR"}
            counts["open_below_stop_count"] += status == "ENTRY_INVALID_STOP_RELATION"
            counts["quantity_zero_count"] += status == "ENTRY_INVALID_CAPITAL"
            if entry_valid:
                key = {
                    "TARGET_FIRST": "target_first_count",
                    "STOP_FIRST": "stop_first_count",
                    "AMBIGUOUS": "ambiguous_count",
                    "NEITHER_WITHIN_HORIZON": "neither_count",
                }.get(outcome)
                if key:
                    counts[key] += 1

    observed_counts = {name: counts[name] for name in EXPECTED_COUNTS}
    serialized_identities = {name: sorted(values) for name, values in identities.items()}
    identity_valid = serialized_identities == {
        "outcome_versions": [CURRENT_STRATEGY_OUTCOME_VERSION],
        "outcome_profiles": [CURRENT_STRATEGY_OUTCOME_PROFILE],
        "outcome_config_hashes": [CURRENT_STRATEGY_OUTCOME_CONFIG_HASH],
        "score_versions": [CURRENT_STRATEGY_SCORE_VERSION],
        "score_profiles": [CURRENT_STRATEGY_SCORE_PROFILE],
        "score_config_hashes": [CURRENT_STRATEGY_SCORE_CONFIG_HASH],
        "risk_versions": [CURRENT_RISK_STRUCTURE_VERSION],
        "risk_config_hashes": [CURRENT_RISK_STRUCTURE_CONFIG_HASH],
    }
    invariant_counts = dict(invariants)
    return {
        "counts": observed_counts,
        "expected_counts": dict(EXPECTED_COUNTS),
        "counts_match": observed_counts == EXPECTED_COUNTS,
        "identity": serialized_identities,
        "identity_valid": identity_valid,
        "invariants": invariant_counts,
        "all_valid": observed_counts == EXPECTED_COUNTS
        and identity_valid
        and not any(invariant_counts.values()),
    }


def outcome_input_hashes(data_dir: Path) -> dict[str, str]:
    return {
        **baseline_input_hashes(data_dir),
        "outcome_v1": file_sha256(resolve_current_strategy_outcome_dataset(data_dir)),
    }


def outcome_input_hash_checks(hashes: dict[str, str]) -> dict[str, bool]:
    expected = {
        **UPSTREAM_HASHES,
        "risk_v1": RISK_STRUCTURE_V1_DATASET_HASH,
        "risk_v1_1": RISK_STRUCTURE_V1_1_DATASET_HASH,
        "score_v1": STRATEGY_SCORE_V1_DATASET_HASH,
        "outcome_v1": STRATEGY_OUTCOME_V1_DATASET_HASH,
    }
    score_checks = baseline_hash_checks(hashes)
    return {
        **score_checks,
        "outcome_v1": hashes.get("outcome_v1") == expected["outcome_v1"],
    }


def audit_outcome_references(repo_root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for path in source_files(repo_root):
        relative_path = path.relative_to(repo_root).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            matched = [pattern.pattern for pattern in REFERENCE_PATTERNS if pattern.search(line)]
            if matched:
                findings.append(
                    {
                        "path": relative_path,
                        "line": line_number,
                        "classification": classify_outcome_reference(relative_path),
                        "patterns": matched,
                        "text": line.strip()[:240],
                    }
                )
    counts = Counter(item["classification"] for item in findings)
    return {
        "scope": "Outcome V1 version, swing profile, canonical filename, and canonical path references.",
        "total_references": len(findings),
        "classification_counts": {name: counts[name] for name in REFERENCE_CLASSIFICATIONS},
        "unintended_forward_references": [
            item for item in findings if item["classification"] == "FORWARD_REFERENCE_MUST_CHANGE"
        ],
        "references": findings,
    }


def source_files(repo_root: Path) -> Iterable[Path]:
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.relative_to(repo_root).parts):
            continue
        yield path


def classify_outcome_reference(relative_path: str) -> str:
    path = relative_path.lower()
    if path.startswith("backend/tests/"):
        return "TEST_FIXTURE_ALLOWED"
    if "audit" in path:
        return "AUDIT_ALLOWED"
    if path.startswith("docs/"):
        return "DOCUMENTATION_ALLOWED"
    if path in {
        "backend/app/strategy/outcomes/__init__.py",
        "backend/app/strategy/outcomes/outcome_baseline.py",
        "backend/app/strategy/outcomes/outcome_config.py",
        "backend/app/strategy/outcomes/outcome_engine.py",
        "backend/scripts/build_strategy_outcomes.py",
        "backend/scripts/promote_strategy_outcome_baseline.py",
        "frontend/src/pages/developmenthome.jsx",
    }:
        return "FORWARD_CURRENT"
    return "FORWARD_REFERENCE_MUST_CHANGE"


def verify_future_data_separation(repo_root: Path) -> dict[str, Any]:
    consumers = {
        "features": [repo_root / "backend/app/features", repo_root / "backend/app/services/daily_feature_engine.py"],
        "candidates": [repo_root / "backend/app/strategy/momentum_candidates.py"],
        "setup": [repo_root / "backend/app/strategy/daily_setup_evaluator.py"],
        "regime": [repo_root / "backend/app/regime"],
        "entry": [repo_root / "backend/app/strategy/entry_evaluator.py"],
        "risk": [repo_root / "backend/app/risk"],
        "score": [repo_root / "backend/app/strategy/scoring"],
    }
    patterns = ("app.strategy.outcomes", "strategy.outcomes", "strategy_outcomes_v1.csv.gz")
    results: dict[str, bool] = {}
    violations: list[dict[str, Any]] = []
    for component, roots in consumers.items():
        component_violations = []
        for root in roots:
            paths = root.rglob("*.py") if root.is_dir() else [root]
            for path in paths:
                text = path.read_text(encoding="utf-8", errors="replace")
                matched = [pattern for pattern in patterns if pattern in text]
                if matched:
                    component_violations.append(
                        {"component": component, "path": path.relative_to(repo_root).as_posix(), "patterns": matched}
                    )
        results[f"{component}_does_not_consume_outcomes"] = not component_violations
        violations.extend(component_violations)
    return {"checks": results, "violations": violations, "verified": all(results.values())}


def build_outcome_baseline_promotion_report(
    *,
    repo_root: Path,
    tests_passed: bool,
    frontend_build_passed: bool,
) -> dict[str, Any]:
    data_dir = repo_root / "data"
    baseline = verify_current_strategy_outcome_baseline(data_dir)
    dataset_hash_before = file_sha256(baseline.dataset_path)
    row_validation = validate_outcome_baseline_rows(baseline.dataset_path)
    audit = json.loads((data_dir / "reports/strategy_outcome_v1_audit_summary.json").read_text(encoding="utf-8"))
    classifications = audit.get("classifications", {})
    audit_approved = (
        audit.get("audit_version") == STRATEGY_OUTCOME_AUDIT_VERSION
        and classifications.get("forward_safety_result") == APPROVED_FORWARD_SAFETY_RESULT
        and classifications.get("entry_revalidation_result") == APPROVED_ENTRY_REVALIDATION_RESULT
        and classifications.get("outcome_label_result") == APPROVED_OUTCOME_LABEL_RESULT
        and classifications.get("four_session_horizon_result") == APPROVED_FOUR_SESSION_HORIZON_RESULT
        and classifications.get("descriptive_pattern") == APPROVED_DESCRIPTIVE_PATTERN
        and classifications.get("overall_audit_result") == APPROVED_OVERALL_AUDIT_RESULT
        and classifications.get("baseline_decision") == APPROVED_BASELINE_DECISION
        and audit.get("ready_for_review") is True
    )
    hashes_before = outcome_input_hashes(data_dir)
    hash_checks = outcome_input_hash_checks(hashes_before)
    reference_audit = audit_outcome_references(repo_root)
    future_data_separation = verify_future_data_separation(repo_root)
    config = StrategyOutcomeConfig()
    methodology = {
        "decision_time": "EOD_T",
        "entry_model": config.entry_model,
        "next_open_revalidation": True,
        "forward_safety_revalidation": True,
        "open_above_frozen_stop_required": True,
        "minimum_effective_reward_risk": str(config.minimum_effective_reward_risk),
        "quantity_at_least_one_required": True,
        "capital_and_risk_valid_required": True,
        "no_leverage": True,
        "technical_stop_source": CURRENT_RISK_STRUCTURE_VERSION,
        "target_source": CURRENT_RISK_STRUCTURE_VERSION,
        "max_canonical_horizon_sessions": config.max_hold_sessions,
        "same_bar_ambiguity_policy": config.same_bar_ambiguity_policy,
        "transaction_cost_status": config.transaction_cost_status,
        "slippage_status": config.slippage_status,
    }
    methodology_locked = (
        config.entry_model == "NEXT_SESSION_OPEN"
        and config.max_hold_sessions == 4
        and str(config.minimum_effective_reward_risk) == "1.50"
        and str(config.research_capital_rupees) == "100000"
        and str(config.max_risk_per_trade_pct) == "1.00"
        and config.same_bar_ambiguity_policy == "AMBIGUOUS_EXCLUDE_FROM_DETERMINISTIC_CLASSIFICATION"
        and config.transaction_cost_status == "NOT_MODELED"
        and config.slippage_status == "NOT_MODELED"
    )
    reconstruction = audit.get("reconstruction", {})
    terminology = audit.get("terminology_and_safety", {})
    lightweight_invariants = {
        "ambiguity_mismatches": reconstruction.get("ambiguity_mismatches"),
        "first_touch_mismatches": reconstruction.get("first_touch_mismatches"),
        "mfe_r_mismatches": reconstruction.get("mfe_r_mismatches"),
        "mae_r_mismatches": reconstruction.get("mae_r_mismatches"),
        "close_return_mismatches": reconstruction.get("close_return_mismatches"),
        "cohort_separation_violations": terminology.get("cohort_separation_violations"),
        "canonical_profitability_language_violations": terminology.get("canonical_profitability_language_violations"),
        "execution_engine_components_introduced": terminology.get("execution_engine_components_introduced"),
        "signals_generated": terminology.get("signals_generated"),
        "orders_placed": terminology.get("orders_placed"),
    }
    lightweight_invariants_clean = all(value == 0 for value in lightweight_invariants.values())
    dataset_hash_after = file_sha256(baseline.dataset_path)
    hashes_after = outcome_input_hashes(data_dir)
    safety = {
        "outcome_dataset_regenerated": 0,
        "portfolio_backtests_run": 0,
        "signals_generated": 0,
        "orders_placed": 0,
        "remote_migrations_applied": 0,
        "supabase_records_persisted": 0,
    }
    checks = (
        dataset_hash_before == STRATEGY_OUTCOME_V1_DATASET_HASH,
        dataset_hash_after == dataset_hash_before,
        hashes_before == hashes_after,
        all(hash_checks.values()),
        row_validation["all_valid"],
        audit_approved,
        methodology_locked,
        lightweight_invariants_clean,
        future_data_separation["verified"],
        not reference_audit["unintended_forward_references"],
        tests_passed,
        frontend_build_passed,
    )
    promotion_status = STRATEGY_OUTCOME_BASELINE_STATUS if all(checks) else "VERIFICATION_INCOMPLETE"
    counts = row_validation["counts"]
    return {
        "phase": "Step 02.11",
        "command": "Command 03",
        "outcome_version": baseline.version,
        "outcome_profile": baseline.profile,
        "outcome_config_hash": baseline.config_hash,
        "outcome_dataset_hash": dataset_hash_after,
        "promotion_status": promotion_status,
        "score_version": CURRENT_STRATEGY_SCORE_VERSION,
        "score_profile": CURRENT_STRATEGY_SCORE_PROFILE,
        "score_config_hash": CURRENT_STRATEGY_SCORE_CONFIG_HASH,
        "score_dataset_hash": hashes_after["score_v1"],
        "risk_version": CURRENT_RISK_STRUCTURE_VERSION,
        "risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
        "risk_dataset_hash": hashes_after["risk_v1_1"],
        "audit_version": audit.get("audit_version"),
        "forward_safety_result": classifications.get("forward_safety_result"),
        "entry_revalidation_result": classifications.get("entry_revalidation_result"),
        "outcome_label_result": classifications.get("outcome_label_result"),
        "four_session_horizon_result": classifications.get("four_session_horizon_result"),
        "descriptive_pattern": classifications.get("descriptive_pattern"),
        "overall_audit_result": classifications.get("overall_audit_result"),
        "baseline_decision": classifications.get("baseline_decision"),
        **counts,
        "future_data_boundary_verified": future_data_separation["verified"],
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "forward_contract": {
            "version": baseline.version,
            "profile": baseline.profile,
            "config_hash": baseline.config_hash,
            "dataset_path": str(baseline.dataset_path),
        },
        "methodology": methodology,
        "methodology_locked": methodology_locked,
        "row_validation": row_validation,
        "audit_linkage": {
            "document": "docs/strategy-v1-historical-outcomes-audit.md",
            "audit_approved": audit_approved,
            "independent_completeness_verification": "105/105",
        },
        "lightweight_invariants": lightweight_invariants,
        "lightweight_invariants_clean": lightweight_invariants_clean,
        "forward_safety_handoff": {
            "entry_session_unsafe_count": audit.get("forward_safety", {}).get("entry_session_unsafe_count"),
            "later_window_only_unsafe_count": audit.get("forward_safety", {}).get("later_window_only_unsafe_count"),
        },
        "portfolio_backtest_handoff": {
            "consecutive_same_symbol_opportunities": audit.get("overlap", {}).get("consecutive_same_symbol_opportunities"),
            "maximum_same_symbol_streak": audit.get("overlap", {}).get("maximum_streak"),
            "same_symbol_overlap_rate_pct": audit.get("overlap", {}).get("same_symbol_overlap_rate_pct"),
            "concurrent_opportunities": audit.get("overlap", {}).get("active_opportunity_distribution"),
            "days_demanded_notional_above_100000": audit.get("capital_demand", {}).get("days_demanded_notional_above_100000"),
            "requirements": [
                "concurrency",
                "available capital",
                "duplicate and same-symbol overlap",
                "portfolio risk",
                "deterministic opportunity selection",
            ],
        },
        "input_hashes_before": hashes_before,
        "input_hashes_after": hashes_after,
        "input_hash_checks": hash_checks,
        "outcome_dataset_unchanged_during_promotion": dataset_hash_after == dataset_hash_before,
        "future_data_separation": future_data_separation,
        "reference_audit": reference_audit,
        "safety": safety,
        "known_limitations": audit.get("known_limitations", []),
        "step_status": "COMPLETE" if promotion_status == STRATEGY_OUTCOME_BASELINE_STATUS else "INCOMPLETE",
        "ready_for_review": promotion_status == STRATEGY_OUTCOME_BASELINE_STATUS,
    }


def write_outcome_baseline_promotion_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def write_outcome_baseline_promotion_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Strategy Outcome Baseline Promotion",
        "",
        f"STATUS: {report['promotion_status']}",
        "",
        f"- Version: {report['outcome_version']}",
        f"- Profile: {report['outcome_profile']}",
        f"- Config hash: `{report['outcome_config_hash']}`",
        f"- Dataset hash: `{report['outcome_dataset_hash']}`",
        f"- Structural audit: {report['audit_version']} / {report['overall_audit_result']}",
        f"- Baseline decision: {report['baseline_decision']}",
        "- Independent Command 02 completeness verification: 105/105.",
        "",
        "STRATEGY_OUTCOME_V1 is frozen unchanged as the authoritative swing daily historical outcome-labeling baseline. The four-session horizon remains canonical even though its audit classification is LIKELY_TOO_SHORT; extended horizons remain audit-only.",
        "",
        "The WEAK descriptive pattern is historical structure, not a profitability claim and not a reason to alter entry, risk, score, stop, target, or exit rules.",
        "",
        "Outcome data may use future prices only in this evaluation layer. Features, candidates, setup, regime, entry, risk, and score must not consume it.",
        "",
        "The next research phase must use a portfolio-level backtest that explicitly handles concurrency, capital availability, same-symbol overlap, portfolio risk, and deterministic opportunity selection. No backtest was started by this promotion.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}
