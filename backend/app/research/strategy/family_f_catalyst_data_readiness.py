from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.research.strategy.family_a_momentum import file_sha256, read_csv, write_csv, write_json
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.06 / Command 01"
COMMAND_VERSION = "FAMILY_F_CATALYST_DATA_READINESS_V1"
COMMAND_PROFILE = "POINT_IN_TIME_CATALYST_SOURCE_AUDIT_V1"
MANIFEST_VERSION = "FAMILY_F_DATA_READINESS_MANIFEST_V1"
FAMILY_ID = "FAMILY_F_CATALYST_MOMENTUM"
FAMILY_F_STATUS = "DATA_READINESS_ONLY"
FAMILY_F_ROADMAP_STATUS = "ACTIVE_DATA_READINESS"
FAMILY_F_DATA_READINESS = "SOURCE_ACQUISITION_REQUIRED"
FAMILY_F_PREREGISTRATION_READINESS = "NO"
HISTORICAL_EARNINGS_SURPRISE_READINESS = "NOT_AVAILABLE"
EXPECTED_MILESTONE_COMMIT = "c2f7534761e31f53376a6d9d1275aacd2eddc985"
EXPECTED_FAMILY_E_CLOSURE_HASH = (
    "4899cdbfe54b0ea636faa8ff0b4504b6ef60242e7eabdf682b2b913cfb001c00"
)
DEVELOPMENT_START = "2022-01-01"
DEVELOPMENT_END = "2024-12-31"

TIMESTAMP_CLASSIFICATIONS = (
    "EXACT_EXCHANGE_TIMESTAMP",
    "RELIABLE_PUBLICATION_TIMESTAMP",
    "DATE_ONLY",
    "INFERRED",
    "UNKNOWN",
)
MARKET_TIMING_BUCKETS = (
    "PRE_OPEN",
    "DURING_MARKET",
    "POST_CLOSE",
    "NON_TRADING_DAY",
    "DATE_ONLY_UNKNOWN_TIME",
)
LINKAGE_CLASSIFICATIONS = (
    "EXACT_ISIN",
    "EXACT_SYMBOL_DATE_VALID",
    "ALIAS_RESOLVED",
    "COMPANY_NAME_ONLY",
    "AMBIGUOUS",
    "UNRESOLVED",
)
CATEGORY_READINESS_CLASSIFICATIONS = (
    "READY",
    "READY_WITH_LIMITATIONS",
    "SOURCE_AVAILABLE_NOT_INGESTED",
    "LICENSE_REQUIRED",
    "TIMESTAMP_INSUFFICIENT",
    "LINKAGE_INSUFFICIENT",
    "NOT_AVAILABLE",
    "INCONCLUSIVE",
)
LICENSE_STATES = (
    "PUBLIC_OFFICIAL",
    "PUBLIC_WITH_LIMITATIONS",
    "LICENSED_REQUIRED",
    "UNKNOWN_LICENSE",
)
SOURCE_RELIABILITY_TIERS = (
    "TIER_1_OFFICIAL",
    "TIER_2_PRIMARY_COMPANY",
    "TIER_3_LICENSED_STRUCTURED",
    "TIER_4_SECONDARY_MEDIA",
    "UNVERIFIED",
)
NORMALIZED_SCHEMA_FIELDS = (
    "event_id",
    "source",
    "source_document_id",
    "published_at",
    "market_timing_bucket",
    "symbol",
    "isin",
    "canonical_security_id",
    "event_category",
    "event_subcategory",
    "headline",
    "structured_fields",
    "classification_method",
    "classification_version",
    "classification_confidence",
    "source_reliability",
    "revision_id",
    "supersedes_event_id",
    "raw_reference",
    "ingested_at",
)

REPORT_NAMES = (
    "family_f_data_readiness_v1_summary.json",
    "family_f_data_readiness_v1_sources.csv",
    "family_f_data_readiness_v1_taxonomy.csv",
    "family_f_data_readiness_v1_timestamp_quality.csv",
    "family_f_data_readiness_v1_linkage.csv",
    "family_f_data_readiness_v1_licensing.csv",
    "family_f_data_readiness_v1_categories.csv",
    "family_f_data_readiness_v1_acquisition_plan.csv",
    "family_f_data_readiness_v1_leakage_risks.csv",
)


class FamilyFDataReadinessInputError(RuntimeError):
    pass


class FamilyFDataReadinessImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return Path(root) / "data/research/strategy_families/family_f/data_readiness/v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _document_with_hash(body: Mapping[str, Any], field: str) -> dict[str, Any]:
    document = dict(body)
    document[field] = canonical_hash(body)
    return document


def verify_family_e_closure(root: Path) -> dict[str, Any]:
    path = (
        Path(root)
        / "data/research/strategy_families/family_e/v1/closure/manifest/"
        "family_e_closure_manifest_v1.json"
    )
    document = _read_json(path)
    body = {key: value for key, value in document.items() if key != "family_e_closure_hash"}
    actual = canonical_hash(body)
    checks = {
        "stored_hash_is_canonical": document.get("family_e_closure_hash") == actual,
        "expected_hash_matches": actual == EXPECTED_FAMILY_E_CLOSURE_HASH,
        "research_paused": document.get("final_statuses", {}).get(
            "FAMILY_E_RESEARCH_STATUS"
        )
        == "PAUSED_NO_VALIDATION_CANDIDATE",
        "validation_not_accessed": document.get("validation_status") == "NOT_ACCESSED",
        "strategy_v2_not_created": document.get("strategy_v2_status") == "NOT_CREATED",
    }
    if not all(checks.values()):
        raise FamilyFDataReadinessInputError(f"Family E closure mismatch: {checks}")
    return {"status": "VERIFIED", "checks": checks, "family_e_closure_hash": actual}


def _in_window(value: str) -> bool:
    return bool(value) and DEVELOPMENT_START <= value <= DEVELOPMENT_END


def _period_index(rows: Iterable[Mapping[str, str]]) -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        result[row["symbol"].strip().upper()].append(dict(row))
    return result


def _active_period(
    periods: Mapping[str, list[dict[str, str]]], symbol: str, on_date: str
) -> dict[str, str] | None:
    for period in periods.get(symbol.strip().upper(), []):
        if period["valid_from"] <= on_date <= period["valid_to"]:
            return period
    return None


def _distribution(values: Iterable[str], allowed: Iterable[str]) -> dict[str, int]:
    counts = Counter(values)
    return {item: counts.get(item, 0) for item in allowed}


