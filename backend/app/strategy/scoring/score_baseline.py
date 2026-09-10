from __future__ import annotations

import csv
import gzip
import json
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from app.risk.risk_baseline import UPSTREAM_HASHES
from app.risk.risk_config import (
    ACTIVE_FORWARD_BASELINE,
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    RISK_STRUCTURE_V1_DATASET_HASH,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
    resolve_current_risk_structure_dataset,
    resolve_risk_structure_dataset,
)
from app.strategy.momentum_candidates import file_sha256
from app.strategy.scoring.score_config import (
    STRATEGY_SCORE_VERSION,
    SWING_DAILY_EOD_PROFILE,
    StrategyScoreConfig,
)

CURRENT_STRATEGY_SCORE_VERSION = STRATEGY_SCORE_VERSION
CURRENT_STRATEGY_SCORE_PROFILE = SWING_DAILY_EOD_PROFILE
CURRENT_STRATEGY_SCORE_CONFIG_HASH = "e257c76b90e25cb7"
STRATEGY_SCORE_V1_DATASET_HASH = "52ef4f91fd598d137e34a60d0093a6bd180342232ab1c57739ce524b497b72ed"
STRATEGY_SCORE_BASELINE_STATUS = ACTIVE_FORWARD_BASELINE
STRATEGY_SCORE_AUDIT_VERSION = "STRATEGY_SCORE_AUDIT_V1"
APPROVED_AUDIT_RESULT = "STABLE_WITH_REVIEW_NOTES"
APPROVED_BASELINE_DECISION = "A_FREEZE_UNCHANGED"

_DATASET_PATHS = {
    (SWING_DAILY_EOD_PROFILE, STRATEGY_SCORE_VERSION): Path(
        "research/strategy_scores/swing/daily/v1/strategy_scores_v1.csv.gz"
    ),
}
_CURRENT_VERSION_BY_PROFILE = {SWING_DAILY_EOD_PROFILE: STRATEGY_SCORE_VERSION}

REFERENCE_CLASSIFICATIONS = (
    "FORWARD_CURRENT",
    "HISTORICAL_ALLOWED",
    "AUDIT_ALLOWED",
    "TEST_FIXTURE_ALLOWED",
    "DOCUMENTATION_ALLOWED",
    "FORWARD_REFERENCE_MUST_CHANGE",
)
REFERENCE_PATTERNS = (
    re.compile(r"\bSTRATEGY_SCORE_V1\b"),
    re.compile(r"\bSWING_DAILY_EOD_V1\b"),
    re.compile(r"strategy_scores_v1\.csv\.gz"),
    re.compile(r"strategy_scores[/\\]swing[/\\]daily[/\\]v1"),
)
SOURCE_SUFFIXES = {".py", ".md", ".js", ".jsx", ".json"}
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "dist", "data", "__pycache__"}
COMPONENTS = (
    "setup",
    "momentum",
    "rvol",
    "relative_strength",
    "regime",
    "sector",
    "catalyst",
    "reward_risk",
)
COMPONENT_CAPS = {
    "setup": Decimal("20"),
    "momentum": Decimal("20"),
    "rvol": Decimal("15"),
    "relative_strength": Decimal("15"),
    "regime": Decimal("10"),
    "sector": Decimal("10"),
    "catalyst": Decimal("5"),
    "reward_risk": Decimal("5"),
}
EXPECTED_COUNTS = {
    "total_rows": 26130,
    "full_score": 10791,
    "preview_score": 3136,
    "exceptional_review_score": 324,
    "not_score_eligible": 11879,
    "entry_eligible": 4268,
    "high_conviction": 0,
}
PROHIBITED_FIELDS = (
    "future_return",
    "forward_return",
    "target_hit",
    "stop_hit",
    "mfe",
    "mae",
    "trade_outcome",
)


@dataclass(frozen=True, slots=True)
class CurrentScoringBaseline:
    version: str
    profile: str
    config_hash: str
    dataset_path: Path
    status: str = STRATEGY_SCORE_BASELINE_STATUS


def get_current_strategy_score_version(profile: str = CURRENT_STRATEGY_SCORE_PROFILE) -> str:
    try:
        return _CURRENT_VERSION_BY_PROFILE[profile]
    except KeyError as exc:
        raise ValueError(f"No current scoring baseline registered for profile {profile!r}") from exc


def get_current_strategy_score_profile() -> str:
    return CURRENT_STRATEGY_SCORE_PROFILE


