from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from app.research.strategy.family_a_momentum import file_sha256
from app.research.strategy.family_f_catalyst_data_readiness import (
    EXPECTED_FAMILY_E_CLOSURE_HASH,
    HISTORICAL_EARNINGS_SURPRISE_READINESS,
    LINKAGE_CLASSIFICATIONS,
)
from app.research.strategy.family_f_official_source_pilot import (
    COMMAND_PROFILE,
    COMMAND_VERSION,
    MANIFEST_VERSION,
    PILOT_REQUEST_PLAN_HASH,
    REPORT_NAMES,
    audit_duplicates,
    build_request_plan,
    classify_announcement_category,
    classify_market_timing,
    deterministic_pilot_population,
    evaluate_source_result,
    parse_source_fixture,
    verify_command_01,
)
from app.research.temporal_validation.config import canonical_hash


REPO_ROOT = Path(__file__).resolve().parents[2]
PILOT_ROOT = REPO_ROOT / "data/research/strategy_families/family_f/source_pilot/v1"
REPORT_ROOT = REPO_ROOT / "data/reports"
SUMMARY_PATH = REPORT_ROOT / REPORT_NAMES[0]
MANIFEST_PATH = PILOT_ROOT / "manifests/family_f_official_source_pilot_manifest_v1.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _summary() -> dict:
    return _json(SUMMARY_PATH)


def _technical_row(**overrides: object) -> dict:
    row = {
        "records_inspected": 20,
        "access_status": "BOUNDED_OFFICIAL_RECORDS_RETRIEVED",
        "trusted_publication_timestamp_percent": 100.0,
        "canonical_linkage_percent": 100.0,
        "stable_document_id_percent": 100.0,
        "reproducible_retrieval_percent": 100.0,
        "licensing_classification": "PUBLIC_RESEARCH_USE_CLEAR",
    }
    row.update(overrides)
    return row


def test_command_identity_and_baseline_hashes_are_exact() -> None:
    assert COMMAND_VERSION == "FAMILY_F_OFFICIAL_SOURCE_PILOT_V1"
    assert COMMAND_PROFILE == "CATALYST_TIMESTAMP_LINKAGE_PILOT_V1"
    assert MANIFEST_VERSION == "FAMILY_F_OFFICIAL_SOURCE_PILOT_MANIFEST_V1"
    command_01 = verify_command_01(REPO_ROOT)
    assert command_01["status"] == "VERIFIED"
    assert command_01["family_f_data_readiness_hash"] == (
        "45ce21fdbf020cd990bdd9ca727e0d278de1eb9d5132d3cba18a70fb72ca0765"
    )
    assert _summary()["baseline"]["family_e_closure_hash"] == EXPECTED_FAMILY_E_CLOSURE_HASH


def test_population_and_request_plan_are_deterministic_and_pre_network() -> None:
    first = deterministic_pilot_population(REPO_ROOT)
    second = deterministic_pilot_population(REPO_ROOT)
    assert first == second
    assert len(first) == 8
    assert len({row["symbol"] for row in first}) == 8
    assert {row["selection_reference_year"] for row in first} >= {
        "2022", "2023", "2024"
    }
    assert all("price" not in " ".join(row).lower() for row in first)
    plan = build_request_plan(REPO_ROOT)
    assert plan["family_f_pilot_request_plan_hash"] == PILOT_REQUEST_PLAN_HASH
    assert plan["created_before_network_access"] is True
    assert plan["request_count"] == 24
    assert plan["target_years"] == ["2022", "2023", "2024"]
    assert all(row["planned_before_network_access"] for row in plan["requests"])
    assert all(row["max_records_to_retain"] <= 50 for row in plan["requests"])


