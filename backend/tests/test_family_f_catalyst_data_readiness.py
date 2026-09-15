from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from app.research.strategy.family_a_momentum import file_sha256, read_csv
from app.research.strategy.family_f_catalyst_data_readiness import (
    CATEGORY_READINESS_CLASSIFICATIONS,
    COMMAND_PROFILE,
    COMMAND_VERSION,
    EXPECTED_FAMILY_E_CLOSURE_HASH,
    EXPECTED_MILESTONE_COMMIT,
    FAMILY_F_DATA_READINESS,
    FAMILY_F_PREREGISTRATION_READINESS,
    FAMILY_F_ROADMAP_STATUS,
    FAMILY_F_STATUS,
    HISTORICAL_EARNINGS_SURPRISE_READINESS,
    LICENSE_STATES,
    LINKAGE_CLASSIFICATIONS,
    MANIFEST_VERSION,
    MARKET_TIMING_BUCKETS,
    NORMALIZED_SCHEMA_FIELDS,
    REPORT_NAMES,
    SOURCE_RELIABILITY_TIERS,
    TIMESTAMP_CLASSIFICATIONS,
    audit_local_coverage,
    verify_family_e_closure,
)
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_ROOT = (
    REPO_ROOT / "data/research/strategy_families/family_f/data_readiness/v1"
)
REPORT_ROOT = REPO_ROOT / "data/reports"
SUMMARY_PATH = REPORT_ROOT / REPORT_NAMES[0]
MANIFEST_PATH = AUDIT_ROOT / "manifests/family_f_data_readiness_manifest_v1.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def test_command_identity_and_checkpoint_are_frozen() -> None:
    assert COMMAND_VERSION == "FAMILY_F_CATALYST_DATA_READINESS_V1"
    assert COMMAND_PROFILE == "POINT_IN_TIME_CATALYST_SOURCE_AUDIT_V1"
    assert MANIFEST_VERSION == "FAMILY_F_DATA_READINESS_MANIFEST_V1"
    assert EXPECTED_MILESTONE_COMMIT == (
        "c2f7534761e31f53376a6d9d1275aacd2eddc985"
    )
    assert _summary()["baseline"]["milestone_commit"] == EXPECTED_MILESTONE_COMMIT


def test_family_e_closure_hash_remains_exact() -> None:
    verification = verify_family_e_closure(REPO_ROOT)
    assert verification["status"] == "VERIFIED"
    assert verification["family_e_closure_hash"] == EXPECTED_FAMILY_E_CLOSURE_HASH
    assert all(verification["checks"].values())


def test_family_f_is_data_readiness_only_and_not_preregistered() -> None:
    summary = _summary()
    assert FAMILY_F_STATUS == "DATA_READINESS_ONLY"
    assert FAMILY_F_ROADMAP_STATUS == "ACTIVE_DATA_READINESS"
    assert FAMILY_F_DATA_READINESS == "SOURCE_ACQUISITION_REQUIRED"
    assert FAMILY_F_PREREGISTRATION_READINESS == "NO"
    assert summary["family_status"] == FAMILY_F_STATUS
    assert summary["FAMILY_F_DATA_READINESS"] == FAMILY_F_DATA_READINESS
    assert (
        summary["FAMILY_F_PREREGISTRATION_READINESS"]
        == FAMILY_F_PREREGISTRATION_READINESS
    )


def test_taxonomy_has_all_seventeen_categories_without_weights() -> None:
    document = _json(AUDIT_ROOT / "taxonomy/catalyst_taxonomy_v1.json")
    rows = document["categories"]
    assert document["category_count"] == 17
    assert [row["taxonomy_code"] for row in rows] == list("ABCDEFGHIJKLMNOPQ")
    assert document["weights_defined"] is False
    assert all(row["strategy_weight"] == "NOT_DEFINED" for row in rows)
    assert all(row["readiness"] in CATEGORY_READINESS_CLASSIFICATIONS for row in rows)


def test_all_required_classification_vocabularies_are_frozen() -> None:
    manifest = _json(MANIFEST_PATH)
    values = manifest["classifications"]
    assert tuple(values["timestamp"]) == TIMESTAMP_CLASSIFICATIONS
    assert tuple(values["market_timing"]) == MARKET_TIMING_BUCKETS
    assert tuple(values["linkage"]) == LINKAGE_CLASSIFICATIONS
    assert tuple(values["category_readiness"]) == CATEGORY_READINESS_CLASSIFICATIONS
    assert tuple(values["licensing"]) == LICENSE_STATES
    assert tuple(values["source_reliability"]) == SOURCE_RELIABILITY_TIERS