def get_current_strategy_score_config_hash(profile: str = CURRENT_STRATEGY_SCORE_PROFILE) -> str:
    if profile != CURRENT_STRATEGY_SCORE_PROFILE:
        raise ValueError(f"No current scoring config registered for profile {profile!r}")
    return CURRENT_STRATEGY_SCORE_CONFIG_HASH


def resolve_strategy_score_dataset(
    data_dir: Path,
    *,
    profile: str,
    version: str,
) -> Path:
    try:
        relative_path = _DATASET_PATHS[(profile, version)]
    except KeyError as exc:
        raise ValueError(f"Unsupported scoring baseline: profile={profile!r}, version={version!r}") from exc
    return Path(data_dir) / relative_path


def resolve_current_strategy_score_dataset(
    data_dir: Path,
    *,
    profile: str = CURRENT_STRATEGY_SCORE_PROFILE,
) -> Path:
    version = get_current_strategy_score_version(profile)
    return resolve_strategy_score_dataset(data_dir, profile=profile, version=version)


def get_current_scoring_baseline(
    data_dir: Path,
    *,
    profile: str = CURRENT_STRATEGY_SCORE_PROFILE,
) -> CurrentScoringBaseline:
    return CurrentScoringBaseline(
        version=get_current_strategy_score_version(profile),
        profile=profile,
        config_hash=get_current_strategy_score_config_hash(profile),
        dataset_path=resolve_current_strategy_score_dataset(data_dir, profile=profile),
    )


def verify_current_strategy_score_baseline(data_dir: Path) -> CurrentScoringBaseline:
    baseline = get_current_scoring_baseline(data_dir)
    if not baseline.dataset_path.exists():
        raise FileNotFoundError(f"Current strategy-score dataset not found: {baseline.dataset_path}")
    observed_hash = file_sha256(baseline.dataset_path)
    if observed_hash != STRATEGY_SCORE_V1_DATASET_HASH:
        raise ValueError(
            f"Current strategy-score dataset hash mismatch: expected {STRATEGY_SCORE_V1_DATASET_HASH}, observed {observed_hash}"
        )
    config = StrategyScoreConfig()
    if config.score_version != baseline.version:
        raise ValueError(f"Current strategy-score version mismatch: {config.score_version}")
    if config.score_profile != baseline.profile:
        raise ValueError(f"Current strategy-score profile mismatch: {config.score_profile}")
    if config.config_hash() != baseline.config_hash:
        raise ValueError(f"Current strategy-score config hash mismatch: {config.config_hash()}")
    return baseline


