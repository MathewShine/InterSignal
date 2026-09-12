from __future__ import annotations

import csv
import gzip
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.backtesting.portfolio_engine import load_frozen_opportunities
from app.research.temporal_validation.config import (
    DEVELOPMENT_RUN,
    PERFORMANCE_ACCESS,
    STRUCTURAL_METADATA,
    TemporalResearchConfig,
    canonical_hash,
)
from app.research.temporal_validation.guard import (
    ValidationAccessGuard,
    ValidationAuthorization,
)
from app.research.temporal_validation.models import ExperimentFreezeArtifact
from app.strategy.outcomes.outcome_baseline import resolve_current_strategy_outcome_dataset
from app.strategy.scoring.score_baseline import resolve_current_strategy_score_dataset

DEVELOPMENT = "DEVELOPMENT"
VALIDATION = "VALIDATION"
OUTSIDE_FROZEN_WINDOWS = "OUTSIDE_FROZEN_WINDOWS"

VALIDATION_STRUCTURAL_FIELDS = (
    "decision_date",
    "trading_date",
    "symbol",
    "isin",
    "score_version",
    "score_profile",
    "raw_strategy_score",
    "source_raw_strategy_score",
    "source_score_band",
    "source_scoring_disposition",
    "risk_version",
    "outcome_version",
    "outcome_profile",
    "outcome_cohort",
    "primary_evaluation_eligible",
    "setup_quality",
    "candidate_state",
    "candidate_category",
    "regime_state",
    "regime_confidence",
    "effective_reward_risk",
    "reward_risk_ratio",
    "entry_recheck_status",
    "entry_valid",
    "forward_data_safe",
    "forward_data_reasons",
)


def read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def partition_label(value: str | date, config: TemporalResearchConfig) -> str:
    observed = parse_iso_date(value) if isinstance(value, str) else value
    if config.development_start <= observed <= config.development_end:
        return DEVELOPMENT
    if config.validation_start <= observed <= config.validation_terminal_date:
        return VALIDATION
    return OUTSIDE_FROZEN_WINDOWS


def partition_rows(
    rows: Iterable[dict[str, Any]],
    *,
    date_field: str,
    config: TemporalResearchConfig,
) -> dict[str, list[dict[str, Any]]]:
    result = {DEVELOPMENT: [], VALIDATION: [], OUTSIDE_FROZEN_WINDOWS: []}
    for source in rows:
        row = dict(source)
        value = str(row.get(date_field, ""))
        if not value:
            result[OUTSIDE_FROZEN_WINDOWS].append(row)
            continue
        result[partition_label(value, config)].append(row)
    return result


def resolve_development_score_rows(data_dir: Path, config: TemporalResearchConfig) -> list[dict[str, str]]:
    rows = read_gzip_csv(resolve_current_strategy_score_dataset(data_dir))
    return partition_rows(rows, date_field=config.score_date_field, config=config)[DEVELOPMENT]


def resolve_validation_score_rows(data_dir: Path, config: TemporalResearchConfig) -> list[dict[str, str]]:
    rows = read_gzip_csv(resolve_current_strategy_score_dataset(data_dir))
    return partition_rows(rows, date_field=config.score_date_field, config=config)[VALIDATION]


def resolve_development_outcome_rows(data_dir: Path, config: TemporalResearchConfig) -> list[dict[str, str]]:
    rows = read_gzip_csv(resolve_current_strategy_outcome_dataset(data_dir))
    return partition_rows(rows, date_field=config.outcome_date_field, config=config)[DEVELOPMENT]


def resolve_validation_outcome_rows(
    data_dir: Path,
    config: TemporalResearchConfig,
    *,
    access_scope: str = STRUCTURAL_METADATA,
    guard: ValidationAccessGuard | None = None,
    artifact: ExperimentFreezeArtifact | None = None,
    authorization: ValidationAuthorization | None = None,
) -> list[dict[str, str]]:
    if access_scope == PERFORMANCE_ACCESS:
        if guard is None or artifact is None:
            raise PermissionError("Guard and frozen experiment are required for validation performance access")
        guard.require_validation_access(artifact, authorization)
    rows = read_gzip_csv(resolve_current_strategy_outcome_dataset(data_dir))
    selected = partition_rows(rows, date_field=config.outcome_date_field, config=config)[VALIDATION]
    return controlled_validation_rows(
        selected,
        access_scope=access_scope,
        guard=guard,
        artifact=artifact,
        authorization=authorization,
    )