def test_timestamp_policy_rejects_date_only_same_day_causality() -> None:
    schema = _json(AUDIT_ROOT / "schema/normalized_catalyst_schema_v1.json")
    assert schema["timestamp_policy"]["timezone"] == "Asia/Kolkata"
    assert schema["timestamp_policy"]["accepted_for_normal_future_research"] == [
        "EXACT_EXCHANGE_TIMESTAMP",
        "RELIABLE_PUBLICATION_TIMESTAMP",
    ]
    assert schema["timestamp_policy"]["date_only_same_day_usable"] is False


def test_normalized_schema_is_design_only_and_exact() -> None:
    schema = _json(AUDIT_ROOT / "schema/normalized_catalyst_schema_v1.json")
    assert tuple(schema["fields"]) == NORMALIZED_SCHEMA_FIELDS
    assert len(schema["fields"]) == 20
    assert schema["status"] == "DESIGN_ONLY_NO_DB_MIGRATION"
    assert schema["provenance_policy"] == (
        "NO_NORMALIZED_EVENT_WITHOUT_IMMUTABLE_RAW_SOURCE_LINEAGE"
    )
    assert schema["dedup_keys"] == [
        ["source", "source_document_id"],
        ["source", "isin_or_symbol", "published_at", "event_category"],
    ]


def test_source_capability_matrix_contains_required_columns() -> None:
    rows = _json(AUDIT_ROOT / "source_inventory/source_inventory_v1.json")["sources"]
    required = {
        "source_name",
        "source_type",
        "purpose",
        "official_or_secondary",
        "historical_available",
        "earliest_date",
        "latest_date",
        "timestamp_precision",
        "publication_timestamp_available",
        "event_category",
        "symbol_available",
        "isin_available",
        "company_name_available",
        "document_id_available",
        "revision_history_available",
        "raw_payload_available",
        "raw_storage",
        "normalization_layer",
        "rate_limits",
        "license_restrictions",
        "licensing_notes",
        "automation_feasibility",
        "research_suitability",
    }
    assert len(rows) >= 12
    assert all(required <= set(row) for row in rows)
    assert {row["source_name"] for row in rows} >= {
        "NSE_CORPORATE_ACTIONS_LOCAL",
        "NIFTY_INDEX_NOTICES_LOCAL",
        "NSE_CORPORATE_FILINGS_ANNOUNCEMENTS",
        "NSE_FINANCIAL_RESULTS_XBRL",
        "BSE_CORPORATE_ANNOUNCEMENTS",
        "SEBI_ORDERS_AND_ACTIONS",
        "ICRA_RATING_RATIONALES",
        "CRISIL_RATING_RATIONALES",
        "LICENSED_HISTORICAL_CONSENSUS",
    }


def test_local_coverage_is_recomputed_from_existing_datasets() -> None:
    stored = _json(AUDIT_ROOT / "coverage/local_coverage_v1.json")
    assert stored == audit_local_coverage(REPO_ROOT)
    corporate = stored["corporate_actions"]
    index = stored["index_membership_notices"]
    assert corporate["all_exchange_rows_in_target_window"] == 7763
    assert corporate["nifty500_rows_on_effective_date"] == 2261
    assert corporate["unique_symbols"] == 536
    assert corporate["publication_timestamp_count"] == 0
    assert corporate["timestamp_quality"]["DATE_ONLY"] == 2261
    assert corporate["source_isin_count"] == 0
    assert corporate["canonical_identity_isin_enriched_count"] == 1805
    assert index["event_count"] == 336
    assert index["unique_symbols"] == 264
    assert index["source_isin_count"] == 127
    assert index["timestamp_quality"]["DATE_ONLY"] == 336


def test_actual_counts_are_only_reported_for_accessible_data() -> None:
    rows = _json(AUDIT_ROOT / "taxonomy/catalyst_taxonomy_v1.json")["categories"]
    by_code = {row["taxonomy_code"]: row for row in rows}
    assert by_code["I"]["actual_accessible_count"] == 1855
    assert by_code["J"]["actual_accessible_count"] == 80
    assert by_code["M"]["actual_accessible_count"] == 336
    assert by_code["A"]["actual_accessible_count"] == "NOT_RETRIEVED"
    assert by_code["N"]["actual_accessible_count"] == "NOT_RETRIEVED"


def test_consensus_and_category_readiness_are_conservative() -> None:
    summary = _summary()
    assert HISTORICAL_EARNINGS_SURPRISE_READINESS == "NOT_AVAILABLE"
    assert (
        summary["consensus"]["HISTORICAL_EARNINGS_SURPRISE_READINESS"]
        == HISTORICAL_EARNINGS_SURPRISE_READINESS
    )
    readiness = summary["category_readiness"]
    assert "READY" not in readiness.values()
    assert readiness["FINANCIAL_RESULTS"] == "SOURCE_AVAILABLE_NOT_INGESTED"
    assert readiness["EARNINGS_SURPRISE_MATERIAL_CHANGE"] == "NOT_AVAILABLE"
    assert readiness["INDEX_INCLUSION_EXCLUSION"] == "TIMESTAMP_INSUFFICIENT"
    assert readiness["DIVIDENDS"] == "TIMESTAMP_INSUFFICIENT"


