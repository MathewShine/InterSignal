from __future__ import annotations

from pathlib import Path

from app.risk.risk_baseline import audit_v1_references, build_baseline_promotion_report, write_baseline_promotion_report
from app.risk.risk_config import (
    ACTIVE_FORWARD_BASELINE,
    CURRENT_RISK_STRUCTURE_CONFIG_HASH,
    CURRENT_RISK_STRUCTURE_VERSION,
    HISTORICAL_SUPERSEDED,
    RISK_STRUCTURE_V1_DATASET_HASH,
    RISK_STRUCTURE_V1_1_DATASET_HASH,
    RISK_STRUCTURE_V1_1_VERSION,
    RISK_STRUCTURE_VERSION,
    RiskStructureV11Config,
    get_current_risk_structure_version,
    normalize_risk_structure_version,
    resolve_current_risk_structure_dataset,
    resolve_risk_structure_dataset,
    risk_structure_version_status,
)
from app.strategy.momentum_candidates import file_sha256
from scripts.build_risk_structures import build_parser
from app.risk.risk_structurer import RiskStructureEngineConfig, build_risk_structures

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"


def test_current_version_and_status_resolve_to_v1_1() -> None:
    assert CURRENT_RISK_STRUCTURE_VERSION == RISK_STRUCTURE_V1_1_VERSION
    assert get_current_risk_structure_version() == RISK_STRUCTURE_V1_1_VERSION
    assert risk_structure_version_status(RISK_STRUCTURE_V1_1_VERSION) == ACTIVE_FORWARD_BASELINE
    assert risk_structure_version_status(RISK_STRUCTURE_VERSION) == HISTORICAL_SUPERSEDED


def test_generic_build_cli_defaults_to_current_v1_1() -> None:
    args = build_parser().parse_args([])
    assert args.version == "current"
    assert normalize_risk_structure_version(args.version) == RISK_STRUCTURE_V1_1_VERSION


def test_legacy_builder_rejects_current_config_before_writing(tmp_path: Path) -> None:
    try:
        build_risk_structures(
            config=RiskStructureEngineConfig(data_dir=tmp_path, risk_config=RiskStructureV11Config())
        )
    except ValueError as exc:
        assert "legacy builder" in str(exc)
    else:
        raise AssertionError("Legacy V1 builder accepted the current V1.1 config")


def test_current_and_historical_dataset_resolution() -> None:
    current_path = resolve_current_risk_structure_dataset(DATA_DIR)
    historical_path = resolve_risk_structure_dataset(DATA_DIR, "v1")
    assert current_path.as_posix().endswith("risk_structures/daily/v1_1/risk_structures_v1_1.csv.gz")
    assert historical_path.as_posix().endswith("risk_structures/daily/v1/risk_structures_v1.csv.gz")
    assert resolve_risk_structure_dataset(DATA_DIR) == current_path
    assert current_path != historical_path


def test_frozen_dataset_and_config_hashes_match() -> None:
    assert file_sha256(resolve_risk_structure_dataset(DATA_DIR, "v1")) == RISK_STRUCTURE_V1_DATASET_HASH
    assert file_sha256(resolve_current_risk_structure_dataset(DATA_DIR)) == RISK_STRUCTURE_V1_1_DATASET_HASH
    assert RiskStructureV11Config().config_hash() == CURRENT_RISK_STRUCTURE_CONFIG_HASH


def test_reference_audit_has_no_forward_v1_consumers() -> None:
    audit = audit_v1_references(REPO_ROOT)
    assert audit["total_references"] > 0
    assert audit["unintended_forward_references"] == []


def test_promotion_report_generation(tmp_path: Path) -> None:
    report = build_baseline_promotion_report(
        repo_root=REPO_ROOT,
        tests_passed=True,
        frontend_build_passed=True,
    )
    output_path = tmp_path / "risk_structure_baseline_promotion.json"
    write_baseline_promotion_report(output_path, report)

    assert report["promotion_status"] == "PROMOTED_CURRENT_BASELINE"
    assert report["current_dataset_validation"]["final_score_status_violations"] == 0
    assert report["current_dataset_validation"]["signal_status_violations"] == 0
    assert output_path.exists()
