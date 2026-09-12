from __future__ import annotations

import csv
import gzip
import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.research.temporal_validation.config import (
    AUTHORIZED_TO_EVALUATE,
    DEFAULT_TEMPORAL_CONFIG,
    DEVELOPMENT_RUN,
    DEVELOPMENT_WINDOW_VERSION,
    EVALUATED,
    EXPECTED_HARNESS_CONFIG_HASH,
    PERFORMANCE_ACCESS,
    REPRODUCTION_RUN,
    SEALED,
    STRUCTURAL_METADATA,
    TEMPORAL_RESEARCH_HARNESS_VERSION,
    TEMPORAL_VALIDATION_PROTOCOL_VERSION,
    VALIDATION_RUN,
    classify_sample_size,
)
from app.research.temporal_validation.guard import ValidationAccessError, ValidationAccessGuard
from app.research.temporal_validation.harness import (
    EXPECTED_MANIFEST_HASH,
    FORBIDDEN_HOLDOUT_PERFORMANCE_FIELDS,
    REPORT_NAMES,
    build_temporal_validation_harness,
    continuous_standardized_difference,
    forbidden_key_paths,
    synthetic_freeze_artifact,
)
from app.research.temporal_validation.models import ExperimentFreezeArtifact, experiment_freeze_schema
from app.research.temporal_validation.partition import (
    DEVELOPMENT,
    OUTSIDE_FROZEN_WINDOWS,
    VALIDATION,
    crosses_validation_boundary,
    partition_label,
    partition_rows,
    resolve_development_backtest_source_rows,
    resolve_development_outcome_rows,
    resolve_development_score_rows,
    resolve_validation_backtest_source_rows,
    resolve_validation_outcome_rows,
    resolve_validation_score_rows,
    row_identity_fingerprint,
    verify_terminal_date_freeze,
)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def generated_report(repo_root: Path) -> dict[str, object]:
    return json.loads(
        (repo_root / "data/reports/temporal_validation_v1_summary.json").read_text(
            encoding="utf-8"
        )
    )


def freeze_artifact() -> ExperimentFreezeArtifact:
    return synthetic_freeze_artifact()


def write_gzip_fixture(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def test_versions_and_initial_state_are_frozen() -> None:
    assert TEMPORAL_RESEARCH_HARNESS_VERSION == "TEMPORAL_RESEARCH_HARNESS_V1"
    assert TEMPORAL_VALIDATION_PROTOCOL_VERSION == "TEMPORAL_VALIDATION_PROTOCOL_V1"
    assert DEFAULT_TEMPORAL_CONFIG.validation_state == SEALED


def test_harness_config_hash_is_frozen() -> None:
    assert DEFAULT_TEMPORAL_CONFIG.config_hash() == EXPECTED_HARNESS_CONFIG_HASH
    assert len(EXPECTED_HARNESS_CONFIG_HASH) == 64


def test_window_definitions_and_decision_date_boundaries() -> None:
    config = DEFAULT_TEMPORAL_CONFIG
    assert config.development_start.isoformat() == "2022-01-01"
    assert config.development_end.isoformat() == "2024-12-31"
    assert config.validation_start.isoformat() == "2025-01-01"
    assert config.validation_terminal_date.isoformat() == "2026-08-13"
    assert partition_label("2024-12-31", config) == DEVELOPMENT
    assert partition_label("2025-01-01", config) == VALIDATION
    assert partition_label("2026-08-14", config) == OUTSIDE_FROZEN_WINDOWS


def test_terminal_date_resolves_to_frozen_source_pool(repo_root: Path) -> None:
    assert verify_terminal_date_freeze(repo_root / "data", DEFAULT_TEMPORAL_CONFIG).isoformat() == "2026-08-13"


def test_terminal_date_silent_extension_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.research.temporal_validation.partition.resolve_validation_terminal_date",
        lambda _data_dir: DEFAULT_TEMPORAL_CONFIG.validation_terminal_date.replace(day=14),
    )
    with pytest.raises(ValueError, match="VALIDATION_WINDOW_V2"):
        verify_terminal_date_freeze(Path("unused"), DEFAULT_TEMPORAL_CONFIG)


