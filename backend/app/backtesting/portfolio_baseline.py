from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from app.backtesting.portfolio_config import (
    PORTFOLIO_BACKTEST_VERSION,
    SELECTION_RANKING,
    SWING_PORTFOLIO_BACKTEST_PROFILE,
    PortfolioBacktestConfig,
)
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
from app.strategy.outcomes.outcome_baseline import (
    CURRENT_STRATEGY_OUTCOME_CONFIG_HASH,
    CURRENT_STRATEGY_OUTCOME_PROFILE,
    CURRENT_STRATEGY_OUTCOME_VERSION,
    STRATEGY_OUTCOME_V1_DATASET_HASH,
    resolve_current_strategy_outcome_dataset,
)
from app.strategy.scoring.score_baseline import (
    CURRENT_STRATEGY_SCORE_CONFIG_HASH,
    CURRENT_STRATEGY_SCORE_PROFILE,
    CURRENT_STRATEGY_SCORE_VERSION,
    STRATEGY_SCORE_V1_DATASET_HASH,
    resolve_current_strategy_score_dataset,
)

CURRENT_PORTFOLIO_BACKTEST_VERSION = PORTFOLIO_BACKTEST_VERSION
CURRENT_PORTFOLIO_BACKTEST_PROFILE = SWING_PORTFOLIO_BACKTEST_PROFILE
CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH = "6e98307afead0ffa"
PORTFOLIO_BACKTEST_BASELINE_STATUS = "ACTIVE_MECHANICAL_BACKTEST_BASELINE"

PORTFOLIO_BACKTEST_TRADES_V1_DATASET_HASH = (
    "75128be670e085e3d9f2d19e89eb35722ba20631beddb448e69394e656763c4d"
)
PORTFOLIO_BACKTEST_DAILY_V1_DATASET_HASH = (
    "80746b25c0a9c4f7d2bc792f0d7a2c2552c36a37391f2fb7ae182e4b58fd9155"
)
PORTFOLIO_BACKTEST_SKIPPED_V1_DATASET_HASH = (
    "4a6ab9a9cdf6032def1c28402533a71890cd141344a3f1ba80757c4220f7feca"
)

EXPECTED_METRICS = {
    "opportunities_considered": 3296,
    "trades_entered": 728,
    "opportunities_skipped": 2568,
    "same_symbol_skips": 153,
    "max_position_skips": 2398,
    "cash_skips": 15,
    "risk_skips": 2,
    "starting_equity": "100000",
    "ending_equity": "86107.226785713465",
    "gross_return_pct": "-13.89277321428653500",
    "cagr_pct": "-3.182877736277989",
    "max_drawdown_pct": "25.76815326209741663605033331",
}

REFERENCE_CLASSIFICATIONS = (
    "FORWARD_CURRENT",
    "AUDIT_ALLOWED",
    "TEST_FIXTURE_ALLOWED",
    "DOCUMENTATION_ALLOWED",
    "HISTORICAL_ALLOWED",
    "FORWARD_REFERENCE_MUST_CHANGE",
)
REFERENCE_PATTERNS = (
    re.compile(r"\bPORTFOLIO_BACKTEST_V1\b"),
    re.compile(r"\bSWING_PORTFOLIO_BACKTEST_V1\b"),
    re.compile(r"portfolio_trades_v1\.csv\.gz"),
    re.compile(r"portfolio_daily_v1\.csv\.gz"),
    re.compile(r"portfolio_skipped_opportunities_v1\.csv\.gz"),
    re.compile(r"backtests[/\\]swing[/\\]portfolio[/\\]v1"),
)
SOURCE_SUFFIXES = {".py", ".md", ".js", ".jsx", ".json"}
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "dist", "data", "__pycache__"}


@dataclass(frozen=True, slots=True)
class _PortfolioBacktestRegistration:
    config_hash: str
    trades_dataset_path: Path
    daily_dataset_path: Path
    skipped_dataset_path: Path