def audit_local_coverage(root: Path) -> dict[str, Any]:
    root = Path(root)
    corporate_path = root / "data/reference/nse/corporate_actions/corporate_action_events.csv"
    extension_path = (
        root
        / "data/research/strategy_families/family_b/v1/history_remediation/raw_manifest/"
        "corporate_action_extension_events.csv"
    )
    membership_events_path = root / "data/reference/nifty500/history/membership_events.csv"
    membership_periods_path = root / "data/reference/nifty500/history/membership_periods.csv"
    required = (corporate_path, extension_path, membership_events_path, membership_periods_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FamilyFDataReadinessInputError(f"Missing local audit inputs: {missing}")

    periods = _period_index(read_csv(membership_periods_path))
    all_actions = read_csv(extension_path) + read_csv(corporate_path)
    target_actions = [row for row in all_actions if _in_window(row["effective_date"])]
    matched_actions: list[tuple[dict[str, str], dict[str, str]]] = []
    for row in target_actions:
        period = _active_period(periods, row["canonical_symbol"], row["effective_date"])
        if period is not None:
            matched_actions.append((row, period))

    action_years = Counter(row["effective_date"][:4] for row, _ in matched_actions)
    action_types = Counter(row["action_type"] for row, _ in matched_actions)
    membership_events = [
        row for row in read_csv(membership_events_path) if _in_window(row["announced_date"])
    ]
    membership_years = Counter(row["announced_date"][:4] for row in membership_events)
    membership_exact_isin = sum(bool(row["isin"].strip()) for row in membership_events)
    action_identity_isin = sum(bool(period["isin"].strip()) for _, period in matched_actions)

    return {
        "version": "FAMILY_F_LOCAL_COVERAGE_AUDIT_V1",
        "target_window": {"start": DEVELOPMENT_START, "end": DEVELOPMENT_END},
        "scope": "POINT_IN_TIME_NIFTY_500_ON_EVENT_EFFECTIVE_DATE",
        "inputs": {
            str(path.relative_to(root)).replace("\\", "/"): file_sha256(path)
            for path in required
        },
        "corporate_actions": {
            "source_role": "EFFECTIVE_EVENT_ONLY_NOT_PUBLICATION_CATALYST",
            "all_exchange_rows_in_target_window": len(target_actions),
            "nifty500_rows_on_effective_date": len(matched_actions),
            "unique_symbols": len({row["canonical_symbol"] for row, _ in matched_actions}),
            "unique_companies": len({row["company_name"] for row, _ in matched_actions}),
            "earliest_date": min(row["effective_date"] for row, _ in matched_actions),
            "latest_date": max(row["effective_date"] for row, _ in matched_actions),
            "year_counts": {year: action_years.get(year, 0) for year in ("2022", "2023", "2024")},
            "action_type_counts": dict(sorted(action_types.items())),
            "timestamp_quality": _distribution(
                ("DATE_ONLY" for _ in matched_actions), TIMESTAMP_CLASSIFICATIONS
            ),
            "publication_timestamp_count": 0,
            "same_day_causal_usable_count": 0,
            "source_isin_count": sum(bool(row["isin"].strip()) for row, _ in matched_actions),
            "exact_symbol_date_valid_count": len(matched_actions),
            "canonical_identity_isin_enriched_count": action_identity_isin,
            "canonical_identity_isin_enriched_percent": round(
                100 * action_identity_isin / len(matched_actions), 6
            ),
            "linkage_quality": {
                "EXACT_ISIN": 0,
                "EXACT_SYMBOL_DATE_VALID": len(matched_actions),
                "ALIAS_RESOLVED": 0,
                "COMPANY_NAME_ONLY": 0,
                "AMBIGUOUS": 0,
                "UNRESOLVED": 0,
            },
            "limitation": (
                "The local NSE corporate-action layer records ex/effective dates, not the "
                "original public announcement timestamp. It cannot establish same-day causality."
            ),
        },
        "index_membership_notices": {
            "source_role": "OFFICIAL_INDEX_NOTICE_DATE_SEPARATE_FROM_EFFECTIVE_DATE",
            "event_count": len(membership_events),
            "unique_symbols": len({row["symbol"] for row in membership_events}),
            "unique_companies": len(
                {row["company_name_normalized"] for row in membership_events}
            ),
            "earliest_date": min(row["announced_date"] for row in membership_events),
            "latest_date": max(row["announced_date"] for row in membership_events),
            "year_counts": {
                year: membership_years.get(year, 0) for year in ("2022", "2023", "2024")
            },
            "timestamp_quality": _distribution(
                ("DATE_ONLY" for _ in membership_events), TIMESTAMP_CLASSIFICATIONS
            ),
            "publication_timestamp_count": 0,
            "same_day_causal_usable_count": 0,
            "source_isin_count": membership_exact_isin,
            "exact_symbol_date_valid_count": len(membership_events) - membership_exact_isin,
            "canonical_identity_linked_count": len(membership_events),
            "canonical_identity_linked_percent": 100.0,
            "linkage_quality": {
                "EXACT_ISIN": membership_exact_isin,
                "EXACT_SYMBOL_DATE_VALID": len(membership_events) - membership_exact_isin,
                "ALIAS_RESOLVED": 0,
                "COMPANY_NAME_ONLY": 0,
                "AMBIGUOUS": 0,
                "UNRESOLVED": 0,
            },
            "limitation": (
                "The local parsed press-release layer retains announcement dates but not "
                "time-of-day publication timestamps."
            ),
        },
        "inventory_conclusion": {
            "existing_project_source_count": 4,
            "existing_event_dataset_count": 2,
            "event_sources": ["NSE_CORPORATE_ACTIONS_LOCAL", "NIFTY_INDEX_NOTICES_LOCAL"],
            "supporting_or_schema_sources": [
                "PROJECT_NEWS_EVENTS_SCHEMA_ONLY",
                "PROJECT_PRICE_VOLUME_INFRASTRUCTURE",
            ],
            "locally_ingested_exact_or_reliable_publication_timestamp_events": 0,
        },
    }


def taxonomy_rows(coverage: Mapping[str, Any]) -> list[dict[str, Any]]:
    action = coverage["corporate_actions"]
    index = coverage["index_membership_notices"]
    types = action["action_type_counts"]
    definitions = [
        ("A", "FINANCIAL_RESULTS", "Quarterly and annual reported results", "SOURCE_AVAILABLE_NOT_INGESTED"),
        ("B", "EARNINGS_SURPRISE_MATERIAL_CHANGE", "Point-in-time reported-versus-consensus change", "NOT_AVAILABLE"),
        ("C", "CORPORATE_ANNOUNCEMENTS_EXCHANGE_FILINGS", "Material NSE/BSE exchange filings", "SOURCE_AVAILABLE_NOT_INGESTED"),
        ("D", "ORDER_CONTRACT_WINS", "Order, contract, project, purchase order, or letter of award", "SOURCE_AVAILABLE_NOT_INGESTED"),
        ("E", "REGULATORY_APPROVAL_REJECTION", "Official approval, rejection, or regulator decision", "SOURCE_AVAILABLE_NOT_INGESTED"),
        ("F", "MANAGEMENT_GUIDANCE_REVISION", "Management guidance or revision", "SOURCE_AVAILABLE_NOT_INGESTED"),
        ("G", "MERGERS_ACQUISITIONS_DEMERGERS", "Mergers, acquisitions, and demergers", "TIMESTAMP_INSUFFICIENT"),
        ("H", "BUYBACKS", "Buyback announcements and revisions", "SOURCE_AVAILABLE_NOT_INGESTED"),
        ("I", "DIVIDENDS", "Ordinary and special dividend announcements", "TIMESTAMP_INSUFFICIENT"),
        ("J", "STOCK_SPLITS_BONUS", "Stock splits and bonus issues", "TIMESTAMP_INSUFFICIENT"),
        ("K", "PREFERENTIAL_QIP_FUNDRAISING", "Preferential allotment, QIP, rights, and fundraising", "TIMESTAMP_INSUFFICIENT"),
        ("L", "PROMOTER_INSIDER_BULK_BLOCK", "Official promoter, insider, bulk, and block disclosures", "SOURCE_AVAILABLE_NOT_INGESTED"),
        ("M", "INDEX_INCLUSION_EXCLUSION", "Official index-provider inclusion and exclusion notices", "TIMESTAMP_INSUFFICIENT"),
        ("N", "RATING_UPGRADE_DOWNGRADE", "Credible rating-agency upgrades and downgrades", "SOURCE_AVAILABLE_NOT_INGESTED"),
        ("O", "BOARD_DECISIONS_MATERIAL_ACTIONS", "Board decisions and material corporate actions", "SOURCE_AVAILABLE_NOT_INGESTED"),
        ("P", "EXCHANGE_SURVEILLANCE_REGULATORY_ACTION", "Exchange surveillance and regulator action", "SOURCE_AVAILABLE_NOT_INGESTED"),
        ("Q", "OTHER_MATERIAL_CORPORATE_FILINGS", "Other material NSE/BSE filing categories", "SOURCE_AVAILABLE_NOT_INGESTED"),
    ]
    actual = {
        "G": types.get("DEMERGER", 0),
        "I": types.get("DIVIDEND", 0) + types.get("SPECIAL_DIVIDEND", 0),
        "J": types.get("STOCK_SPLIT", 0) + types.get("BONUS", 0),
        "K": types.get("RIGHTS", 0),
        "M": index["event_count"],
    }
    rows = []
    for code, category, description, readiness in definitions:
        count = actual.get(code)
        source = ""
        if code in {"G", "I", "J", "K"}:
            source = "NSE_CORPORATE_ACTIONS_LOCAL_EFFECTIVE_DATE_ONLY"
        elif code == "M":
            source = "NIFTY_INDEX_NOTICES_LOCAL_DATE_ONLY"
        rows.append(
            {
                "taxonomy_code": code,
                "event_category": category,
                "definition": description,
                "readiness": readiness,
                "actual_accessible_count": count if count is not None else "NOT_RETRIEVED",
                "actual_count_source": source or "CAPABILITY_ASSESSMENT_ONLY",
                "strategy_weight": "NOT_DEFINED",
            }
        )
    return rows


def source_rows() -> list[dict[str, Any]]:
    def row(
        source_name: str,
        source_type: str,
        authority: str,
        project_state: str,
        historical: str,
        earliest: str,
        latest: str,
        precision: str,
        publication: str,
        category: str,
        symbol: str,
        isin: str,
        company: str,
        document: str,
        revisions: str,
        raw: str,
        rate_limits: str,
        license_state: str,
        automation: str,
        suitability: str,
        reference: str,
    ) -> dict[str, Any]:
        return {
            "source_name": source_name,
            "source_type": source_type,
            "purpose": f"{category}: {suitability}",
            "official_or_secondary": authority,
            "project_state": project_state,
            "historical_available": historical,
            "earliest_date": earliest,
            "latest_date": latest,
            "timestamp_precision": precision,
            "publication_timestamp_available": publication,
            "event_category": category,
            "symbol_available": symbol,
            "isin_available": isin,
            "company_name_available": company,
            "document_id_available": document,
            "revision_history_available": revisions,
            "raw_payload_available": raw,
            "raw_storage": reference if raw in {"YES", "DOWNLOAD_CAPABILITY"} else "NOT_STORED_LOCALLY",
            "normalization_layer": {
                "LOCAL_DATASET": "IMPLEMENTED",
                "LOCAL_SUPPORTING_DATA": "IMPLEMENTED_SUPPORTING_MARKET_DATA",
                "SCHEMA_ONLY_NO_ROWS": "SCHEMA_ONLY",
            }.get(project_state, "NOT_IMPLEMENTED"),
            "rate_limits": rate_limits,
            "license_restrictions": license_state,
            "license_state": license_state,
            "licensing_notes": (
                f"{license_state}; confirm terms before new automated or bulk retrieval"
            ),
            "automation_feasibility": automation,
            "research_suitability": suitability,
            "reference": reference,
        }

    return [
        row("NSE_CORPORATE_ACTIONS_LOCAL", "corporate_action_effective_events", "OFFICIAL", "LOCAL_DATASET", "YES", "2020-01-06", "2026-09-07", "DATE_ONLY", "NO", "G,I,J,K,O", "YES", "NO", "YES", "YES", "NO", "YES", "NOT_APPLICABLE_LOCAL", "PUBLIC_WITH_LIMITATIONS", "IMPLEMENTED_LOCAL_READ", "EFFECTIVE_DATE_ONLY_NOT_SAME_DAY_CAUSAL", "data/reference/nse/corporate_actions/corporate_action_events.csv"),
        row("NIFTY_INDEX_NOTICES_LOCAL", "index_provider_press_releases", "OFFICIAL", "LOCAL_DATASET", "YES", "2021-06-15", "2026-09-03", "DATE_ONLY", "NO", "M", "YES", "PARTIAL", "YES", "YES", "PARTIAL", "YES", "NOT_APPLICABLE_LOCAL", "PUBLIC_WITH_LIMITATIONS", "IMPLEMENTED_LOCAL_READ", "NEXT_DAY_OR_DATE_ONLY_RESEARCH_WITH_LIMITATIONS", "data/reference/nifty500/history/membership_events.csv"),
        row("PROJECT_NEWS_EVENTS_SCHEMA_ONLY", "database_schema_placeholder", "INTERNAL", "SCHEMA_ONLY_NO_ROWS", "NO", "", "", "UNKNOWN", "UNVERIFIED", "C-Q", "SCHEMA_FIELD", "NO", "SCHEMA_FIELD", "NO", "NO", "NO", "NOT_APPLICABLE", "UNKNOWN_LICENSE", "NO_SOURCE_IMPLEMENTATION", "NOT_AVAILABLE", "backend/migrations/001_initial_schema.sql"),
        row("PROJECT_PRICE_VOLUME_INFRASTRUCTURE", "supporting_market_data", "MIXED_OFFICIAL_PROVIDER", "LOCAL_SUPPORTING_DATA", "YES", "2021-09-07", "2026-09-07", "DAILY_AND_BOUNDED_5M", "NOT_AN_EVENT_SOURCE", "CONFIRMATION_ONLY", "YES", "PARTIAL", "YES", "NO", "NO", "YES", "EXISTING_PIPELINES", "PUBLIC_WITH_LIMITATIONS", "IMPLEMENTED", "READY_DAILY_BOUNDED_INTRADAY", "data/research/adjusted/daily/nse"),
        row("NSE_CORPORATE_FILINGS_ANNOUNCEMENTS", "exchange_announcements", "OFFICIAL", "SOURCE_AVAILABLE_NOT_INGESTED", "CAPABILITY_CONFIRMED_RANGE_UNAUDITED", "PENDING_PILOT", "CURRENT", "EXACT_EXCHANGE_TIMESTAMP_CAPABILITY", "YES", "A,C-Q", "YES", "PARTIAL", "YES", "YES", "YES", "DOWNLOAD_CAPABILITY", "SITE_OR_PRODUCT_CONTROLS", "PUBLIC_WITH_LIMITATIONS", "PILOT_REQUIRED", "BEST_PRIMARY_CANDIDATE", "https://www.nseindia.com/companies-listing/corporate-filings-application?id=allAnnouncements"),
        row("NSE_FINANCIAL_RESULTS_XBRL", "structured_exchange_filings", "OFFICIAL", "SOURCE_AVAILABLE_NOT_INGESTED", "CAPABILITY_CONFIRMED_RANGE_UNAUDITED", "PENDING_PILOT", "CURRENT", "EXACT_EXCHANGE_TIMESTAMP_CAPABILITY", "YES", "A", "YES", "PARTIAL", "YES", "YES", "YES", "STRUCTURED_PAYLOAD_CAPABILITY", "SITE_OR_PRODUCT_CONTROLS", "PUBLIC_WITH_LIMITATIONS", "PILOT_REQUIRED", "REPORTED_RESULTS_ONLY_NO_CONSENSUS", "https://www.nseindia.com/static/companies-listing/xbrl-information"),
        row("BSE_CORPORATE_ANNOUNCEMENTS", "exchange_announcements", "OFFICIAL", "SOURCE_AVAILABLE_NOT_INGESTED", "CAPABILITY_CONFIRMED_RANGE_UNAUDITED", "PENDING_PILOT", "CURRENT", "EXACT_EXCHANGE_TIMESTAMP_CAPABILITY", "YES", "A,C-Q", "YES", "PARTIAL", "YES", "YES", "YES", "DOWNLOAD_CAPABILITY", "SITE_CONTROLS_UNKNOWN_BULK_TERMS", "PUBLIC_WITH_LIMITATIONS", "PILOT_REQUIRED", "RECONCILIATION_SOURCE", "https://www.bseindia.com/corporates/ann.html"),
        row("NSE_INSIDER_TRADING_ARCHIVE", "exchange_disclosure_archive", "OFFICIAL", "SOURCE_AVAILABLE_NOT_INGESTED", "YES_UNMEASURED", "PENDING_PILOT", "CURRENT", "PENDING_PILOT", "PENDING_PILOT", "L", "YES", "PARTIAL", "YES", "YES", "PENDING_PILOT", "EXPORT_CAPABILITY", "DATE_RANGE_CONTROLS", "PUBLIC_WITH_LIMITATIONS", "PILOT_REQUIRED", "TIMING_SEMANTICS_UNAUDITED", "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading-archive-data"),
        row("NSE_BULK_BLOCK_ARCHIVE", "exchange_transaction_archive", "OFFICIAL", "SOURCE_AVAILABLE_NOT_INGESTED", "YES", "2018_OR_EARLIER_CAPABILITY", "CURRENT", "DATE_ONLY_OR_POST_MARKET", "AFTER_MARKET_DISSEMINATION", "L", "YES", "NO", "YES", "FILE_DATE", "NO", "DOWNLOAD_CAPABILITY", "SITE_OR_REPORT_CONTROLS", "PUBLIC_WITH_LIMITATIONS", "PILOT_REQUIRED", "NOT_SAME_DAY_UNLESS_TIMING_PROVEN", "https://www.nseindia.com/all-reports"),
        row("SEBI_ORDERS_AND_ACTIONS", "regulator_orders", "OFFICIAL", "SOURCE_AVAILABLE_NOT_INGESTED", "YES", "2022_OR_EARLIER", "CURRENT", "DATE_ONLY", "NO_TIME_CONFIRMED", "E,P", "NO", "NO", "YES", "YES", "POSSIBLE", "DOCUMENT_DOWNLOAD", "SITE_CONTROLS", "PUBLIC_WITH_LIMITATIONS", "TEXT_AND_ENTITY_PILOT_REQUIRED", "NEXT_DAY_ONLY_UNTIL_TIME_PROVEN", "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=2&smid=2&ssid=9"),
        row("ICRA_RATING_RATIONALES", "rating_agency_disclosures", "CREDIBLE_PRIMARY", "SOURCE_AVAILABLE_NOT_INGESTED", "YES", "2021_OR_EARLIER", "CURRENT", "DATE_ONLY_LISTING", "PENDING_PILOT", "N", "NO", "NO", "YES", "YES", "POSSIBLE", "DOCUMENT_DOWNLOAD", "TERMS_AND_AUTOMATION_UNAUDITED", "UNKNOWN_LICENSE", "PILOT_REQUIRED", "ENTITY_MAPPING_REQUIRED", "https://www.icra.in/Rating/AllRatingRationales"),
        row("CRISIL_RATING_RATIONALES", "rating_agency_disclosures", "CREDIBLE_PRIMARY", "SOURCE_AVAILABLE_NOT_INGESTED", "YES", "PENDING_PILOT", "CURRENT", "DATE_ONLY_OR_DOCUMENT_METADATA", "PENDING_PILOT", "N", "NO", "NO", "YES", "YES", "POSSIBLE", "DOCUMENT_DOWNLOAD", "TERMS_AND_AUTOMATION_UNAUDITED", "UNKNOWN_LICENSE", "PILOT_REQUIRED", "ENTITY_MAPPING_REQUIRED", "https://www.crisilratings.com/en/home/our-business/ratings/regulatory-disclosures.html"),
        row("COMPANY_INVESTOR_RELATIONS", "issuer_primary_disclosures", "PRIMARY_COMPANY", "NOT_INGESTED", "VARIES_BY_ISSUER", "UNKNOWN", "CURRENT", "VARIES", "VARIES", "A,C-Q", "VARIES", "VARIES", "YES", "VARIES", "VARIES", "DOCUMENT_DOWNLOAD", "ISSUER_SPECIFIC", "PUBLIC_WITH_LIMITATIONS", "LOW_UNIVERSE_WIDE", "FALLBACK_OR_RECONCILIATION_ONLY", "ISSUER_SPECIFIC"),
        row("LICENSED_HISTORICAL_CONSENSUS", "analyst_consensus", "LICENSED_STRUCTURED", "NO_PROVIDER_CONNECTED", "NOT_AVAILABLE_IN_PROJECT", "", "", "UNKNOWN", "UNKNOWN", "B", "PENDING_PROVIDER", "PENDING_PROVIDER", "PENDING_PROVIDER", "PENDING_PROVIDER", "PENDING_PROVIDER", "NO", "PROVIDER_SPECIFIC", "LICENSED_REQUIRED", "NOT_ASSESSED", "REQUIRED_FOR_TRUE_EARNINGS_SURPRISE", "NO_PROVIDER_SELECTED"),
    ]


def licensing_rows(sources: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    subscriptions = {
        "LICENSED_HISTORICAL_CONSENSUS": "POTENTIALLY_REQUIRED_LATER",
        "NSE_CORPORATE_FILINGS_ANNOUNCEMENTS": "POTENTIALLY_REQUIRED_LATER",
        "NSE_FINANCIAL_RESULTS_XBRL": "POTENTIALLY_REQUIRED_LATER",
    }
    rows = []
    for source in sources:
        if source["project_state"] in {"LOCAL_DATASET", "LOCAL_SUPPORTING_DATA", "SCHEMA_ONLY_NO_ROWS"}:
            requirement = "NOT_REQUIRED"
        else:
            requirement = subscriptions.get(source["source_name"], "NOT_REQUIRED")
        rows.append(
            {
                "source_name": source["source_name"],
                "license_state": source["license_state"],
                "subscription_requirement": requirement,
                "current_action": "NO_PURCHASE_OR_CONNECTION_AUTHORIZED",
                "finding": (
                    "Bulk, reproducible historical use requires terms review; public page "
                    "availability is not equivalent to redistribution or bulk-use permission."
                ),
            }
        )
    return rows


def acquisition_rows() -> list[dict[str, Any]]:
    return [
        {
            "priority": 1,
            "source": "NSE_CORPORATE_FILINGS_ANNOUNCEMENTS",
            "category": "C,D,E,F,G,H,I,J,K,O,P,Q",
            "date_range": f"{DEVELOPMENT_START}/{DEVELOPMENT_END}",
            "required_fields": "document_id,published_at,symbol,company_name,subject,attachment,revision_status",
            "timestamp_requirements": "EXACT_EXCHANGE_TIMESTAMP;Asia/Kolkata;retain raw value",
            "identity_requirements": "symbol plus ISIN where supplied; point-in-time alias resolution",
            "licensing_action": "Confirm research retrieval terms; evaluate licensed EOD SFTP if public archive is not reproducible",
            "estimated_requests_storage": "10-symbol pilot: 30 symbol-year partitions; full request and storage estimate pending measured pilot",
            "quality_pilot": "10 symbols; multiple filing types; one sample in each of 2022/2023/2024; reconcile timestamp and revisions",
        },
        {
            "priority": 2,
            "source": "NSE_FINANCIAL_RESULTS_XBRL",
            "category": "A",
            "date_range": f"{DEVELOPMENT_START}/{DEVELOPMENT_END}",
            "required_fields": "document_id,published_at,period_end,revenue,profit,EPS,symbol,ISIN,revision_status",
            "timestamp_requirements": "Exact exchange receipt/dissemination timestamp",
            "identity_requirements": "ISIN preferred; symbol valid on publication date",
            "licensing_action": "Confirm archive and XBRL reuse terms",
            "estimated_requests_storage": "Pilot measurement required; do not extrapolate before response/document sizes are observed",
            "quality_pilot": "5-10 issuers across all three years; reconcile XBRL to announcement metadata and corrected filings",
        },
        {
            "priority": 3,
            "source": "NIFTY_INDEX_NOTICES_LOCAL",
            "category": "M",
            "date_range": f"{DEVELOPMENT_START}/{DEVELOPMENT_END}",
            "required_fields": "source_document,published_at,announced_date,effective_date,symbol,ISIN,revision_chain",
            "timestamp_requirements": "Recover trustworthy publication time or restrict to next-session/date-only use",
            "identity_requirements": "Preserve existing point-in-time symbol/ISIN mapping without modifying membership",
            "licensing_action": "Confirm archival-use terms; no subscription currently identified",
            "estimated_requests_storage": "35 known Nifty-500-change PDFs in local archive; metadata reconciliation only",
            "quality_pilot": "Reconcile 5-10 notices spanning 2022/2023/2024 against publication metadata and superseding notices",
        },
        {
            "priority": 4,
            "source": "NSE_INSIDER_TRADING_ARCHIVE_AND_BULK_BLOCK_REPORTS",
            "category": "L",
            "date_range": f"{DEVELOPMENT_START}/{DEVELOPMENT_END}",
            "required_fields": "publication_time,trade_date,disclosure_date,symbol,person/entity,quantity,value,document_id",
            "timestamp_requirements": "Separate transaction time/date from public disclosure time",
            "identity_requirements": "symbol-date mapping; issuer ISIN where present; person/entity kept separate",
            "licensing_action": "Confirm archive-export automation and research-use terms",
            "estimated_requests_storage": "Pending measured pilot",
            "quality_pilot": "5-10 symbols and multiple disclosure types across 2022/2023/2024; test duplicates and late disclosures",
        },
        {
            "priority": 5,
            "source": "SEBI_ORDERS_AND_ACTIONS",
            "category": "E,P",
            "date_range": f"{DEVELOPMENT_START}/{DEVELOPMENT_END}",
            "required_fields": "document_id,publication_date_or_time,title,entity,order_type,raw_document",
            "timestamp_requirements": "Date-only is next-session only unless official publication time is proven",
            "identity_requirements": "entity-to-issuer mapping with auditable evidence; ambiguity retained",
            "licensing_action": "Confirm official document reuse/automation terms",
            "estimated_requests_storage": "Pending measured pilot; documents can dominate storage",
            "quality_pilot": "5-10 listed entities across all three years; entity mapping and document correction checks",
        },
        {
            "priority": 6,
            "source": "ICRA_AND_CRISIL_RATING_RATIONALES",
            "category": "N",
            "date_range": f"{DEVELOPMENT_START}/{DEVELOPMENT_END}",
            "required_fields": "agency_document_id,published_at,issuer,instrument,rating_action,prior_rating,new_rating,raw_document",
            "timestamp_requirements": "Publication time preferred; otherwise next-session/date-only restriction",
            "identity_requirements": "issuer-to-listed-security mapping; instrument-level distinction retained",
            "licensing_action": "Obtain written terms clarity before automation or bulk use",
            "estimated_requests_storage": "Pending measured pilot",
            "quality_pilot": "5-10 issuers, upgrades/downgrades/affirmations, each target year; reconcile issuer and instrument",
        },
        {
            "priority": 7,
            "source": "LICENSED_HISTORICAL_CONSENSUS",
            "category": "B",
            "date_range": f"{DEVELOPMENT_START}/{DEVELOPMENT_END}",
            "required_fields": "as_of_timestamp,issuer,metric,period,consensus_value,contributor_count,vintage",
            "timestamp_requirements": "Point-in-time vintage strictly before result publication",
            "identity_requirements": "provider identifier crosswalk to historical ISIN/security",
            "licensing_action": "Only assess vendors if earnings-surprise research is later prioritized; no purchase now",
            "estimated_requests_storage": "Unknown until provider/product selected",
            "quality_pilot": "Provider-authorized sample only; verify vintages, revisions, survivorship, and entitlement",
        },
    ]


def pilot_rows(acquisition: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source": row["source"],
            "pilot_universe": "5-10 point-in-time Nifty 500 symbols",
            "years": "2022,2023,2024",
            "checks": "timestamp_reconciliation;entity_mapping;duplicate_handling;revision_chain;raw_provenance;license_terms",
            "pass_target": ">=95% trustworthy timestamps and >=95% canonical linkage with stable semantics",
            "execution_status": "NOT_RUN",
        }
        for row in acquisition
    ]


def leakage_rows() -> list[dict[str, Any]]:
    return [
        {"risk_id": "F-LEAK-001", "risk": "Using an effective date as publication time", "control": "Store both fields; effective date alone is never same-day causal", "severity": "CRITICAL"},
        {"risk_id": "F-LEAK-002", "risk": "Using a revised or corrected filing as the original", "control": "Immutable original payload plus revision_id and supersedes_event_id", "severity": "CRITICAL"},
        {"risk_id": "F-LEAK-003", "risk": "Using current identifiers for historical linkage", "control": "Point-in-time symbol/ISIN aliases and date-valid canonical mapping", "severity": "HIGH"},
        {"risk_id": "F-LEAK-004", "risk": "Treating post-close disclosure as available during that session", "control": "Asia/Kolkata market timing bucket derived from trustworthy timestamp", "severity": "CRITICAL"},
        {"risk_id": "F-LEAK-005", "risk": "Using labels or summaries created after future outcomes", "control": "Versioned contemporaneous metadata/classifier and raw evidence trace", "severity": "CRITICAL"},
        {"risk_id": "F-LEAK-006", "risk": "Survivorship bias in the issuer universe", "control": "Join only to frozen point-in-time Nifty 500 membership", "severity": "HIGH"},
        {"risk_id": "F-LEAK-007", "risk": "Using later analyst-consensus revisions", "control": "Require point-in-time vintage strictly before publication; otherwise no surprise label", "severity": "CRITICAL"},
        {"risk_id": "F-LEAK-008", "risk": "Duplicate exchange/issuer/media announcements", "control": "Deterministic source/document/security/time/type keys plus cross-source relation", "severity": "HIGH"},
    ]


def schema_document() -> dict[str, Any]:
    return {
        "version": "FAMILY_F_NORMALIZED_CATALYST_SCHEMA_V1",
        "status": "DESIGN_ONLY_NO_DB_MIGRATION",
        "fields": list(NORMALIZED_SCHEMA_FIELDS),
        "timestamp_policy": {
            "timezone": "Asia/Kolkata",
            "accepted_for_normal_future_research": [
                "EXACT_EXCHANGE_TIMESTAMP",
                "RELIABLE_PUBLICATION_TIMESTAMP",
            ],
            "date_only_same_day_usable": False,
        },
        "classification_trace": [
            "raw filing",
            "deterministic metadata",
            "document text extraction",
            "classifier",
            "confidence",
            "human/audit trace",
        ],
        "ai_policy": (
            "AI may classify a retained source document but must never invent an event. "
            "Every classification retains source document ID, timestamp, raw reference, "
            "classifier version, confidence, and evidence."
        ),
        "revision_policy": "Preserve original publication, every revision timestamp, and revision chain.",
        "dedup_keys": [
            ["source", "source_document_id"],
            ["source", "isin_or_symbol", "published_at", "event_category"],
        ],
        "provenance_policy": "NO_NORMALIZED_EVENT_WITHOUT_IMMUTABLE_RAW_SOURCE_LINEAGE",
    }


def timestamp_rows() -> list[dict[str, Any]]:
    definitions = {
        "EXACT_EXCHANGE_TIMESTAMP": ("Exchange-recorded public dissemination time", True, True),
        "RELIABLE_PUBLICATION_TIMESTAMP": ("Provider time demonstrably tied to public release", True, True),
        "DATE_ONLY": ("Public or effective calendar date without release time", False, False),
        "INFERRED": ("Time estimated from indirect evidence", False, False),
        "UNKNOWN": ("No defensible public-availability time", False, False),
    }
    return [
        {
            "classification": value,
            "definition": definitions[value][0],
            "normally_eligible_for_future_research": definitions[value][1],
            "same_day_causal_usable": definitions[value][2],
        }
        for value in TIMESTAMP_CLASSIFICATIONS
    ]


def linkage_rows() -> list[dict[str, Any]]:
    return [
        {
            "classification": value,
            "definition": {
                "EXACT_ISIN": "Source ISIN maps directly to canonical historical security",
                "EXACT_SYMBOL_DATE_VALID": "Exchange symbol maps uniquely on the event publication date",
                "ALIAS_RESOLVED": "Documented historical alias resolves to canonical identity",
                "COMPANY_NAME_ONLY": "Only normalized issuer name is available",
                "AMBIGUOUS": "More than one credible security or issuer match exists",
                "UNRESOLVED": "No defensible canonical match exists",
            }[value],
            "eligible_for_95_percent_linkage_target": value
            in {"EXACT_ISIN", "EXACT_SYMBOL_DATE_VALID", "ALIAS_RESOLVED"},
        }
        for value in LINKAGE_CLASSIFICATIONS
    ]


def initial_researchable_categories() -> list[dict[str, Any]]:
    entries = [
        (1, "CORPORATE_ANNOUNCEMENTS_EXCHANGE_FILINGS", "NSE exchange dissemination metadata is the strongest official timestamp candidate; acquisition and pilot remain required."),
        (2, "FINANCIAL_RESULTS", "NSE XBRL can provide structured reported results; a point-in-time archive pilot is required and this excludes surprise."),
        (3, "INDEX_INCLUSION_EXCLUSION", "Official notices and local mappings exist, but local timestamps are date-only and need reconciliation or next-session restriction."),
        (4, "CORPORATE_ACTION_ANNOUNCEMENTS", "Local effective events are well structured, but original exchange announcement timestamps must be acquired."),
        (5, "PROMOTER_INSIDER_BULK_BLOCK", "Official archives exist; public dissemination timing and duplicate semantics need a pilot."),
        (6, "RATING_UPGRADE_DOWNGRADE", "Primary agency disclosures exist; timestamp licensing and issuer/instrument linkage remain unproven."),
    ]
    return [
        {"rank": rank, "category": category, "data_quality_basis": basis, "profitability_considered": False}
        for rank, category, basis in entries
    ]


def _write_immutable_manifest(path: Path, document: Mapping[str, Any]) -> None:
    if path.is_file():
        existing = _read_json(path)
        if existing != document:
            raise FamilyFDataReadinessImmutabilityError(
                f"Refusing to overwrite immutable Family F manifest: {path}"
            )
        return
    write_json(path, document)


def _component_paths(root: Path) -> dict[str, Path]:
    base = output_root(root)
    return {
        "source_inventory": base / "source_inventory/source_inventory_v1.json",
        "taxonomy": base / "taxonomy/catalyst_taxonomy_v1.json",
        "coverage": base / "coverage/local_coverage_v1.json",
        "licensing": base / "licensing/licensing_assessment_v1.json",
        "schema": base / "schema/normalized_catalyst_schema_v1.json",
        "risk": base / "risk/data_leakage_risk_register_v1.json",
        "acquisition": base / "acquisition_plan/acquisition_plan_v1.json",
        "pilot": base / "acquisition_plan/pilot_plan_v1.json",
    }


def _component_hashes(root: Path, paths: Mapping[str, Path]) -> dict[str, str]:
    return {
        str(path.relative_to(root)).replace("\\", "/"): file_sha256(path)
        for path in paths.values()
    }


def build_family_f_data_readiness(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    closure = verify_family_e_closure(root)
    coverage = audit_local_coverage(root)
    sources = source_rows()
    taxonomy = taxonomy_rows(coverage)
    licenses = licensing_rows(sources)
    acquisition = acquisition_rows()
    pilots = pilot_rows(acquisition)
    risks = leakage_rows()
    schema = schema_document()
    initial = initial_researchable_categories()
    paths = _component_paths(root)

    documents = {
        "source_inventory": {
            "version": "FAMILY_F_SOURCE_INVENTORY_V1",
            "source_count": len(sources),
            "existing_project_source_count": 4,
            "existing_event_dataset_count": 2,
            "sources": sources,
        },
        "taxonomy": {
            "version": "FAMILY_F_CATALYST_TAXONOMY_V1",
            "category_count": len(taxonomy),
            "categories": taxonomy,
            "weights_defined": False,
        },
        "coverage": coverage,
        "licensing": {
            "version": "FAMILY_F_LICENSING_ASSESSMENT_V1",
            "states": list(LICENSE_STATES),
            "sources": licenses,
            "required_now": [],
            "potentially_required_later": [
                "NSE licensed historical corporate announcement product if public retrieval is not reproducible",
                "Licensed historical analyst consensus only if true earnings-surprise research is later authorized",
            ],
            "purchase_or_connection_executed": False,
        },
        "schema": schema,
        "risk": {
            "version": "FAMILY_F_DATA_LEAKAGE_RISK_REGISTER_V1",
            "risks": risks,
            "immutable_raw_provenance_required": True,
        },
        "acquisition": {
            "version": "FAMILY_F_DATA_ACQUISITION_PLAN_V1",
            "status": "PLAN_ONLY_NOT_EXECUTED",
            "items": acquisition,
            "bulk_ingestion_executed": False,
        },
        "pilot": {
            "version": "FAMILY_F_SOURCE_QUALITY_PILOT_PLAN_V1",
            "status": "PLAN_ONLY_NOT_EXECUTED",
            "pilots": pilots,
        },
    }
    for name, document in documents.items():
        write_json(paths[name], document)

    manifest_path = output_root(root) / "manifests/family_f_data_readiness_manifest_v1.json"
    generated_at = utc_now()
    if manifest_path.is_file():
        generated_at = _read_json(manifest_path)["generated_at"]
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": generated_at,
        "baseline": {
            "milestone_commit": EXPECTED_MILESTONE_COMMIT,
            "family_e_closure_hash": closure["family_e_closure_hash"],
            "family_e_closure_status": closure["status"],
        },
        "scope": {
            "family_id": FAMILY_ID,
            "family_status": FAMILY_F_STATUS,
            "development_target": {"start": DEVELOPMENT_START, "end": DEVELOPMENT_END},
            "universe": "POINT_IN_TIME_NIFTY_500",
            "data_readiness_only": True,
        },
        "classifications": {
            "timestamp": list(TIMESTAMP_CLASSIFICATIONS),
            "market_timing": list(MARKET_TIMING_BUCKETS),
            "linkage": list(LINKAGE_CLASSIFICATIONS),
            "category_readiness": list(CATEGORY_READINESS_CLASSIFICATIONS),
            "licensing": list(LICENSE_STATES),
            "source_reliability": list(SOURCE_RELIABILITY_TIERS),
        },
        "component_hashes": _component_hashes(root, paths),
        "decisions": {
            "FAMILY_F_DATA_READINESS": FAMILY_F_DATA_READINESS,
            "FAMILY_F_PREREGISTRATION_READINESS": FAMILY_F_PREREGISTRATION_READINESS,
            "HISTORICAL_EARNINGS_SURPRISE_READINESS": HISTORICAL_EARNINGS_SURPRISE_READINESS,
            "initial_researchable_categories": initial,
        },
        "safety": {
            "strategy_implementation_started": False,
            "strategy_parameters_created": False,
            "experiments_created": 0,
            "backtests_run": 0,
            "bulk_historical_ingestions": 0,
            "new_providers_connected": 0,
            "validation_accessed": False,
            "strategy_v2_created": False,
            "db_migrations_created": 0,
            "live_signals": 0,
            "live_orders": 0,
            "broker_calls": 0,
            "remote_migrations": 0,
            "supabase_persistence": 0,
            "external_writes": 0,
            "credentials_written": 0,
        },
    }
    manifest = _document_with_hash(manifest_body, "family_f_data_readiness_hash")
    _write_immutable_manifest(manifest_path, manifest)

    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": generated_at,
        "family_id": FAMILY_ID,
        "family_status": FAMILY_F_STATUS,
        "roadmap_status": FAMILY_F_ROADMAP_STATUS,
        "target": manifest["scope"],
        "baseline": manifest["baseline"],
        "inventory": coverage["inventory_conclusion"],
        "local_coverage": coverage,
        "source_capability_count": len(sources),
        "taxonomy_category_count": len(taxonomy),
        "category_readiness": {row["event_category"]: row["readiness"] for row in taxonomy},
        "timestamp_policy": schema["timestamp_policy"],
        "linkage_target": ">=95% EXACT_ISIN, EXACT_SYMBOL_DATE_VALID, or ALIAS_RESOLVED",
        "readiness_target": {
            "trustworthy_point_in_time_timestamp_percent": ">=95%",
            "canonical_linkage_percent": ">=95%",
            "all_target_years_present": True,
            "stable_semantics": True,
            "acceptable_legal_licensing_use": True,
            "reproducible_retrieval": True,
        },
        "consensus": {
            "HISTORICAL_EARNINGS_SURPRISE_READINESS": HISTORICAL_EARNINGS_SURPRISE_READINESS,
            "reason": "No point-in-time historical analyst-consensus dataset exists in the project.",
        },
        "initial_researchable_categories": initial,
        "FAMILY_F_DATA_READINESS": FAMILY_F_DATA_READINESS,
        "FAMILY_F_PREREGISTRATION_READINESS": FAMILY_F_PREREGISTRATION_READINESS,
        "acquisition_plan_required": True,
        "price_volume_readiness": {
            "daily_return": "AVAILABLE",
            "daily_volume": "AVAILABLE",
            "relative_volume": "AVAILABLE",
            "point_in_time_market_membership": "AVAILABLE_WITH_DOCUMENTED_PARTIAL_HISTORY",
            "next_open_reference": "AVAILABLE",
            "five_minute_confirmation": "BOUNDED_SYMBOLS_ONLY",
            "all_nifty500_intraday": "NOT_AVAILABLE",
            "signals_run": False,
        },
        "reliability_policy": {
            "preferred_tiers": ["TIER_1_OFFICIAL", "TIER_2_PRIMARY_COMPANY", "TIER_3_LICENSED_STRUCTURED"],
            "unverified_secondary_only_signal_allowed": False,
            "independent_price_volume_validation_required_later": True,
        },
        "normalized_schema": schema,
        "revision_handling": schema["revision_policy"],
        "duplicate_handling": schema["dedup_keys"],
        "governance": manifest["safety"],
        "reports": list(REPORT_NAMES),
        "documentation": "docs/strategy-family-f-catalyst-data-readiness-v1.md",
        "roadmap": "docs/strategy-family-research-roadmap-v1.md",
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "family_f_data_readiness_hash": manifest["family_f_data_readiness_hash"],
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    report_root = root / "data/reports"
    write_json(report_root / REPORT_NAMES[0], summary)
    write_csv(report_root / REPORT_NAMES[1], sources)
    write_csv(report_root / REPORT_NAMES[2], taxonomy)
    write_csv(report_root / REPORT_NAMES[3], timestamp_rows())
    write_csv(report_root / REPORT_NAMES[4], linkage_rows())
    write_csv(report_root / REPORT_NAMES[5], licenses)
    write_csv(report_root / REPORT_NAMES[6], taxonomy)
    write_csv(report_root / REPORT_NAMES[7], acquisition)
    write_csv(report_root / REPORT_NAMES[8], risks)
    return summary


def finalize_family_f_data_readiness(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    path = root / "data/reports/family_f_data_readiness_v1_summary.json"
    summary = _read_json(path)
    summary["verification"] = {
        "backend_targeted_tests": backend_targeted_tests,
        "backend_full_tests": backend_full_tests,
        "frontend_build": frontend_build,
        "ready_for_review": all(
            value.startswith("PASS")
            for value in (backend_targeted_tests, backend_full_tests, frontend_build)
        ),
    }
    write_json(path, summary)
    return summary