def resolve_development_backtest_source_rows(
    data_dir: Path, config: TemporalResearchConfig
) -> list[dict[str, str]]:
    rows, _ = load_frozen_opportunities(resolve_current_strategy_outcome_dataset(data_dir))
    return partition_rows(rows, date_field=config.backtest_source_date_field, config=config)[DEVELOPMENT]


def resolve_validation_backtest_source_rows(
    data_dir: Path,
    config: TemporalResearchConfig,
    *,
    access_scope: str = STRUCTURAL_METADATA,
    guard: ValidationAccessGuard | None = None,
    artifact: ExperimentFreezeArtifact | None = None,
    authorization: ValidationAuthorization | None = None,
) -> list[dict[str, str]]:
    if access_scope == PERFORMANCE_ACCESS:
        if guard is None or artifact is None:
            raise PermissionError("Guard and frozen experiment are required for validation performance access")
        guard.require_validation_access(artifact, authorization)
    rows, _ = load_frozen_opportunities(resolve_current_strategy_outcome_dataset(data_dir))
    selected = partition_rows(rows, date_field=config.backtest_source_date_field, config=config)[VALIDATION]
    return controlled_validation_rows(
        selected,
        access_scope=access_scope,
        guard=guard,
        artifact=artifact,
        authorization=authorization,
    )


def controlled_validation_rows(
    rows: Sequence[dict[str, str]],
    *,
    access_scope: str,
    guard: ValidationAccessGuard | None,
    artifact: ExperimentFreezeArtifact | None,
    authorization: ValidationAuthorization | None,
) -> list[dict[str, str]]:
    if access_scope == STRUCTURAL_METADATA:
        return [structural_projection(row) for row in rows]
    if access_scope != PERFORMANCE_ACCESS:
        raise ValueError(f"Unsupported validation access scope: {access_scope}")
    if guard is None or artifact is None:
        raise PermissionError("Guard and frozen experiment are required for validation performance access")
    guard.require_validation_access(artifact, authorization)
    return [dict(row) for row in rows]


def structural_projection(row: dict[str, Any]) -> dict[str, str]:
    return {field: str(row.get(field, "")) for field in VALIDATION_STRUCTURAL_FIELDS if field in row}


def row_identity(row: dict[str, Any], *, layer: str, date_field: str, version_field: str) -> dict[str, str]:
    return {
        "layer": layer,
        "decision_date": str(row.get(date_field, "")),
        "symbol": str(row.get("symbol", "")),
        "isin": str(row.get("isin", "")),
        "source_version": str(row.get(version_field, "")),
    }


def row_identity_fingerprint(
    rows: Sequence[dict[str, Any]],
    *,
    layer: str,
    date_field: str,
    version_field: str,
) -> str:
    identities = [
        row_identity(row, layer=layer, date_field=date_field, version_field=version_field)
        for row in rows
    ]
    identities.sort(
        key=lambda row: (
            row["decision_date"],
            row["symbol"],
            row["isin"],
            row["source_version"],
        )
    )
    return canonical_hash(identities)


def crosses_validation_boundary(row: dict[str, Any], config: TemporalResearchConfig) -> bool:
    decision = str(row.get("decision_date", ""))
    if not decision or partition_label(decision, config) != DEVELOPMENT:
        return False
    observed_dates = [str(row.get("next_session_date", ""))]
    observed_dates.extend(str(row.get(f"session_date_{index}", "")) for index in range(1, 5))
    return any(value and value >= config.validation_start.isoformat() for value in observed_dates)


def resolve_validation_terminal_date(data_dir: Path) -> date:
    rows, _ = load_frozen_opportunities(resolve_current_strategy_outcome_dataset(data_dir))
    return max(parse_iso_date(row["decision_date"]) for row in rows)


def verify_terminal_date_freeze(data_dir: Path, config: TemporalResearchConfig) -> date:
    observed = resolve_validation_terminal_date(data_dir)
    if observed != config.validation_terminal_date:
        raise ValueError(
            "Frozen validation terminal date changed; create VALIDATION_WINDOW_V2 instead of extending V1"
        )
    return observed


def development_run_mode() -> str:
    return DEVELOPMENT_RUN