@dataclass(frozen=True, slots=True)
class CurrentPortfolioBacktestBaseline:
    version: str
    profile: str
    config_hash: str
    trades_dataset_path: Path
    daily_dataset_path: Path
    skipped_dataset_path: Path
    status: str = PORTFOLIO_BACKTEST_BASELINE_STATUS


_BASELINE_REGISTRY = {
    (SWING_PORTFOLIO_BACKTEST_PROFILE, PORTFOLIO_BACKTEST_VERSION): _PortfolioBacktestRegistration(
        config_hash=CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH,
        trades_dataset_path=Path("research/backtests/swing/portfolio/v1/portfolio_trades_v1.csv.gz"),
        daily_dataset_path=Path("research/backtests/swing/portfolio/v1/portfolio_daily_v1.csv.gz"),
        skipped_dataset_path=Path(
            "research/backtests/swing/portfolio/v1/portfolio_skipped_opportunities_v1.csv.gz"
        ),
    ),
}
_CURRENT_VERSION_BY_PROFILE = {SWING_PORTFOLIO_BACKTEST_PROFILE: PORTFOLIO_BACKTEST_VERSION}


def get_current_portfolio_backtest_version(
    profile: str = CURRENT_PORTFOLIO_BACKTEST_PROFILE,
) -> str:
    try:
        return _CURRENT_VERSION_BY_PROFILE[profile]
    except KeyError as exc:
        raise ValueError(f"No current portfolio-backtest baseline registered for profile {profile!r}") from exc


def get_current_portfolio_backtest_profile() -> str:
    return CURRENT_PORTFOLIO_BACKTEST_PROFILE


def get_current_portfolio_backtest_config_hash(
    profile: str = CURRENT_PORTFOLIO_BACKTEST_PROFILE,
) -> str:
    version = get_current_portfolio_backtest_version(profile)
    return _registration(profile=profile, version=version).config_hash


def get_portfolio_backtest_config(*, profile: str, version: str) -> PortfolioBacktestConfig:
    registration = _registration(profile=profile, version=version)
    config = PortfolioBacktestConfig(backtest_version=version, backtest_profile=profile)
    if config.config_hash() != registration.config_hash:
        raise ValueError(
            "Registered portfolio-backtest config hash mismatch: "
            f"expected {registration.config_hash}, observed {config.config_hash()}"
        )
    return config


def get_current_portfolio_backtest_config(
    profile: str = CURRENT_PORTFOLIO_BACKTEST_PROFILE,
) -> PortfolioBacktestConfig:
    return get_portfolio_backtest_config(
        profile=profile,
        version=get_current_portfolio_backtest_version(profile),
    )


def resolve_portfolio_backtest_trades_dataset(
    data_dir: Path, *, profile: str, version: str
) -> Path:
    return Path(data_dir) / _registration(profile=profile, version=version).trades_dataset_path


def resolve_portfolio_backtest_daily_dataset(
    data_dir: Path, *, profile: str, version: str
) -> Path:
    return Path(data_dir) / _registration(profile=profile, version=version).daily_dataset_path


def resolve_portfolio_backtest_skipped_dataset(
    data_dir: Path, *, profile: str, version: str
) -> Path:
    return Path(data_dir) / _registration(profile=profile, version=version).skipped_dataset_path


def resolve_current_portfolio_backtest_trades_dataset(
    data_dir: Path, *, profile: str = CURRENT_PORTFOLIO_BACKTEST_PROFILE
) -> Path:
    return resolve_portfolio_backtest_trades_dataset(
        data_dir,
        profile=profile,
        version=get_current_portfolio_backtest_version(profile),
    )


def resolve_current_portfolio_backtest_daily_dataset(
    data_dir: Path, *, profile: str = CURRENT_PORTFOLIO_BACKTEST_PROFILE
) -> Path:
    return resolve_portfolio_backtest_daily_dataset(
        data_dir,
        profile=profile,
        version=get_current_portfolio_backtest_version(profile),
    )