def test_partition_rows_uses_decision_date_not_exit_date() -> None:
    rows = [
        {"decision_date": "2024-12-31", "exit_date": "2025-01-06"},
        {"decision_date": "2025-01-02", "exit_date": "2025-01-06"},
    ]
    partitions = partition_rows(rows, date_field="decision_date", config=DEFAULT_TEMPORAL_CONFIG)
    assert len(partitions[DEVELOPMENT]) == 1
    assert len(partitions[VALIDATION]) == 1


def test_cross_boundary_flag_uses_future_session_without_reassignment() -> None:
    row = {
        "decision_date": "2024-12-31",
        "next_session_date": "2025-01-01",
        "session_date_4": "2025-01-06",
    }
    assert crosses_validation_boundary(row, DEFAULT_TEMPORAL_CONFIG)
    assert partition_label(row["decision_date"], DEFAULT_TEMPORAL_CONFIG) == DEVELOPMENT


def test_row_fingerprint_is_order_independent_and_identity_only() -> None:
    rows = [
        {"decision_date": "2022-01-03", "symbol": "A", "isin": "I1", "version": "V1", "mfe_r_4": "9"},
        {"decision_date": "2022-01-04", "symbol": "B", "isin": "I2", "version": "V1", "mfe_r_4": "1"},
    ]
    first = row_identity_fingerprint(rows, layer="L", date_field="decision_date", version_field="version")
    changed_outcomes = [dict(row, mfe_r_4="999") for row in reversed(rows)]
    second = row_identity_fingerprint(changed_outcomes, layer="L", date_field="decision_date", version_field="version")
    assert first == second


def test_score_resolvers_partition_synthetic_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "scores.csv.gz"
    write_gzip_fixture(
        path,
        [
            {"trading_date": "2024-12-31", "symbol": "A", "isin": "I", "score_version": "V1"},
            {"trading_date": "2025-01-02", "symbol": "B", "isin": "J", "score_version": "V1"},
        ],
    )
    monkeypatch.setattr(
        "app.research.temporal_validation.partition.resolve_current_strategy_score_dataset",
        lambda _data_dir: path,
    )
    assert len(resolve_development_score_rows(tmp_path, DEFAULT_TEMPORAL_CONFIG)) == 1
    assert len(resolve_validation_score_rows(tmp_path, DEFAULT_TEMPORAL_CONFIG)) == 1


def test_outcome_resolvers_redact_sealed_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "outcomes.csv.gz"
    write_gzip_fixture(
        path,
        [
            {"decision_date": "2024-12-31", "symbol": "A", "isin": "I", "outcome_version": "V1", "mfe_r_4": "1"},
            {"decision_date": "2025-01-02", "symbol": "B", "isin": "J", "outcome_version": "V1", "mfe_r_4": "9"},
        ],
    )
    monkeypatch.setattr(
        "app.research.temporal_validation.partition.resolve_current_strategy_outcome_dataset",
        lambda _data_dir: path,
    )
    development = resolve_development_outcome_rows(tmp_path, DEFAULT_TEMPORAL_CONFIG)
    validation = resolve_validation_outcome_rows(tmp_path, DEFAULT_TEMPORAL_CONFIG)
    assert development[0]["mfe_r_4"] == "1"
    assert "mfe_r_4" not in validation[0]


def test_performance_access_is_denied_before_loading_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.research.temporal_validation.partition.read_gzip_csv",
        lambda _path: (_ for _ in ()).throw(AssertionError("sealed guard must run first")),
    )
    with pytest.raises(ValidationAccessError, match="SEALED"):
        resolve_validation_outcome_rows(
            Path("unused"),
            DEFAULT_TEMPORAL_CONFIG,
            access_scope=PERFORMANCE_ACCESS,
            guard=ValidationAccessGuard(),
            artifact=freeze_artifact(),
        )