def test_offline_fixture_parser_preserves_raw_provenance() -> None:
    rows = parse_source_fixture(
        "OFFICIAL_FIXTURE",
        [{"source_document_id": "A-1", "published_at": "2024-01-02"}],
    )
    assert rows == [
        {
            "source_document_id": "A-1",
            "published_at": "2024-01-02",
            "source": "OFFICIAL_FIXTURE",
            "timestamp_classification": "UNKNOWN",
            "linkage_classification": "UNRESOLVED",
            "revision_id": "",
            "supersedes_event_id": "",
            "raw_metadata": {
                "source_document_id": "A-1",
                "published_at": "2024-01-02",
            },
        }
    ]


def test_timestamp_and_market_timing_classifications() -> None:
    assert classify_market_timing(
        "2022-11-15T08:00:00+05:30", "EXACT_EXCHANGE_TIMESTAMP"
    ) == "PRE_OPEN"
    assert classify_market_timing(
        "2022-11-15T12:00:00+05:30", "RELIABLE_PUBLICATION_TIMESTAMP"
    ) == "DURING_MARKET"
    assert classify_market_timing(
        "2022-11-15T18:00:00+05:30", "EXACT_EXCHANGE_TIMESTAMP"
    ) == "POST_CLOSE"
    assert classify_market_timing(
        "2022-11-13T12:00:00+05:30", "EXACT_EXCHANGE_TIMESTAMP"
    ) == "NON_TRADING_DAY"
    assert classify_market_timing("2022-11-15", "DATE_ONLY") == "DATE_ONLY_UNKNOWN_TIME"


def test_linkage_and_timestamp_records_use_frozen_vocabularies() -> None:
    records = _json(PILOT_ROOT / "normalized_samples/family_f_normalized_records_v1.json")["records"]
    assert {row["timestamp_classification"] for row in records} == {
        "EXACT_EXCHANGE_TIMESTAMP", "DATE_ONLY", "UNKNOWN"
    }
    assert all(row["linkage_classification"] in LINKAGE_CLASSIFICATIONS for row in records)
    assert {row["linkage_classification"] for row in records} == {
        "EXACT_ISIN", "EXACT_SYMBOL_DATE_VALID"
    }
    assert all(row["provenance_retained"] is True for row in records)


def test_announcement_mapping_is_neutral_and_bounded() -> None:
    expected = {
        "Order win": "ORDER_OR_CONTRACT",
        "Board decision": "BOARD_DECISION",
        "Fund Raising": "FUNDRAISING",
        "Acquisition": "M_AND_A",
        "Buyback": "BUYBACK",
        "Dividend": "DIVIDEND",
        "Stock split": "SPLIT_OR_BONUS",
        "Regulation 30": "REGULATORY",
        "Press release": "OTHER_FILING",
    }
    assert {key: classify_announcement_category(key) for key in expected} == expected
    assert not any("BULL" in value or "BEAR" in value for value in expected.values())


def test_duplicate_design_and_collision_detection() -> None:
    records = _json(PILOT_ROOT / "normalized_samples/family_f_normalized_records_v1.json")["records"]
    audit = audit_duplicates(records)
    assert audit["primary_key"] == ["source", "source_document_id"]
    assert audit["fallback_key"] == [
        "source", "ISIN-or-symbol", "published_at", "event_category"
    ]
    assert audit["primary_collision_count"] == 0
    assert audit["fallback_collision_count"] == 0
    duplicate = audit_duplicates([records[0], records[0]])
    assert duplicate["primary_collision_count"] == 1
    assert duplicate["fallback_collision_count"] == 1


def test_threshold_pass_conditional_fail_and_access_logic() -> None:
    assert evaluate_source_result(_technical_row()) == "PILOT_PASS"
    assert evaluate_source_result(
        _technical_row(licensing_classification="AUTOMATION_RESTRICTED")
    ) == "PILOT_CONDITIONAL"
    assert evaluate_source_result(
        _technical_row(trusted_publication_timestamp_percent=94.99)
    ) == "PILOT_FAIL"
    assert evaluate_source_result(
        _technical_row(records_inspected=0, access_status="AUTOMATION_ACCESS_RESTRICTED")
    ) == "ACCESS_RESTRICTED"
    assert evaluate_source_result(
        _technical_row(records_inspected=0, access_status="NO_MATCH")
    ) == "INCONCLUSIVE"