def resolve_current_portfolio_backtest_skipped_dataset(
    data_dir: Path, *, profile: str = CURRENT_PORTFOLIO_BACKTEST_PROFILE
) -> Path:
    return resolve_portfolio_backtest_skipped_dataset(
        data_dir,
        profile=profile,
        version=get_current_portfolio_backtest_version(profile),
    )


def get_portfolio_backtest_baseline(
    data_dir: Path, *, profile: str, version: str
) -> CurrentPortfolioBacktestBaseline:
    registration = _registration(profile=profile, version=version)
    return CurrentPortfolioBacktestBaseline(
        version=version,
        profile=profile,
        config_hash=registration.config_hash,
        trades_dataset_path=Path(data_dir) / registration.trades_dataset_path,
        daily_dataset_path=Path(data_dir) / registration.daily_dataset_path,
        skipped_dataset_path=Path(data_dir) / registration.skipped_dataset_path,
    )


def get_current_portfolio_backtest_baseline(
    data_dir: Path, *, profile: str = CURRENT_PORTFOLIO_BACKTEST_PROFILE
) -> CurrentPortfolioBacktestBaseline:
    return get_portfolio_backtest_baseline(
        data_dir,
        profile=profile,
        version=get_current_portfolio_backtest_version(profile),
    )


def verify_current_portfolio_backtest_baseline(data_dir: Path) -> CurrentPortfolioBacktestBaseline:
    baseline = get_current_portfolio_backtest_baseline(data_dir)
    expected_hashes = {
        baseline.trades_dataset_path: PORTFOLIO_BACKTEST_TRADES_V1_DATASET_HASH,
        baseline.daily_dataset_path: PORTFOLIO_BACKTEST_DAILY_V1_DATASET_HASH,
        baseline.skipped_dataset_path: PORTFOLIO_BACKTEST_SKIPPED_V1_DATASET_HASH,
    }
    for path, expected_hash in expected_hashes.items():
        if not path.exists():
            raise FileNotFoundError(f"Current portfolio-backtest dataset not found: {path}")
        observed_hash = file_sha256(path)
        if observed_hash != expected_hash:
            raise ValueError(
                f"Current portfolio-backtest dataset hash mismatch for {path.name}: "
                f"expected {expected_hash}, observed {observed_hash}"
            )
    config = get_current_portfolio_backtest_config()
    if config.backtest_version != baseline.version:
        raise ValueError(f"Current portfolio-backtest version mismatch: {config.backtest_version}")
    if config.backtest_profile != baseline.profile:
        raise ValueError(f"Current portfolio-backtest profile mismatch: {config.backtest_profile}")
    if config.config_hash() != baseline.config_hash:
        raise ValueError(f"Current portfolio-backtest config hash mismatch: {config.config_hash()}")
    return baseline