def test_backtest_source_resolvers_partition_and_redact(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"decision_date": "2024-12-30", "symbol": "A", "isin": "I", "outcome_version": "V1", "mfe_r_4": "1"},
        {"decision_date": "2025-01-02", "symbol": "B", "isin": "J", "outcome_version": "V1", "mfe_r_4": "9"},
    ]
    monkeypatch.setattr(
        "app.research.temporal_validation.partition.load_frozen_opportunities",
        lambda _path: (rows, {}),
    )
    monkeypatch.setattr(
        "app.research.temporal_validation.partition.resolve_current_strategy_outcome_dataset",
        lambda _data_dir: Path("unused"),
    )
    development = resolve_development_backtest_source_rows(Path("unused"), DEFAULT_TEMPORAL_CONFIG)
    validation = resolve_validation_backtest_source_rows(Path("unused"), DEFAULT_TEMPORAL_CONFIG)
    assert development[0]["mfe_r_4"] == "1"
    assert "mfe_r_4" not in validation[0]


def test_experiment_freeze_hash_is_deterministic() -> None:
    artifact = freeze_artifact()
    artifact.validate()
    assert artifact.development_freeze_hash() == artifact.development_freeze_hash()
    assert len(artifact.parameter_hash()) == 64


def test_parameter_mutation_changes_parameter_and_freeze_hash() -> None:
    artifact = freeze_artifact()
    changed = artifact.with_parameters({"fixture": "CHANGED"})
    assert changed.parameter_hash() != artifact.parameter_hash()
    assert changed.development_freeze_hash() != artifact.development_freeze_hash()


def test_freeze_artifact_cannot_self_authorize() -> None:
    with pytest.raises(ValueError, match="self-authorize"):
        replace(freeze_artifact(), validation_authorized=True).validate()


def test_authorization_requires_explicit_user_approval() -> None:
    artifact = freeze_artifact()
    guard = ValidationAccessGuard()
    with pytest.raises(ValidationAccessError, match="Explicit"):
        guard.authorize_validation(
            artifact,
            supplied_freeze_hash=artifact.development_freeze_hash(),
            explicit_user_authorized=False,
            authorization_reference="fixture",
        )
    assert guard.state == SEALED


def test_authorization_rejects_wrong_freeze_hash() -> None:
    artifact = freeze_artifact()
    with pytest.raises(ValidationAccessError, match="hash mismatch"):
        ValidationAccessGuard().authorize_validation(
            artifact,
            supplied_freeze_hash="f" * 64,
            explicit_user_authorized=True,
            authorization_reference="fixture",
        )


def test_synthetic_authorized_validation_path_and_one_shot_rule() -> None:
    artifact = freeze_artifact()
    guard = ValidationAccessGuard()
    authorization = guard.authorize_validation(
        artifact,
        supplied_freeze_hash=artifact.development_freeze_hash(),
        explicit_user_authorized=True,
        authorization_reference="SYNTHETIC_TEST_ONLY",
    )
    assert guard.state == AUTHORIZED_TO_EVALUATE
    with pytest.raises(ValidationAccessError, match="active authorized run"):
        guard.require_validation_access(artifact, authorization)
    guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)
    guard.require_validation_access(artifact, authorization)
    assert guard.validation_run_count == 1
    guard.record_validation_result("a" * 64)
    assert guard.state == EVALUATED
    with pytest.raises(ValidationAccessError):
        guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)


def test_authorized_validation_resolver_path_works_only_during_active_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        {
            "decision_date": "2025-01-02",
            "symbol": "FIXTURE",
            "isin": "TEST",
            "outcome_version": "V1",
            "mfe_r_4": "9",
        }
    ]
    monkeypatch.setattr(
        "app.research.temporal_validation.partition.load_frozen_opportunities",
        lambda _path: (rows, {}),
    )
    monkeypatch.setattr(
        "app.research.temporal_validation.partition.resolve_current_strategy_outcome_dataset",
        lambda _data_dir: Path("unused"),
    )
    artifact = freeze_artifact()
    guard = ValidationAccessGuard()
    authorization = guard.authorize_validation(
        artifact,
        supplied_freeze_hash=artifact.development_freeze_hash(),
        explicit_user_authorized=True,
        authorization_reference="SYNTHETIC_TEST_ONLY",
    )
    with pytest.raises(ValidationAccessError):
        resolve_validation_backtest_source_rows(
            Path("unused"),
            DEFAULT_TEMPORAL_CONFIG,
            access_scope=PERFORMANCE_ACCESS,
            guard=guard,
            artifact=artifact,
            authorization=authorization,
        )
    guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)
    resolved = resolve_validation_backtest_source_rows(
        Path("unused"),
        DEFAULT_TEMPORAL_CONFIG,
        access_scope=PERFORMANCE_ACCESS,
        guard=guard,
        artifact=artifact,
        authorization=authorization,
    )
    assert resolved[0]["mfe_r_4"] == "9"