def test_licensing_has_no_purchase_or_connection() -> None:
    document = _json(AUDIT_ROOT / "licensing/licensing_assessment_v1.json")
    assert document["required_now"] == []
    assert document["potentially_required_later"]
    assert document["purchase_or_connection_executed"] is False
    assert all(row["license_state"] in LICENSE_STATES for row in document["sources"])
    assert all(
        row["current_action"] == "NO_PURCHASE_OR_CONNECTION_AUTHORIZED"
        for row in document["sources"]
    )


def test_acquisition_and_pilot_plans_are_unexecuted() -> None:
    acquisition = _json(AUDIT_ROOT / "acquisition_plan/acquisition_plan_v1.json")
    pilot = _json(AUDIT_ROOT / "acquisition_plan/pilot_plan_v1.json")
    assert acquisition["status"] == "PLAN_ONLY_NOT_EXECUTED"
    assert acquisition["bulk_ingestion_executed"] is False
    assert len(acquisition["items"]) >= 6
    assert pilot["status"] == "PLAN_ONLY_NOT_EXECUTED"
    assert all(row["execution_status"] == "NOT_RUN" for row in pilot["pilots"])
    assert all(row["years"] == "2022,2023,2024" for row in pilot["pilots"])


def test_manifest_is_canonical_immutable_and_hashes_components() -> None:
    manifest = _json(MANIFEST_PATH)
    body = {
        key: value
        for key, value in manifest.items()
        if key != "family_f_data_readiness_hash"
    }
    assert manifest["family_f_data_readiness_hash"] == canonical_hash(body)
    assert manifest["manifest_version"] == MANIFEST_VERSION
    for relative, expected in manifest["component_hashes"].items():
        assert file_sha256(REPO_ROOT / relative) == expected


def test_no_strategy_experiment_backtest_validation_or_migration() -> None:
    source = (
        REPO_ROOT
        / "backend/app/research/strategy/family_f_catalyst_data_readiness.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    assert not re.search(r"\b(?:CONTROL|CAT)-F-\d{3}\b", source)
    assert not any("backtest" in module for module in imported_modules)
    assert not any("validation" in module and "temporal_validation.config" not in module for module in imported_modules)
    governance = _summary()["governance"]
    assert governance["strategy_implementation_started"] is False
    assert governance["strategy_parameters_created"] is False
    assert governance["experiments_created"] == 0
    assert governance["backtests_run"] == 0
    assert governance["bulk_historical_ingestions"] == 0
    assert governance["new_providers_connected"] == 0
    assert governance["validation_accessed"] is False
    assert governance["strategy_v2_created"] is False
    assert governance["db_migrations_created"] == 0


def test_security_and_live_side_effect_counters_are_zero() -> None:
    governance = _summary()["governance"]
    for field in (
        "live_signals",
        "live_orders",
        "broker_calls",
        "remote_migrations",
        "supabase_persistence",
        "external_writes",
        "credentials_written",
    ):
        assert governance[field] == 0


def test_roadmap_has_exact_current_family_states() -> None:
    text = (REPO_ROOT / "docs/strategy-family-research-roadmap-v1.md").read_text(
        encoding="utf-8"
    )
    expected = {
        "A": "PAUSED_PENDING_LATER_VALIDATION_DESIGN",
        "B": "PAUSED_NO_VALIDATION_CANDIDATE",
        "C": "PAUSED_NO_VALIDATION_CANDIDATE",
        "D": "PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE",
        "E": "PAUSED_NO_VALIDATION_CANDIDATE",
        "F": "ACTIVE_DATA_READINESS",
        "G": "PLANNED_NOT_STARTED",
    }
    for family, status in expected.items():
        assert re.search(rf"^\| Family {family} \|[^\n]+\| {status} \|$", text, re.MULTILINE)


def test_all_reports_and_documentation_are_generated() -> None:
    assert all((REPORT_ROOT / name).is_file() for name in REPORT_NAMES)
    assert (
        REPO_ROOT / "docs/strategy-family-f-catalyst-data-readiness-v1.md"
    ).is_file()
    assert len(read_csv(REPORT_ROOT / REPORT_NAMES[1])) >= 12
    assert len(read_csv(REPORT_ROOT / REPORT_NAMES[2])) == 17
    assert len(read_csv(REPORT_ROOT / REPORT_NAMES[3])) == 5
    assert len(read_csv(REPORT_ROOT / REPORT_NAMES[4])) == 6