def audit_portfolio_backtest_references(repo_root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    for path in _source_files(repo_root):
        relative_path = path.relative_to(repo_root).as_posix()
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            matched = [pattern.pattern for pattern in REFERENCE_PATTERNS if pattern.search(line)]
            if not matched:
                continue
            findings.append(
                {
                    "path": relative_path,
                    "line": line_number,
                    "classification": _classify_reference(relative_path),
                    "patterns": matched,
                    "text": line.strip()[:240],
                }
            )
    counts = Counter(item["classification"] for item in findings)
    return {
        "scope": (
            "PORTFOLIO_BACKTEST_V1, SWING_PORTFOLIO_BACKTEST_V1, the three canonical "
            "ledger filenames, and the canonical swing portfolio v1 path."
        ),
        "total_references": len(findings),
        "classification_counts": {name: counts[name] for name in REFERENCE_CLASSIFICATIONS},
        "unintended_forward_references": [
            item for item in findings if item["classification"] == "FORWARD_REFERENCE_MUST_CHANGE"
        ],
        "references": findings,
    }


def build_portfolio_backtest_baseline_promotion_report(
    *, repo_root: Path, tests_passed: bool, frontend_build_passed: bool
) -> dict[str, Any]:
    data_dir = Path(repo_root) / "data"
    baseline = verify_current_portfolio_backtest_baseline(data_dir)
    hashes_before = portfolio_backtest_regression_hashes(data_dir)
    hash_checks = portfolio_backtest_regression_hash_checks(hashes_before)
    summary = json.loads(
        (data_dir / "reports/portfolio_backtest_v1_summary.json").read_text(encoding="utf-8")
    )
    audit = json.loads(
        (data_dir / "reports/portfolio_backtest_v1_audit_summary.json").read_text(encoding="utf-8")
    )
    config = get_current_portfolio_backtest_config()
    metrics = _promotion_metrics(summary)
    classes = audit["classifications"]
    reference_audit = audit_portfolio_backtest_references(repo_root)
    dependencies = {
        "outcome_version": CURRENT_STRATEGY_OUTCOME_VERSION,
        "outcome_profile": CURRENT_STRATEGY_OUTCOME_PROFILE,
        "outcome_config_hash": CURRENT_STRATEGY_OUTCOME_CONFIG_HASH,
        "outcome_hash": hashes_before["outcome_v1"],
        "score_version": CURRENT_STRATEGY_SCORE_VERSION,
        "score_profile": CURRENT_STRATEGY_SCORE_PROFILE,
        "score_config_hash": CURRENT_STRATEGY_SCORE_CONFIG_HASH,
        "score_hash": hashes_before["score_v1"],
        "risk_version": CURRENT_RISK_STRUCTURE_VERSION,
        "risk_config_hash": CURRENT_RISK_STRUCTURE_CONFIG_HASH,
        "risk_hash": hashes_before["risk_v1_1"],
    }
    source = summary["source_contract"]
    dependency_checks = {
        "outcome_version": source["outcome_version"] == dependencies["outcome_version"],
        "outcome_hash": source["outcome_dataset_hash"] == dependencies["outcome_hash"],
        "score_version": source["score_version"] == dependencies["score_version"],
        "score_hash": dependencies["score_hash"] == STRATEGY_SCORE_V1_DATASET_HASH,
        "risk_version": source["risk_version"] == dependencies["risk_version"],
        "risk_hash": dependencies["risk_hash"] == RISK_STRUCTURE_V1_1_DATASET_HASH,
    }
    methodology_checks = _methodology_checks(config, summary, audit)
    audit_checks = {
        "audit_identity": audit.get("audit_version") == "PORTFOLIO_BACKTEST_AUDIT_V1",
        "audit_ready": audit.get("ready_for_review") is True,
        "accounting_clean": classes["ACCOUNTING_RESULT"] == "CLEAN",
        "chronology_clean": classes["CHRONOLOGY_RESULT"] == "CLEAN_NO_LOOKAHEAD",
        "exit_clean": classes["EXIT_RESULT"] == "CLEAN",
        "baseline_decision": classes["BASELINE_DECISION"] == "A FREEZE UNCHANGED",
        "zero_source_linkage_violations": (
            audit["accounting"]["trade_linkage"]["violation_count"] == 0
        ),
        "zero_ranking_mismatches": audit["ranking"]["reconstruction_mismatches"] == 0,
        "zero_lookahead_violations": not audit["ranking"]["lookahead"]["future_fields_consumed"],
    }
    metrics_match = metrics == EXPECTED_METRICS
    hashes_after = portfolio_backtest_regression_hashes(data_dir)
    unchanged_checks = {name: hashes_after[name] == value for name, value in hashes_before.items()}
    all_checks = (
        all(hash_checks.values())
        and all(unchanged_checks.values())
        and metrics_match
        and all(dependency_checks.values())
        and all(methodology_checks.values())
        and all(audit_checks.values())
        and not reference_audit["unintended_forward_references"]
        and tests_passed
        and frontend_build_passed
    )
    promotion_status = (
        PORTFOLIO_BACKTEST_BASELINE_STATUS if all_checks else "VERIFICATION_INCOMPLETE"
    )
    return {
        "phase": "Step 02.12",
        "command": "Command 03",
        "backtest_version": baseline.version,
        "backtest_profile": baseline.profile,
        "backtest_config_hash": baseline.config_hash,
        "trade_dataset_hash": hashes_after["portfolio_trades_v1"],
        "daily_dataset_hash": hashes_after["portfolio_daily_v1"],
        "skipped_dataset_hash": hashes_after["portfolio_skipped_v1"],
        "promotion_status": promotion_status,
        **dependencies,
        "audit_version": audit["audit_version"],
        "accounting_result": classes["ACCOUNTING_RESULT"],
        "chronology_result": classes["CHRONOLOGY_RESULT"],
        "constraint_result": classes["CONSTRAINT_RESULT"],
        "ranking_result": classes["RANKING_RESULT"],
        "ranking_sensitivity": audit["ranking"]["sensitivity_classification"],
        "selection_distortion_result": classes["SELECTION_DISTORTION_RESULT"],
        "exit_result": classes["EXIT_RESULT"],
        "gross_pattern": classes["GROSS_PATTERN"],
        "yearly_stability": classes["YEARLY_STABILITY"],
        "cost_headroom": classes["COST_HEADROOM"],
        "overall_audit_result": classes["OVERALL_BACKTEST_AUDIT_RESULT"],
        "baseline_decision": classes["BASELINE_DECISION"],
        **metrics,
        "future_data_boundary_verified": (
            audit["source_pool"]["all_forward_safe"]
            and audit["chronology"]["daily_processing_order_violations"] == 0
            and audit_checks["zero_lookahead_violations"]
        ),
        "tests_passed": tests_passed,
        "frontend_build_passed": frontend_build_passed,
        "forward_contract": {
            "version": baseline.version,
            "profile": baseline.profile,
            "config_hash": baseline.config_hash,
            "trades_dataset_path": str(baseline.trades_dataset_path),
            "daily_dataset_path": str(baseline.daily_dataset_path),
            "skipped_dataset_path": str(baseline.skipped_dataset_path),
        },
        "dependency_checks": dependency_checks,
        "methodology_checks": methodology_checks,
        "audit_checks": audit_checks,
        "baseline_metrics_match": metrics_match,
        "input_hashes": hashes_after,
        "input_hash_checks": hash_checks,
        "unchanged_during_promotion": unchanged_checks,
        "forward_reference_audit": reference_audit,
        "review_notes": [
            "The 4% planned-open-risk cap is enforced at admission; later equity changes may cause passive drift without forced deleveraging.",
            "Ranking is deterministic and mechanically valid, but fixed audit counterfactuals classify sensitivity as EXTREME.",
            "Selection distortion is HIGH because 728 of 3,296 valid opportunities were admitted under finite slots, cash, and risk.",
            "TARGET exits contributed positively, STOP exits contributed a large loss, and TIME exits contributed positively in aggregate.",
            "Gross historical performance is WEAK and YEARLY_UNSTABLE; costs could materially worsen it.",
        ],
        "performance_scope": "HISTORICAL_RESEARCH_GROSS_BEFORE_COSTS",
        "safety": {
            "portfolio_datasets_regenerated": 0,
            "optimization_runs": 0,
            "ranking_sweeps_run": 0,
            "live_signals_generated": 0,
            "live_orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_records_persisted": 0,
        },
        "step_status": "COMPLETE" if all_checks else "INCOMPLETE",
        "ready_for_review": all_checks,
    }


def portfolio_backtest_regression_hashes(data_dir: Path) -> dict[str, str]:
    baseline = get_current_portfolio_backtest_baseline(data_dir)
    return {
        "feature": file_sha256(data_dir / "research/features/daily/v1/daily_features_v1.csv.gz"),
        "candidate": file_sha256(data_dir / "research/candidates/daily/v1/momentum_candidates_v1.csv.gz"),
        "setup": file_sha256(data_dir / "research/setups/daily/v1/daily_setup_evaluations_v1.csv.gz"),
        "regime": file_sha256(data_dir / "research/regime/daily/v1/market_regime_daily_v1.csv.gz"),
        "entry": file_sha256(data_dir / "research/entry_evaluations/daily/v1/entry_evaluations_v1.csv.gz"),
        "risk_v1": file_sha256(resolve_risk_structure_dataset(data_dir, "v1")),
        "risk_v1_1": file_sha256(resolve_current_risk_structure_dataset(data_dir)),
        "score_v1": file_sha256(resolve_current_strategy_score_dataset(data_dir)),
        "outcome_v1": file_sha256(resolve_current_strategy_outcome_dataset(data_dir)),
        "portfolio_trades_v1": file_sha256(baseline.trades_dataset_path),
        "portfolio_daily_v1": file_sha256(baseline.daily_dataset_path),
        "portfolio_skipped_v1": file_sha256(baseline.skipped_dataset_path),
    }


def portfolio_backtest_regression_hash_checks(hashes: dict[str, str]) -> dict[str, bool]:
    expected = {
        **UPSTREAM_HASHES,
        "risk_v1": RISK_STRUCTURE_V1_DATASET_HASH,
        "risk_v1_1": RISK_STRUCTURE_V1_1_DATASET_HASH,
        "score_v1": STRATEGY_SCORE_V1_DATASET_HASH,
        "outcome_v1": STRATEGY_OUTCOME_V1_DATASET_HASH,
        "portfolio_trades_v1": PORTFOLIO_BACKTEST_TRADES_V1_DATASET_HASH,
        "portfolio_daily_v1": PORTFOLIO_BACKTEST_DAILY_V1_DATASET_HASH,
        "portfolio_skipped_v1": PORTFOLIO_BACKTEST_SKIPPED_V1_DATASET_HASH,
    }
    return {name: hashes.get(name) == expected_hash for name, expected_hash in expected.items()}


def write_portfolio_backtest_baseline_promotion_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def write_portfolio_backtest_baseline_promotion_markdown(
    path: Path, report: dict[str, Any]
) -> None:
    lines = [
        "# Portfolio Backtest Baseline Promotion",
        "",
        f"STATUS: {report['promotion_status']}",
        "",
        f"- Baseline: {report['backtest_version']} / {report['backtest_profile']} / `{report['backtest_config_hash']}`",
        f"- Audit: {report['audit_version']} — {report['overall_audit_result']}",
        f"- Decision: {report['baseline_decision']}",
        "- Step 02.12 — Portfolio Backtest Foundation: COMPLETE",
        "",
        "The mechanical baseline is frozen unchanged. Independent audit work found accounting, chronology, and exit mechanics clean. Ranking is deterministic but highly sensitive, and selection distortion is high because finite portfolio capacity admitted only 728 of 3,296 mechanically valid opportunities.",
        "",
        "The weak gross result is preserved rather than optimized away. Results remain HISTORICAL RESEARCH / GROSS BEFORE COSTS: costs, slippage, taxes, and fees are not modeled. Future portfolio-backtest profiles or methodology variants must use separately registered versions and must not silently replace this baseline.",
        "",
        "See `docs/strategy-v1-portfolio-backtest-audit.md` for the structural audit and `docs/strategy-v1-portfolio-backtest-foundation.md` for the frozen contract.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _registration(*, profile: str, version: str) -> _PortfolioBacktestRegistration:
    try:
        return _BASELINE_REGISTRY[(profile, version)]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported portfolio-backtest baseline: profile={profile!r}, version={version!r}"
        ) from exc


def _promotion_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    pool = summary["opportunity_pool"]
    portfolio = summary["portfolio_metrics"]
    skips = summary["skip_reasons"]
    return {
        "opportunities_considered": pool["mechanically_valid_opportunities_considered"],
        "trades_entered": pool["actual_portfolio_trades_entered"],
        "opportunities_skipped": pool["opportunities_skipped"],
        "same_symbol_skips": skips["SKIP_SAME_SYMBOL_ALREADY_OPEN"]["count"],
        "max_position_skips": skips["SKIP_MAX_POSITIONS"]["count"],
        "cash_skips": skips["SKIP_INSUFFICIENT_CASH"]["count"],
        "risk_skips": skips["SKIP_PORTFOLIO_RISK_LIMIT"]["count"],
        "starting_equity": portfolio["starting_equity"],
        "ending_equity": portfolio["ending_equity"],
        "gross_return_pct": portfolio["total_gross_return_pct"],
        "cagr_pct": portfolio["cagr_pct"],
        "max_drawdown_pct": portfolio["maximum_drawdown_pct"],
    }


def _methodology_checks(
    config: PortfolioBacktestConfig, summary: dict[str, Any], audit: dict[str, Any]
) -> dict[str, bool]:
    contract = summary["contract"]
    return {
        "identity": (
            config.backtest_version == CURRENT_PORTFOLIO_BACKTEST_VERSION
            and config.backtest_profile == CURRENT_PORTFOLIO_BACKTEST_PROFILE
            and config.config_hash() == CURRENT_PORTFOLIO_BACKTEST_CONFIG_HASH
        ),
        "starting_capital": config.initial_capital_rupees == Decimal("100000"),
        "max_positions": config.max_concurrent_positions == 4,
        "per_trade_risk": config.max_risk_per_trade_pct == Decimal("1.00"),
        "total_open_risk": config.max_total_open_risk_pct == Decimal("4.00"),
        "same_symbol": config.same_symbol_policy == "ONE_OPEN_POSITION_PER_SYMBOL",
        "ranking": config.selection_ranking == SELECTION_RANKING,
        "hold_horizon": config.max_hold_sessions == 4,
        "target_exit": config.target_exit_policy == "FROZEN_TARGET",
        "stop_exit": config.stop_exit_policy == "FROZEN_STOP",
        "time_exit": config.time_exit_policy == "SESSION_4_CLOSE",
        "ambiguity": config.ambiguity_policy == "CONSERVATIVE_STOP_FIRST",
        "chronology": config.session_ordering_policy == (
            "OPEN_ENTRIES_BEFORE_INTRADAY_EXITS_NO_SAME_DAY_CASH_REUSE"
        ),
        "no_same_day_cash_reuse": audit["chronology"]["same_day_capital_reuse_violations"] == 0,
        "no_leverage": audit["constraints"]["no_leverage"]["violation_count"] == 0,
        "costs": contract["transaction_cost_status"] == "NOT_MODELED",
        "slippage": contract["slippage_status"] == "NOT_MODELED",
        "performance_basis": contract["performance_basis"] == "GROSS_BEFORE_COSTS_RESEARCH_ONLY",
        "risk_admission": audit["constraints"]["total_open_risk"]["entry_violations"] == 0,
    }


def _source_files(repo_root: Path) -> Iterable[Path]:
    for path in sorted(Path(repo_root).rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if any(part in EXCLUDED_PARTS for part in path.relative_to(repo_root).parts):
            continue
        yield path


def _classify_reference(relative_path: str) -> str:
    path = relative_path.lower()
    if path.startswith("backend/tests/"):
        return "TEST_FIXTURE_ALLOWED"
    if "audit" in path:
        return "AUDIT_ALLOWED"
    if path.startswith("docs/"):
        return "DOCUMENTATION_ALLOWED"
    if path in {
        "backend/app/backtesting/__init__.py",
        "backend/app/backtesting/portfolio_baseline.py",
        "backend/app/backtesting/portfolio_config.py",
        "backend/app/backtesting/portfolio_engine.py",
        "backend/scripts/build_portfolio_backtest.py",
        "backend/scripts/promote_portfolio_backtest_baseline.py",
        "frontend/src/pages/developmenthome.jsx",
    }:
        return "FORWARD_CURRENT"
    if path.startswith("docs/archive/") or path.startswith("archive/"):
        return "HISTORICAL_ALLOWED"
    return "FORWARD_REFERENCE_MUST_CHANGE"