def test_development_run_needs_no_validation_authorization() -> None:
    guard = ValidationAccessGuard()
    guard.begin_run(DEVELOPMENT_RUN)
    assert guard.state == SEALED
    assert guard.validation_run_count == 0


def test_reproduction_requires_exact_frozen_definition_and_result_hash() -> None:
    artifact = freeze_artifact()
    guard = ValidationAccessGuard()
    authorization = guard.authorize_validation(
        artifact,
        supplied_freeze_hash=artifact.development_freeze_hash(),
        explicit_user_authorized=True,
        authorization_reference="SYNTHETIC_TEST_ONLY",
    )
    guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)
    guard.record_validation_result("b" * 64)
    guard.begin_run(REPRODUCTION_RUN, artifact=artifact, expected_result_hash="b" * 64)
    with pytest.raises(ValidationAccessError):
        guard.begin_run(REPRODUCTION_RUN, artifact=artifact, expected_result_hash="c" * 64)
    with pytest.raises(ValidationAccessError):
        guard.begin_run(
            REPRODUCTION_RUN,
            artifact=artifact.with_parameters({"fixture": "MUTATED"}),
            expected_result_hash="b" * 64,
        )


def test_validation_result_is_immutable() -> None:
    artifact = freeze_artifact()
    guard = ValidationAccessGuard()
    authorization = guard.authorize_validation(
        artifact,
        supplied_freeze_hash=artifact.development_freeze_hash(),
        explicit_user_authorized=True,
        authorization_reference="SYNTHETIC_TEST_ONLY",
    )
    guard.begin_run(VALIDATION_RUN, artifact=artifact, authorization=authorization)
    guard.record_validation_result("d" * 64)
    with pytest.raises(ValidationAccessError):
        guard.record_validation_result("e" * 64)


def test_experiment_freeze_schema_requires_cost_and_hashes() -> None:
    schema = experiment_freeze_schema()
    assert schema["properties"]["cost_model"]["const"] == "INDIA_EQUITY_COST_MODEL_V1"
    assert "development_freeze_hash" in schema["required"]
    assert schema["governance"]["parameter_change_requires_new_version"] is True


def test_independent_window_starting_capital_is_not_carried_forward() -> None:
    assert DEFAULT_TEMPORAL_CONFIG.development_initial_capital_rupees == 100000
    assert DEFAULT_TEMPORAL_CONFIG.validation_initial_capital_rupees == 100000


def test_sample_adequacy_thresholds() -> None:
    assert classify_sample_size(29) == "NOT_INFERENTIAL"
    assert classify_sample_size(30) == "SMALL"
    assert classify_sample_size(100) == "LIMITED"
    assert classify_sample_size(300) == "ADEQUATE_FOR_DESCRIPTION"


def test_data_shift_standardization_is_descriptive() -> None:
    assert continuous_standardized_difference([1, 2, 3], [1, 2, 3]) == 0
    assert continuous_standardized_difference([1, 1], [2, 2]) == 0


def test_forbidden_holdout_performance_fields_are_detected() -> None:
    violations = forbidden_key_paths({"safe": {"gross_pnl": "1"}})
    assert violations == ["safe.gross_pnl"]
    assert "mfe" in FORBIDDEN_HOLDOUT_PERFORMANCE_FIELDS