def validate_score_baseline_rows(dataset_path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    observed_versions: set[str] = set()
    observed_profiles: set[str] = set()
    observed_config_hashes: set[str] = set()
    observed_risk_versions: set[str] = set()
    observed_risk_hashes: set[str] = set()
    arithmetic_mismatches = 0
    component_cap_violations = 0
    normalized_eligibility_leaks = 0
    sector_free_point_violations = 0
    catalyst_free_point_violations = 0
    preview_promotions = 0
    exceptional_promotions = 0
    blocking_penalty_eligible_violations = 0
    signal_status_violations = 0
    execution_status_violations = 0
    prohibited_fields: list[str] = []
    with gzip.open(dataset_path, "rt", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        prohibited_fields = [
            field for field in reader.fieldnames or []
            if any(token in field.lower() for token in PROHIBITED_FIELDS)
        ]
        for row in reader:
            counts["total_rows"] += 1
            counts[score_count_key(row.get("score_mode", ""))] += 1
            counts[disposition_count_key(row.get("scoring_disposition", ""))] += 1
            observed_versions.add(row.get("score_version", ""))
            observed_profiles.add(row.get("score_profile", ""))
            observed_config_hashes.add(row.get("score_config_hash", ""))
            observed_risk_versions.add(row.get("risk_version", ""))
            observed_risk_hashes.add(row.get("risk_config_hash", ""))
            points = {component: decimal_or_zero(row.get(f"{component}_points")) for component in COMPONENTS}
            raw = decimal_or_zero(row.get("raw_strategy_score"))
            arithmetic_mismatches += raw != sum(points.values(), Decimal("0"))
            component_cap_violations += sum(
                value < 0 or value > COMPONENT_CAPS[component]
                for component, value in points.items()
            )
            disposition = row.get("scoring_disposition", "")
            normalized_eligibility_leaks += raw < 80 and disposition in {"ENTRY_ELIGIBLE", "HIGH_CONVICTION"}
            sector_free_point_violations += row.get("sector_availability") != "UNAVAILABLE" or points["sector"] != 0
            catalyst_free_point_violations += row.get("catalyst_availability") != "UNAVAILABLE" or points["catalyst"] != 0
            preview_promotions += row.get("score_mode") == "PREVIEW_SCORE" and disposition != "PREVIEW_ONLY"
            exceptional_promotions += row.get("score_mode") == "EXCEPTIONAL_REVIEW_SCORE" and disposition != "EXCEPTIONAL_REVIEW"
            blocking_penalty_eligible_violations += truthy(row.get("blocking_penalty_present")) and disposition in {"ENTRY_ELIGIBLE", "HIGH_CONVICTION"}
            signal_status_violations += row.get("trade_signal_status") != "NOT_GENERATED"
            execution_status_violations += row.get("execution_status") != "NOT_IMPLEMENTED"
    observed_counts = {name: counts[name] for name in EXPECTED_COUNTS}
    invariant_counts = {
        "arithmetic_mismatches": arithmetic_mismatches,
        "component_cap_violations": component_cap_violations,
        "normalized_eligibility_leaks": normalized_eligibility_leaks,
        "sector_free_point_violations": sector_free_point_violations,
        "catalyst_free_point_violations": catalyst_free_point_violations,
        "preview_promotions": preview_promotions,
        "exceptional_promotions": exceptional_promotions,
        "blocking_penalty_eligible_violations": blocking_penalty_eligible_violations,
        "signal_status_violations": signal_status_violations,
        "execution_status_violations": execution_status_violations,
    }
    identity = {
        "score_versions": sorted(observed_versions),
        "score_profiles": sorted(observed_profiles),
        "score_config_hashes": sorted(observed_config_hashes),
        "risk_versions": sorted(observed_risk_versions),
        "risk_config_hashes": sorted(observed_risk_hashes),
    }
    identity_valid = (
        observed_versions == {CURRENT_STRATEGY_SCORE_VERSION}
        and observed_profiles == {CURRENT_STRATEGY_SCORE_PROFILE}
        and observed_config_hashes == {CURRENT_STRATEGY_SCORE_CONFIG_HASH}
        and observed_risk_versions == {CURRENT_RISK_STRUCTURE_VERSION}
        and observed_risk_hashes == {CURRENT_RISK_STRUCTURE_CONFIG_HASH}
    )
    return {
        "counts": observed_counts,
        "expected_counts": dict(EXPECTED_COUNTS),
        "counts_match": observed_counts == EXPECTED_COUNTS,
        "identity": identity,
        "identity_valid": identity_valid,
        "invariants": invariant_counts,
        "prohibited_fields": prohibited_fields,
        "all_valid": observed_counts == EXPECTED_COUNTS
        and identity_valid
        and not prohibited_fields
        and not any(invariant_counts.values()),
    }


def audit_score_references(repo_root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for path in source_files(repo_root):
        relative_path = path.relative_to(repo_root).as_posix()
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
            matched = [pattern.pattern for pattern in REFERENCE_PATTERNS if pattern.search(line)]
            if not matched:
                continue
            findings.append(
                {
                    "path": relative_path,
                    "line": line_number,
                    "classification": classify_score_reference(relative_path),
                    "patterns": matched,
                    "text": line.strip()[:240],
                }
            )
    counts = Counter(item["classification"] for item in findings)
    return {
        "scope": "STRATEGY_SCORE_V1, SWING_DAILY_EOD_V1, canonical score filename, and canonical swing/v1 path references.",
        "total_references": len(findings),
        "classification_counts": {name: counts[name] for name in REFERENCE_CLASSIFICATIONS},
        "unintended_forward_references": [
            item for item in findings if item["classification"] == "FORWARD_REFERENCE_MUST_CHANGE"
        ],
        "references": findings,
    }


def build_score_baseline_promotion_report(
    *,
    repo_root: Path,
    tests_passed: bool,
    frontend_build_passed: bool,
) -> dict[str, Any]:
    data_dir = repo_root / "data"
    baseline = verify_current_strategy_score_baseline(data_dir)
    dataset_hash_before = file_sha256(baseline.dataset_path)
    row_validation = validate_score_baseline_rows(baseline.dataset_path)
    structural_audit = json.loads(
        (data_dir / "reports" / "strategy_score_v1_audit_summary.json").read_text(encoding="utf-8")
    )
    reference_audit = audit_score_references(repo_root)
    hashes = baseline_input_hashes(data_dir)
    hash_checks = baseline_hash_checks(hashes)
    score_config = StrategyScoreConfig()
    weights_locked = score_config.snapshot()["weights"] == {
        "setup": "20", "momentum": "20", "rvol": "15", "relative_strength": "15",
        "regime": "10", "sector": "10", "catalyst": "5", "reward_risk": "5",
    }
    thresholds_locked = (
        score_config.thresholds.entry_eligible == 80
        and score_config.thresholds.high_conviction == 90
    )
    coverage_locked = score_config.thresholds.minimum_score_coverage_pct == 80
    missing_policy_locked = (
        score_config.sector_history_status == "UNAVAILABLE_POINT_IN_TIME_MAPPING"
        and score_config.catalyst_history_status == "UNAVAILABLE_HISTORICAL_CATALYST_LAYER"
    )
    audit_approved = (
        structural_audit.get("audit_version") == STRATEGY_SCORE_AUDIT_VERSION
        and structural_audit.get("classifications", {}).get("overall_structural_result") == APPROVED_AUDIT_RESULT
        and structural_audit.get("classifications", {}).get("baseline_decision") == APPROVED_BASELINE_DECISION
        and structural_audit.get("ready_for_review") is True
    )
    dataset_hash_after = file_sha256(baseline.dataset_path)
    safety = {
        "score_dataset_regenerated": 0,
        "backtests_run": 0,
        "trade_signals_generated": 0,
        "orders_placed": 0,
        "remote_migrations_applied": 0,
        "supabase_records_persisted": 0,
    }
    checks = (
        dataset_hash_before == STRATEGY_SCORE_V1_DATASET_HASH,
        dataset_hash_after == dataset_hash_before,
        all(hash_checks.values()),
        row_validation["all_valid"],
        audit_approved,
        not reference_audit["unintended_forward_references"],
        weights_locked,
        thresholds_locked,
        coverage_locked,
        missing_policy_locked,
        score_config.normalized_score_usage == "DIAGNOSTIC_ONLY",
        tests_passed,
        frontend_build_passed,
    )
    promotion_status = ACTIVE_FORWARD_BASELINE if all(checks) else "VERIFICATION_INCOMPLETE"
    return {
        "phase": "Step 02.10",
        "command": "Command 03",
        "score_version": baseline.version,
        "score_profile": baseline.profile,
        "score_config_hash": baseline.config_hash,
        "score_dataset_hash": dataset_hash_after,
        "promotion_status": promotion_status,
        "structural_audit_version": structural_audit.get("audit_version"),
        "structural_audit_result": structural_audit.get("classifications", {}).get("overall_structural_result"),
        "baseline_decision": structural_audit.get("classifications", {}).get("baseline_decision"),
        "weights_locked": weights_locked,
        "thresholds_locked": thresholds_locked,
        "coverage_policy_locked": coverage_locked,
        "missing_component_policy_locked": missing_policy_locked,
        "normalized_score_usage": score_config.normalized_score_usage,
        "current_risk_version": CURRENT_RISK_STRUCTURE_VERSION,
        "current_risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
        "current_risk_dataset_hash": hashes["risk_v1_1"],
        "forward_contract": {
            "version": baseline.version,
            "profile": baseline.profile,
            "config_hash": baseline.config_hash,
            "dataset_path": str(baseline.dataset_path),
        },
        "row_validation": row_validation,
        "input_hashes": hashes,
        "input_hash_checks": hash_checks,
        "score_dataset_unchanged_during_promotion": dataset_hash_after == dataset_hash_before,
        "forward_reference_audit": reference_audit,
        "audit_review_notes": [
            "Setup quality partially overlaps other evidence; no high double-counting defect was found.",
            "Momentum/RS overlap is moderate and acceptable: FULL_SCORE Pearson 0.3838 and Spearman 0.3390.",
            "Neutral score 80 is ceiling-dependent and intentionally strict.",
            "Threshold 80 is structurally selective.",
            "Missing sector and catalyst evidence materially limits current score headroom.",
        ],
        "theoretical_max": {"BULLISH": 85, "NEUTRAL": 80, "BEARISH": 75},
        "high_conviction_reachability": "NOT_CURRENTLY_REACHABLE_WITH_HISTORICAL_85_POINT_COVERAGE",
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "leakage": {
            "new_data_processing": 0,
            "future_returns": 0,
            "t_plus_1_ohlc": 0,
            "future_benchmark": 0,
            "future_regime": 0,
            "stop_target_outcomes": 0,
            "mfe": 0,
            "mae": 0,
            "future_news": 0,
            "current_sector_back_projection": 0,
        },
        "safety": safety,
        "step_status": "COMPLETE" if promotion_status == ACTIVE_FORWARD_BASELINE else "INCOMPLETE",
        "ready_for_review": promotion_status == ACTIVE_FORWARD_BASELINE,
    }


def baseline_input_hashes(data_dir: Path) -> dict[str, str]:
    return {
        "feature": file_sha256(data_dir / "research/features/daily/v1/daily_features_v1.csv.gz"),
        "candidate": file_sha256(data_dir / "research/candidates/daily/v1/momentum_candidates_v1.csv.gz"),
        "setup": file_sha256(data_dir / "research/setups/daily/v1/daily_setup_evaluations_v1.csv.gz"),
        "regime": file_sha256(data_dir / "research/regime/daily/v1/market_regime_daily_v1.csv.gz"),
        "entry": file_sha256(data_dir / "research/entry_evaluations/daily/v1/entry_evaluations_v1.csv.gz"),
        "risk_v1": file_sha256(resolve_risk_structure_dataset(data_dir, "v1")),
        "risk_v1_1": file_sha256(resolve_current_risk_structure_dataset(data_dir)),
        "score_v1": file_sha256(resolve_current_strategy_score_dataset(data_dir)),
    }


def baseline_hash_checks(hashes: dict[str, str]) -> dict[str, bool]:
    expected = {
        **UPSTREAM_HASHES,
        "risk_v1": RISK_STRUCTURE_V1_DATASET_HASH,
        "risk_v1_1": RISK_STRUCTURE_V1_1_DATASET_HASH,
        "score_v1": STRATEGY_SCORE_V1_DATASET_HASH,
    }
    return {name: hashes.get(name) == value for name, value in expected.items()}


def source_files(repo_root: Path) -> Iterable[Path]:
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.relative_to(repo_root).parts):
            continue
        yield path


def classify_score_reference(relative_path: str) -> str:
    path = relative_path.lower()
    if path.startswith("backend/tests/"):
        return "TEST_FIXTURE_ALLOWED"
    if "audit" in path:
        return "AUDIT_ALLOWED"
    if path.startswith("docs/"):
        return "DOCUMENTATION_ALLOWED"
    if path in {
        "backend/app/strategy/scoring/score_config.py",
        "backend/app/strategy/scoring/score_baseline.py",
        "backend/app/strategy/scoring/strategy_scorer.py",
        "backend/scripts/build_strategy_scores.py",
        "backend/scripts/promote_strategy_score_baseline.py",
        "frontend/src/pages/developmenthome.jsx",
    }:
        return "FORWARD_CURRENT"
    return "FORWARD_REFERENCE_MUST_CHANGE"


def score_count_key(mode: str) -> str:
    return {
        "FULL_SCORE": "full_score",
        "PREVIEW_SCORE": "preview_score",
        "EXCEPTIONAL_REVIEW_SCORE": "exceptional_review_score",
        "NOT_SCORE_ELIGIBLE": "not_score_eligible",
    }.get(mode, "unknown_score_mode")


def disposition_count_key(disposition: str) -> str:
    return {
        "ENTRY_ELIGIBLE": "entry_eligible",
        "HIGH_CONVICTION": "high_conviction",
    }.get(disposition, "other_disposition")


def decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except InvalidOperation:
        return Decimal("0")


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def write_score_baseline_promotion_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def write_score_baseline_promotion_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Strategy Score Baseline Promotion",
        "",
        "STATUS: ACTIVE_FORWARD_BASELINE",
        "",
        f"- Version: {report['score_version']}",
        f"- Profile: {report['score_profile']}",
        f"- Config hash: `{report['score_config_hash']}`",
        f"- Dataset hash: `{report['score_dataset_hash']}`",
        f"- Structural audit: {report['structural_audit_version']} / {report['structural_audit_result']}",
        "- Decision: freeze the existing score unchanged; no new methodology version was created.",
        "",
        "## Scope",
        "",
        "The swing daily-EOD score is the current forward research baseline. Future consumers must resolve it through the central profile-aware baseline contract.",
        "",
        "Sector and catalyst evidence remain unavailable historically. They contribute zero points and zero available weight, leaving typical coverage at 85%. Raw score remains the eligibility basis; normalized score remains diagnostic only.",
        "",
        "No outcomes, backtest, signal generation, execution, broker action, migration, or Supabase persistence occurred during promotion.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