def test_actual_pilot_decisions_are_conservative() -> None:
    summary = _summary()
    by_source = {row["source"]: row for row in summary["source_results"]}
    assert by_source["NSE_CORPORATE_ANNOUNCEMENTS"]["pilot_result"] == "PILOT_CONDITIONAL"
    assert by_source["NIFTY_INDICES_NOTICES"]["pilot_result"] == "PILOT_FAIL"
    assert by_source["BSE_CORPORATE_ANNOUNCEMENTS"]["pilot_result"] == "ACCESS_RESTRICTED"
    assert by_source["CRISIL_RATING_DISCLOSURES"]["pilot_result"] == "ACCESS_RESTRICTED"
    assert summary["FAMILY_F_HISTORICAL_ACQUISITION_READINESS"] == "CONDITIONAL"
    assert summary["FAMILY_F_NEXT_STAGE"] == "LICENSE_RESOLUTION"
    assert summary["FAMILY_F_PREREGISTRATION_READINESS"] == "NO"
    assert HISTORICAL_EARNINGS_SURPRISE_READINESS == "NOT_AVAILABLE"
    assert summary["HISTORICAL_EARNINGS_SURPRISE_READINESS"] == "NOT_AVAILABLE"


def test_no_price_outcomes_validation_bulk_ingestion_or_strategy_v2() -> None:
    manifest = _json(MANIFEST_PATH)
    safety = manifest["safety"]
    assert safety == {
        "strategy_created": False,
        "trading_parameters_created": False,
        "price_outcome_analysis_run": False,
        "bulk_historical_ingestion_run": False,
        "subscription_purchased": False,
        "access_restriction_bypassed": False,
        "validation_accessed": False,
        "strategy_v2_created": False,
        "family_g_started": False,
        "credentials_written": False,
        "browser_session_material_written": False,
        "live_signals": 0,
        "live_orders": 0,
        "broker_calls": 0,
        "remote_migrations": 0,
        "supabase_persistence": 0,
    }
    records = _json(PILOT_ROOT / "normalized_samples/family_f_normalized_records_v1.json")["records"]
    prohibited = {"price", "return", "outcome", "signal", "entry", "stop", "holding_period", "catalyst_score"}
    assert all(not (prohibited & set(row)) for row in records)
    source = (REPO_ROOT / "backend/app/research/strategy/family_f_official_source_pilot.py").read_text(encoding="utf-8")
    assert not re.search(r"\b(?:CONTROL|CAT)-F-\d{3}\b", source)
    imports = {
        node.module or "" for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)
    }
    assert not any("backtest" in module for module in imports)
    assert not any("validation" in module and module != "app.research.temporal_validation.config" for module in imports)


def test_manifest_is_canonical_and_hashes_every_component() -> None:
    manifest = _json(MANIFEST_PATH)
    body = {key: value for key, value in manifest.items() if key != "family_f_source_pilot_hash"}
    assert manifest["family_f_source_pilot_hash"] == canonical_hash(body)
    assert manifest["request_plan"]["family_f_pilot_request_plan_hash"] == PILOT_REQUEST_PLAN_HASH
    for relative, expected in manifest["component_hashes"].items():
        assert file_sha256(REPO_ROOT / relative) == expected


def test_all_reports_documentation_and_storage_areas_exist() -> None:
    assert all((REPORT_ROOT / name).is_file() for name in REPORT_NAMES)
    for directory in (
        "request_plan", "raw_samples", "normalized_samples", "timestamp_audit",
        "linkage", "reconciliation", "licensing", "results", "manifests",
    ):
        assert (PILOT_ROOT / directory).is_dir()
    assert (REPO_ROOT / "docs/strategy-family-f-official-source-pilot-v1.md").is_file()