def test_generated_manifest_and_population(generated_report: dict[str, object]) -> None:
    report = generated_report
    assert report["manifest"]["manifest_hash"] == EXPECTED_MANIFEST_HASH
    assert report["population"]["development"]["source_opportunities"] == 2068
    assert report["population"]["validation"]["source_opportunities"] == 1224
    assert report["population"]["development"]["admitted_full_baseline_trades"] == 478
    assert report["population"]["validation"]["structural_expected_baseline_trades"] == 246


def test_development_baseline_reference_only(generated_report: dict[str, object]) -> None:
    result = generated_report["development_baseline_reference"]
    assert result["label"] == "BASELINE_REFERENCE_ONLY"
    assert result["starting_equity"] == "100000"
    assert result["entered_trades"] == 481
    assert result["all_invariants_valid"] is True
    assert result["tuning_performed"] is False


def test_validation_no_peek_and_sealed_state(generated_report: dict[str, object]) -> None:
    governance = generated_report["validation_governance"]
    assert governance["validation_state"] == SEALED
    assert governance["validation_run_count"] == 0
    assert governance["validation_performance_exposed"] is False
    assert governance["holdout_performance_report_generated"] is False
    assert generated_report["no_peek"]["violation_count"] == 0


def test_contamination_register_is_explicit(generated_report: dict[str, object]) -> None:
    rows = generated_report["contamination_register"]
    assert len(rows) == 11
    assert all(row["validation_period_touched"] for row in rows)
    assert all(row["parameter_tuned"] is False for row in rows)


def test_input_only_shift_and_holdout_sample_classifications(generated_report: dict[str, object]) -> None:
    assert generated_report["distribution_shift"]["basis"] == "INPUT_DISTRIBUTIONS_ONLY_NO_OUTCOMES"
    assert generated_report["classifications"]["TEMPORAL_DATA_SHIFT_RESULT"] in {"LOW", "MODERATE", "HIGH"}
    assert generated_report["classifications"]["HOLDOUT_SAMPLE_RESULT"] == "LIMITED"


def test_future_validation_requires_nonzero_frozen_costs(generated_report: dict[str, object]) -> None:
    contract = generated_report["cost_aware_validation"]
    assert contract["required_cost_model"] == "INDIA_EQUITY_COST_MODEL_V1"
    assert contract["nonzero_cost_slippage_scenario_required"] is True
    assert contract["zero_cost_only_is_sufficient"] is False


def test_live_and_small_capital_readiness_remain_false(generated_report: dict[str, object]) -> None:
    assert generated_report["readiness"]["LIVE_TRADING_READY"] is False
    assert generated_report["readiness"]["SMALL_CAPITAL_LIVE_READY"] is False


def test_baseline_diagnostic_and_cost_registries_are_immutable(generated_report: dict[str, object]) -> None:
    assert generated_report["regression"]["all_unchanged"] is True
    assert all(generated_report["regression"]["expected_hash_checks"].values())
    assert generated_report["diagnostic_registry_regression"]["unchanged"] is True
    assert generated_report["cost_registry_regression"]["unchanged"] is True
    assert generated_report["baseline_mutation_violations"] == 0


def test_pilot_and_reproducibility(generated_report: dict[str, object]) -> None:
    assert generated_report["pilot"]["required_case_count"] == 14
    assert generated_report["pilot"]["passed_case_count"] == 14
    assert generated_report["pilot"]["passed"] is True
    assert generated_report["reproducibility"]["match"] is True


def test_all_machine_reports_are_generated(repo_root: Path, generated_report: dict[str, object]) -> None:
    for name in REPORT_NAMES:
        path = repo_root / "data/reports" / name
        assert path.exists()
        assert path.stat().st_size > 0
    holdout_root = repo_root / "data/research/temporal_validation/v1/holdout_metadata"
    assert [path.name for path in holdout_root.glob("*")] == ["validation_blind_summary_v1.json"]
    payload = json.loads((holdout_root / "validation_blind_summary_v1.json").read_text(encoding="utf-8"))
    assert forbidden_key_paths(payload) == []
