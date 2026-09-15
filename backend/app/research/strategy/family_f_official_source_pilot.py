from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

from app.research.strategy.family_a_momentum import (
    file_sha256,
    read_csv,
    write_csv,
    write_json,
)
from app.research.strategy.family_f_catalyst_data_readiness import (
    EXPECTED_FAMILY_E_CLOSURE_HASH,
    HISTORICAL_EARNINGS_SURPRISE_READINESS,
    LINKAGE_CLASSIFICATIONS,
    MARKET_TIMING_BUCKETS,
    TIMESTAMP_CLASSIFICATIONS,
    verify_family_e_closure,
)
from app.research.temporal_validation.config import canonical_hash


COMMAND = "Step 03.06 / Command 02"
COMMAND_VERSION = "FAMILY_F_OFFICIAL_SOURCE_PILOT_V1"
COMMAND_PROFILE = "CATALYST_TIMESTAMP_LINKAGE_PILOT_V1"
MANIFEST_VERSION = "FAMILY_F_OFFICIAL_SOURCE_PILOT_MANIFEST_V1"
FAMILY_ID = "FAMILY_F_CATALYST_MOMENTUM"
FAMILY_STATUS = "DATA_READINESS_ONLY"
EXPECTED_MILESTONE_COMMIT = "c2f7534761e31f53376a6d9d1275aacd2eddc985"
EXPECTED_COMMAND_01_HASH = (
    "45ce21fdbf020cd990bdd9ca727e0d278de1eb9d5132d3cba18a70fb72ca0765"
)
DEVELOPMENT_START = "2022-01-01"
DEVELOPMENT_END = "2024-12-31"
TARGET_YEARS = ("2022", "2023", "2024")
PILOT_SYMBOL_COUNT = 8
PILOT_REQUEST_PLAN_HASH = (
    "8522ea20315ca6632a75f06694c615b7dd1a0ff4526c5bddf4b78a585ca1a98d"
)

TERMS_CLASSIFICATIONS = (
    "PUBLIC_RESEARCH_USE_CLEAR",
    "PUBLIC_ACCESS_TERMS_REVIEW_REQUIRED",
    "LICENSE_REQUIRED",
    "AUTOMATION_RESTRICTED",
    "UNKNOWN",
)
SOURCE_RESULTS = (
    "PILOT_PASS",
    "PILOT_CONDITIONAL",
    "PILOT_FAIL",
    "ACCESS_RESTRICTED",
    "INCONCLUSIVE",
)
ACQUISITION_READINESS = ("YES", "CONDITIONAL", "NO")
NEXT_STAGES = (
    "HISTORICAL_ACQUISITION",
    "LICENSE_RESOLUTION",
    "SOURCE_REDESIGN",
    "DATA_BLOCKED",
    "INCONCLUSIVE",
)

SOURCE_DEFINITIONS = (
    {
        "source": "NSE_CORPORATE_ANNOUNCEMENTS",
        "source_group": "A",
        "event_category": "EXCHANGE_CORPORATE_ANNOUNCEMENTS",
        "access_path": "https://www.nseindia.com/companies-listing/corporate-filings-application?id=allAnnouncements",
        "access_method": "OFFICIAL_WEB_SEARCH_BY_SYMBOL_AND_DATE_RANGE",
    },
    {
        "source": "NSE_FINANCIAL_RESULTS_XBRL",
        "source_group": "B",
        "event_category": "REPORTED_FINANCIAL_RESULTS",
        "access_path": "https://www.nseindia.com/static/companies-listing/xbrl-information",
        "access_method": "OFFICIAL_XBRL_INDEX_BY_SYMBOL_AND_DATE_RANGE",
    },
    {
        "source": "NIFTY_INDICES_NOTICES",
        "source_group": "C",
        "event_category": "INDEX_NOTICES",
        "access_path": "https://www.niftyindices.com/press-release",
        "access_method": "OFFICIAL_NOTICE_INDEX_AND_DOCUMENT_REFERENCE",
    },
    {
        "source": "NSE_INSIDER_BULK_BLOCK_ARCHIVES",
        "source_group": "D",
        "event_category": "INSIDER_BULK_BLOCK_DISCLOSURES",
        "access_path": "https://www.nseindia.com/companies-listing/corporate-filings-insider-trading-archive-data",
        "access_method": "OFFICIAL_ARCHIVE_BY_SYMBOL_AND_DATE_RANGE",
    },
    {
        "source": "BSE_CORPORATE_ANNOUNCEMENTS",
        "source_group": "E",
        "event_category": "EXCHANGE_ANNOUNCEMENT_CROSS_CHECK",
        "access_path": "https://www.bseindia.com/corporates/ann.html",
        "access_method": "OFFICIAL_WEB_SEARCH_BY_COMPANY_OR_ISIN_AND_DATE_RANGE",
    },
    {
        "source": "SEBI_ORDERS_AND_ACTIONS",
        "source_group": "F",
        "event_category": "REGULATORY_DISCLOSURES",
        "access_path": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=2&smid=2&ssid=9",
        "access_method": "OFFICIAL_ORDER_INDEX_BY_ENTITY_AND_YEAR",
    },
    {
        "source": "ICRA_RATING_RATIONALES",
        "source_group": "G",
        "event_category": "RATING_EVENTS",
        "access_path": "https://www.icra.in/Rating/AllRatingRationales",
        "access_method": "OFFICIAL_RATIONALE_SEARCH_BY_ISSUER_AND_YEAR",
    },
    {
        "source": "CRISIL_RATING_DISCLOSURES",
        "source_group": "G",
        "event_category": "RATING_EVENTS",
        "access_path": "https://www.crisilratings.com/en/home/our-business/ratings/regulatory-disclosures.html",
        "access_method": "OFFICIAL_RATING_DISCLOSURE_SEARCH_BY_ISSUER_AND_YEAR",
    },
)

REPORT_NAMES = (
    "family_f_source_pilot_v1_summary.json",
    "family_f_source_pilot_v1_request_plan.csv",
    "family_f_source_pilot_v1_sources.csv",
    "family_f_source_pilot_v1_records.csv",
    "family_f_source_pilot_v1_timestamp_audit.csv",
    "family_f_source_pilot_v1_linkage.csv",
    "family_f_source_pilot_v1_reconciliation.csv",
    "family_f_source_pilot_v1_licensing.csv",
    "family_f_source_pilot_v1_results.csv",
    "family_f_source_pilot_v1_acquisition_candidates.csv",
)

# This fixture is a transcription of the bounded official NSE announcement-table
# inspection performed after the request plan was frozen.  It deliberately keeps
# source metadata only; there are no prices, returns, signals, or outcome labels.
NSE_ANNOUNCEMENT_FIXTURE = (
    ("Trading Window", "30-Dec-2022 13:35:02", "30-Dec-2022 13:35:09", "BHARATFORG_30122022133502_SEIntimationTradingWindowsigned.pdf"),
    ("Loss of Share Certificates", "28-Dec-2022 14:37:20", "28-Dec-2022 14:37:25", "BHARATFORG_28122022143720_LossofShareCertificates.pdf"),
    ("Press Release", "21-Dec-2022 17:07:13", "21-Dec-2022 17:07:17", "BHARATFORG_21122022170713_SEIntimationPressRelease.pdf"),
    ("Loss of Share Certificates", "15-Dec-2022 15:35:18", "15-Dec-2022 15:35:32", "BHARATFORG_15122022153518_IssueofDuplicates.pdf"),
    ("Analyst / Investor Meet", "14-Dec-2022 17:17:07", "14-Dec-2022 17:17:11", "BHARATFORG_14122022171706_SEIntimationInvestorMeet.pdf"),
    ("Transcript", "09-Dec-2022 22:30:31", "09-Dec-2022 22:30:41", "BHARATFORG_09122022223030_SEIntimationFinal.pdf"),
    ("Related Party Transaction", "29-Nov-2022 16:02:18", "29-Nov-2022 16:02:20", "BHARATFORG_29112022160218_SEIntimationRPT_Combined.pdf"),
    ("Newspaper Advertisement", "25-Nov-2022 17:42:51", "25-Nov-2022 17:42:54", "BHARATFORG_25112022174251_SEIntimationIEPFSigned.pdf"),
    ("Communication under Regulation 30", "25-Nov-2022 17:36:21", "25-Nov-2022 17:36:24", "BHARATFORG_25112022173621_SEIntimation.pdf"),
    ("Loss of Share Certificates", "25-Nov-2022 11:32:03", "25-Nov-2022 11:32:12", "BHARATFORG_25112022113203_SEIntiLoss.pdf"),
    ("Analyst / Investor Meet", "24-Nov-2022 17:16:24", "24-Nov-2022 17:16:29", "BHARATFORG_24112022171624_SEIntimationInvestorMeet.pdf"),
    ("Analyst / Investor Meet", "22-Nov-2022 18:13:06", "22-Nov-2022 18:13:12", "BHARATFORG_22112022181306_SEIntimationInvestorMeet.pdf"),
    ("Analyst / Investor Meet", "21-Nov-2022 13:11:27", "21-Nov-2022 13:11:32", "BHARATFORG_21112022131127_SEIntimationInvestorMeet.pdf"),
    ("Communication under Regulation 30", "16-Nov-2022 16:32:24", "16-Nov-2022 16:32:28", "BHARATFORG_16112022163224_SEIntimation.pdf"),
    ("Record Date", "15-Nov-2022 17:11:24", "15-Nov-2022 17:11:33", "BHARATFORG_15112022171124_SEIntimationsigned.pdf"),
    ("Transcript", "15-Nov-2022 14:24:52", "15-Nov-2022 14:24:56", "BHARATFORG_15112022142451_SEIntimationtranscriptsigned.pdf"),
    ("Newspaper Advertisement - Financial Results", "15-Nov-2022 12:20:51", "15-Nov-2022 12:20:55", "BHARATFORG_15112022122051_SEIntimationNewspaperAdvtsigned.pdf"),
    ("Loss of Share Certificates", "15-Nov-2022 11:14:51", "15-Nov-2022 11:14:54", "BHARATFORG_15112022111451_LossofShareCertinttoSE.pdf"),
    ("Analyst Call Recording", "14-Nov-2022 20:43:39", "14-Nov-2022 20:43:44", "BHARATFORG_14112022204339_SEIntimationAudiosigned.pdf"),
    ("Dividend", "14-Nov-2022 17:58:21", "14-Nov-2022 17:58:29", "BHARATFORG_14112022175821_SEIntimation_Signed.pdf"),
)


class FamilyFSourcePilotInputError(RuntimeError):
    pass


class FamilyFSourcePilotImmutabilityError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def output_root(root: Path) -> Path:
    return Path(root) / "data/research/strategy_families/family_f/source_pilot/v1"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _selection_rank(prefix: str, symbol: str, isin: str) -> str:
    value = f"{COMMAND_VERSION}|{prefix}|{symbol}|{isin}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def verify_command_01(root: Path) -> dict[str, Any]:
    path = (
        Path(root)
        / "data/research/strategy_families/family_f/data_readiness/v1/manifests/"
        "family_f_data_readiness_manifest_v1.json"
    )
    document = _read_json(path)
    body = {
        key: value
        for key, value in document.items()
        if key != "family_f_data_readiness_hash"
    }
    actual = canonical_hash(body)
    checks = {
        "stored_hash_is_canonical": document.get("family_f_data_readiness_hash")
        == actual,
        "expected_hash_matches": actual == EXPECTED_COMMAND_01_HASH,
        "command_version_matches": document.get("command_version")
        == "FAMILY_F_CATALYST_DATA_READINESS_V1",
        "data_readiness_only": document.get("scope", {}).get("data_readiness_only")
        is True,
    }
    if not all(checks.values()):
        raise FamilyFSourcePilotInputError(f"Family F Command 01 mismatch: {checks}")
    return {
        "status": "VERIFIED",
        "checks": checks,
        "family_f_data_readiness_hash": actual,
    }


def deterministic_pilot_population(root: Path) -> list[dict[str, Any]]:
    root = Path(root)
    periods_path = root / "data/reference/nifty500/history/membership_periods.csv"
    events_path = root / "data/reference/nifty500/history/membership_events.csv"
    names_path = root / "data/reference/nifty500/nifty500_constituents_normalized.csv"
    missing = [path for path in (periods_path, events_path, names_path) if not path.is_file()]
    if missing:
        raise FamilyFSourcePilotInputError(f"Missing pilot population inputs: {missing}")

    periods = read_csv(periods_path)
    events = read_csv(events_path)
    names = {
        row["trading_symbol"]: row["company_name"] for row in read_csv(names_path)
    }
    stable = [
        row
        for row in periods
        if row["valid_from"] <= DEVELOPMENT_START
        and row["valid_to"] >= DEVELOPMENT_END
        and row["isin"].strip()
    ]
    stable.sort(
        key=lambda row: (
            _selection_rank("STABLE_MULTI_YEAR", row["symbol"], row["isin"]),
            row["symbol"],
        )
    )
    selected: list[dict[str, Any]] = []
    for row in stable[:4]:
        selected.append(
            {
                "symbol": row["symbol"],
                "company": names.get(row["symbol"], row["symbol"]),
                "isin": row["isin"],
                "selection_stratum": "STABLE_MULTI_YEAR_MEMBER",
                "selection_reference_year": "2022-2024",
                "membership_valid_from": row["valid_from"],
                "membership_valid_to": row["valid_to"],
                "membership_confidence": row["source_confidence"],
                "selection_rank": _selection_rank(
                    "STABLE_MULTI_YEAR", row["symbol"], row["isin"]
                ),
            }
        )

    seen = {row["symbol"] for row in selected}
    for year in TARGET_YEARS:
        candidates = [
            row
            for row in events
            if row["announced_date"].startswith(year)
            and row["symbol"].strip()
            and row["isin"].strip()
            and row["symbol"] not in seen
        ]
        candidates.sort(
            key=lambda row: (
                _selection_rank(f"INDEX_EVENT_{year}", row["symbol"], row["isin"]),
                row["symbol"],
            )
        )
        if not candidates:
            raise FamilyFSourcePilotInputError(
                f"No eligible index-event population candidate for {year}"
            )
        row = candidates[0]
        selected.append(
            {
                "symbol": row["symbol"],
                "company": row["company_name_original"],
                "isin": row["isin"],
                "selection_stratum": "OFFICIAL_INDEX_NOTICE_EVENT",
                "selection_reference_year": year,
                "membership_valid_from": row["announced_date"],
                "membership_valid_to": row["effective_date"],
                "membership_confidence": row["mapping_confidence"],
                "selection_rank": _selection_rank(
                    f"INDEX_EVENT_{year}", row["symbol"], row["isin"]
                ),
            }
        )
        seen.add(row["symbol"])

    remaining = [
        row
        for row in events
        if DEVELOPMENT_START <= row["announced_date"] <= DEVELOPMENT_END
        and row["symbol"].strip()
        and row["isin"].strip()
        and row["symbol"] not in seen
    ]
    remaining.sort(
        key=lambda row: (
            _selection_rank("INDEX_EVENT_SUPPLEMENT", row["symbol"], row["isin"]),
            row["announced_date"],
            row["symbol"],
        )
    )
    row = remaining[0]
    selected.append(
        {
            "symbol": row["symbol"],
            "company": row["company_name_original"],
            "isin": row["isin"],
            "selection_stratum": "OFFICIAL_INDEX_NOTICE_EVENT",
            "selection_reference_year": row["announced_date"][:4],
            "membership_valid_from": row["announced_date"],
            "membership_valid_to": row["effective_date"],
            "membership_confidence": row["mapping_confidence"],
            "selection_rank": _selection_rank(
                "INDEX_EVENT_SUPPLEMENT", row["symbol"], row["isin"]
            ),
        }
    )

    if len(selected) != PILOT_SYMBOL_COUNT or len({row["symbol"] for row in selected}) != len(selected):
        raise FamilyFSourcePilotInputError("Pilot population is not exactly eight unique securities")
    return selected


def pilot_request_rows(population: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_index, source in enumerate(SOURCE_DEFINITIONS):
        for year_index, year in enumerate(TARGET_YEARS):
            security = population[(source_index * len(TARGET_YEARS) + year_index) % len(population)]
            request_id = f"FFP-{source['source_group']}-{source_index + 1:02d}-{year}"
            rows.append(
                {
                    "request_id": request_id,
                    "source": source["source"],
                    "source_group": source["source_group"],
                    "symbol": security["symbol"],
                    "company": security["company"],
                    "isin": security["isin"],
                    "target_year": year,
                    "event_category": source["event_category"],
                    "expected_query_access_path": source["access_path"],
                    "access_method": source["access_method"],
                    "bounded_request_rule": "ONE_SECURITY_ONE_YEAR_METADATA_ONLY",
                    "max_records_to_retain": 50,
                    "planned_before_network_access": True,
                }
            )
    return rows


def build_request_plan(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    command_01 = verify_command_01(root)
    family_e = verify_family_e_closure(root)
    if family_e["family_e_closure_hash"] != EXPECTED_FAMILY_E_CLOSURE_HASH:
        raise FamilyFSourcePilotInputError("Family E closure hash mismatch")
    population = deterministic_pilot_population(root)
    requests = pilot_request_rows(population)
    body = {
        "version": "FAMILY_F_PILOT_REQUEST_PLAN_V1",
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "created_before_network_access": True,
        "selection_rule": (
            "Four full-window members ranked by SHA256(command|stable|symbol|ISIN), "
            "one official index-notice security per target year ranked by SHA256, and "
            "one supplementary official index-notice security ranked by SHA256; no "
            "price or outcome field participates."
        ),
        "selection_input_hashes": {
            "data/reference/nifty500/history/membership_periods.csv": file_sha256(
                root / "data/reference/nifty500/history/membership_periods.csv"
            ),
            "data/reference/nifty500/history/membership_events.csv": file_sha256(
                root / "data/reference/nifty500/history/membership_events.csv"
            ),
            "data/reference/nifty500/nifty500_constituents_normalized.csv": file_sha256(
                root / "data/reference/nifty500/nifty500_constituents_normalized.csv"
            ),
        },
        "target_years": list(TARGET_YEARS),
        "pilot_symbol_count": len(population),
        "source_count": len(SOURCE_DEFINITIONS),
        "request_count": len(requests),
        "population": population,
        "requests": requests,
        "baseline": {
            "milestone_commit": EXPECTED_MILESTONE_COMMIT,
            "family_f_data_readiness_hash": command_01[
                "family_f_data_readiness_hash"
            ],
            "family_e_closure_hash": family_e["family_e_closure_hash"],
        },
        "safety": {
            "performance_based_selection": False,
            "network_access_executed_during_plan_creation": False,
            "bulk_history_planned": False,
            "historical_consensus_planned": False,
        },
    }
    document = dict(body)
    document["family_f_pilot_request_plan_hash"] = canonical_hash(body)
    target = output_root(root) / "request_plan/family_f_pilot_request_plan_v1.json"
    if target.exists() and _read_json(target) != document:
        raise FamilyFSourcePilotImmutabilityError(
            f"Frozen request plan differs from deterministic rebuild: {target}"
        )
    write_json(target, document)
    write_csv(root / "data/reports" / REPORT_NAMES[1], requests)
    return document


def parse_source_fixture(
    source: str, raw_records: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Normalize bounded, already-retrieved metadata fixtures without network access."""
    rows: list[dict[str, Any]] = []
    for raw in raw_records:
        row = dict(raw)
        row["source"] = source
        row.setdefault("timestamp_classification", "UNKNOWN")
        row.setdefault("linkage_classification", "UNRESOLVED")
        row.setdefault("revision_id", "")
        row.setdefault("supersedes_event_id", "")
        row.setdefault("raw_metadata", dict(raw))
        rows.append(row)
    return rows


def classify_market_timing(published_at: str, timestamp_classification: str) -> str:
    if timestamp_classification not in TIMESTAMP_CLASSIFICATIONS:
        raise ValueError(f"Unknown timestamp classification: {timestamp_classification}")
    if timestamp_classification in {"DATE_ONLY", "INFERRED", "UNKNOWN"}:
        return "DATE_ONLY_UNKNOWN_TIME"
    value = published_at.replace("Z", "+00:00")
    timestamp = datetime.fromisoformat(value)
    if timestamp.tzinfo is None:
        raise ValueError("Trusted timestamp must include an explicit timezone")
    local = timestamp.astimezone(ZoneInfo("Asia/Kolkata"))
    if local.weekday() >= 5:
        return "NON_TRADING_DAY"
    local_time = local.timetz().replace(tzinfo=None)
    if local_time < time(9, 15):
        return "PRE_OPEN"
    if local_time <= time(15, 30):
        return "DURING_MARKET"
    return "POST_CLOSE"


def classify_announcement_category(subject: str) -> str:
    """Apply a transparent keyword feasibility mapping, never a polarity label."""
    value = subject.casefold()
    rules = (
        (("order", "contract"), "ORDER_OR_CONTRACT"),
        (("board",), "BOARD_DECISION"),
        (("fund rais", "fundrais", "preferential", "rights issue"), "FUNDRAISING"),
        (("merger", "acquisition", "amalgamation"), "M_AND_A"),
        (("buyback",), "BUYBACK"),
        (("dividend",), "DIVIDEND"),
        (("split", "bonus"), "SPLIT_OR_BONUS"),
        (("regulation", "trading window", "related party"), "REGULATORY"),
    )
    for needles, category in rules:
        if any(needle in value for needle in needles):
            return category
    return "OTHER_FILING"


def _nse_timestamp(value: str) -> str:
    local = datetime.strptime(value, "%d-%b-%Y %H:%M:%S").replace(
        tzinfo=ZoneInfo("Asia/Kolkata")
    )
    return local.isoformat()


def _nse_announcement_records(retrieved_at: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (subject, received, disseminated, filename) in enumerate(
        NSE_ANNOUNCEMENT_FIXTURE, start=1
    ):
        published_at = _nse_timestamp(disseminated)
        reference = f"https://nsearchives.nseindia.com/corporate/{filename}"
        rows.append(
            {
                "pilot_record_id": f"FFP-NSE-A-2022-{index:03d}",
                "request_id": "FFP-A-01-2022",
                "source": "NSE_CORPORATE_ANNOUNCEMENTS",
                "source_group": "A",
                "source_reference": reference,
                "source_document_id": filename,
                "announcement_id": filename.rsplit(".", 1)[0],
                "filing_id": "",
                "symbol": "BHARATFORG",
                "isin": "INE465A01025",
                "company": "Bharat Forge Ltd.",
                "event_category": classify_announcement_category(subject),
                "source_event_category": "EXCHANGE_CORPORATE_ANNOUNCEMENTS",
                "subject": subject,
                "published_at": published_at,
                "published_at_asia_kolkata": published_at,
                "source_publication_field": "Exchange Dissemination Time",
                "exchange_received_at": _nse_timestamp(received),
                "exchange_disseminated_at": published_at,
                "document_timestamp": "",
                "timestamp_classification": "EXACT_EXCHANGE_TIMESTAMP",
                "timestamp_semantics_evidence": (
                    "Official table separately labels Exchange Received Time and "
                    "Exchange Dissemination Time; dissemination is the retained "
                    "public-availability field."
                ),
                "market_timing": classify_market_timing(
                    published_at, "EXACT_EXCHANGE_TIMESTAMP"
                ),
                "same_day_causal_research_ready": "YES",
                "linkage_classification": "EXACT_SYMBOL_DATE_VALID",
                "linkage_evidence": (
                    "Official NSE symbol joined to the frozen point-in-time membership "
                    "record; the source row itself does not expose ISIN."
                ),
                "stable_document_id": "YES",
                "reproducible_retrieval": "YES",
                "revision_id": "",
                "supersedes_event_id": "",
                "revision_status": "NOT_OBSERVED",
                "retrieved_at": retrieved_at,
                "raw_metadata": {
                    "subject": subject,
                    "exchange_received_time": received,
                    "exchange_dissemination_time": disseminated,
                    "attachment_filename": filename,
                },
                "provenance_retained": True,
                "text_classification_required": "YES",
            }
        )

    # A second planned year was checked through a stable official archive result,
    # but its publication semantics were not visible in the bounded response.  It
    # is retained as UNKNOWN rather than inferring time from the filename.
    filename = "SUNPHARMA_27072023180903_AnnualReportFY23.pdf"
    rows.append(
        {
            "pilot_record_id": "FFP-NSE-A-2023-001",
            "request_id": "FFP-A-01-2023",
            "source": "NSE_CORPORATE_ANNOUNCEMENTS",
            "source_group": "A",
            "source_reference": f"https://archives.nseindia.com/corporate/{filename}",
            "source_document_id": filename,
            "announcement_id": filename.rsplit(".", 1)[0],
            "filing_id": "",
            "symbol": "SUNPHARMA",
            "isin": "INE044A01036",
            "company": "Sun Pharmaceutical Industries Ltd.",
            "event_category": "OTHER_FILING",
            "source_event_category": "EXCHANGE_CORPORATE_ANNOUNCEMENTS",
            "subject": "Annual Report FY 2023",
            "published_at": "",
            "published_at_asia_kolkata": "",
            "source_publication_field": "NOT_EXPOSED_IN_BOUNDED_RESPONSE",
            "exchange_received_at": "",
            "exchange_disseminated_at": "",
            "document_timestamp": "",
            "timestamp_classification": "UNKNOWN",
            "timestamp_semantics_evidence": (
                "Stable official archive document found, but no labeled publication "
                "timestamp was retained; filename digits are not treated as evidence."
            ),
            "market_timing": "DATE_ONLY_UNKNOWN_TIME",
            "same_day_causal_research_ready": "NO",
            "linkage_classification": "EXACT_SYMBOL_DATE_VALID",
            "linkage_evidence": "Official symbol joined to the frozen point-in-time membership record.",
            "stable_document_id": "YES",
            "reproducible_retrieval": "YES",
            "revision_id": "",
            "supersedes_event_id": "",
            "revision_status": "NOT_OBSERVED",
            "retrieved_at": retrieved_at,
            "raw_metadata": {
                "subject": "Annual Report FY 2023",
                "attachment_filename": filename,
            },
            "provenance_retained": True,
            "text_classification_required": "YES",
        }
    )
    return rows


def _index_notice_records(root: Path, retrieved_at: str) -> list[dict[str, Any]]:
    population = {row["symbol"] for row in deterministic_pilot_population(root)}
    source = root / "data/reference/nifty500/history/membership_events.csv"
    matches = [
        row
        for row in read_csv(source)
        if row["symbol"] in population
        and DEVELOPMENT_START <= row["announced_date"] <= DEVELOPMENT_END
    ]
    rows: list[dict[str, Any]] = []
    for index, raw in enumerate(matches, start=1):
        filename = raw["source_reference"].rsplit("/", 1)[-1]
        rows.append(
            {
                "pilot_record_id": f"FFP-NIFTY-C-{index:03d}",
                "request_id": f"FFP-C-SUPPLEMENTAL-{raw['announced_date'][:4]}",
                "source": "NIFTY_INDICES_NOTICES",
                "source_group": "C",
                "source_reference": raw["source_reference"],
                "source_document_id": filename,
                "announcement_id": filename.rsplit(".", 1)[0],
                "filing_id": "",
                "symbol": raw["symbol"],
                "isin": raw["isin"],
                "company": raw["company_name_original"],
                "event_category": "INDEX_INCLUSION" if raw["event_type"] == "ADDED" else "INDEX_EXCLUSION",
                "source_event_category": "INDEX_NOTICES",
                "subject": raw["notes"],
                "published_at": raw["announced_date"],
                "published_at_asia_kolkata": raw["announced_date"],
                "source_publication_field": "Press-release date",
                "exchange_received_at": "",
                "exchange_disseminated_at": "",
                "document_timestamp": raw["announced_date"],
                "effective_at": raw["effective_date"],
                "timestamp_classification": "DATE_ONLY",
                "timestamp_semantics_evidence": (
                    "Official press-release archive and document provide an announcement "
                    "date distinct from the later effective date, but no time of day."
                ),
                "market_timing": "DATE_ONLY_UNKNOWN_TIME",
                "same_day_causal_research_ready": "NO",
                "linkage_classification": "EXACT_ISIN",
                "linkage_evidence": "Official notice extraction includes explicit symbol and mapped ISIN.",
                "stable_document_id": "YES",
                "reproducible_retrieval": "YES",
                "revision_id": "",
                "supersedes_event_id": "",
                "revision_status": "NOT_EXPOSED",
                "retrieved_at": retrieved_at,
                "raw_metadata": raw,
                "provenance_retained": True,
                "text_classification_required": "NO",
            }
        )
    return rows


def source_access_rows() -> list[dict[str, Any]]:
    observations = {
        "NSE_CORPORATE_ANNOUNCEMENTS": (2, 0, 1, "BOUNDED_OFFICIAL_RECORDS_RETRIEVED", "AUTOMATION_RESTRICTED", "Obtain written permission or licensed delivery before historical acquisition."),
        "NSE_FINANCIAL_RESULTS_XBRL": (0, 0, 3, "HISTORICAL_SLICE_NOT_RESOLVED", "AUTOMATION_RESTRICTED", "Resolve an authorized XBRL archive/download route and verify field semantics."),
        "NIFTY_INDICES_NOTICES": (3, 0, 0, "OFFICIAL_DATE_ONLY_DOCUMENTS_RETRIEVED", "PUBLIC_ACCESS_TERMS_REVIEW_REQUIRED", "Confirm archival research/storage terms and acquire timestamped publication metadata if available."),
        "NSE_INSIDER_BULK_BLOCK_ARCHIVES": (0, 0, 3, "ENDPOINT_VISIBLE_NO_BOUNDED_RECORDS_RETAINED", "AUTOMATION_RESTRICTED", "Obtain authorized archive access and separate transaction from dissemination timestamps."),
        "BSE_CORPORATE_ANNOUNCEMENTS": (0, 3, 0, "AUTOMATION_ACCESS_RESTRICTED", "UNKNOWN", "Resolve official access and terms; do not substitute BSE time for NSE time."),
        "SEBI_ORDERS_AND_ACTIONS": (0, 0, 3, "OFFICIAL_INDEX_VISIBLE_NO_MATCHED_RECORDS", "PUBLIC_ACCESS_TERMS_REVIEW_REQUIRED", "Review reuse terms and repeat only a bounded entity-matched pilot."),
        "ICRA_RATING_RATIONALES": (0, 0, 3, "OFFICIAL_SEARCH_VISIBLE_NO_MATCHED_RECORDS", "PUBLIC_ACCESS_TERMS_REVIEW_REQUIRED", "Review reuse terms and issuer/instrument identifier coverage."),
        "CRISIL_RATING_DISCLOSURES": (0, 3, 0, "AUTOMATION_ACCESS_RESTRICTED", "UNKNOWN", "Resolve official access and terms without bypassing controls."),
    }
    rows: list[dict[str, Any]] = []
    for definition in SOURCE_DEFINITIONS:
        successful, restricted, inconclusive, access_status, terms, action = observations[
            definition["source"]
        ]
        rows.append(
            {
                **definition,
                "priority": "TIER_1_OFFICIAL",
                "planned_requests": 3,
                "successful_requests": successful,
                "restricted_or_blocked_requests": restricted,
                "inconclusive_requests": inconclusive,
                "access_status": access_status,
                "licensing_classification": terms,
                "licensing_prerequisite": action,
                "bulk_crawl_performed": False,
                "restriction_bypassed": False,
            }
        )
    return rows


def audit_duplicates(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    primary = Counter(
        (str(row["source"]), str(row["source_document_id"])) for row in records
    )
    fallback = Counter(
        (
            str(row["source"]),
            str(row.get("isin") or row.get("symbol")),
            str(row.get("published_at", "")),
            str(row["event_category"]),
        )
        for row in records
    )
    primary_collisions = [key for key, count in primary.items() if count > 1]
    fallback_collisions = [key for key, count in fallback.items() if count > 1]
    return {
        "primary_key": ["source", "source_document_id"],
        "fallback_key": ["source", "ISIN-or-symbol", "published_at", "event_category"],
        "primary_collision_count": len(primary_collisions),
        "fallback_collision_count": len(fallback_collisions),
        "primary_collisions": primary_collisions,
        "fallback_collisions": fallback_collisions,
        "records_removed": 0,
    }


def _percent(count: int, total: int) -> float:
    return round((count / total * 100.0) if total else 0.0, 2)


def calculate_source_metrics(
    sources: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in sources:
        inspected = [row for row in records if row["source"] == source["source"]]
        total = len(inspected)
        counts = Counter(str(row["timestamp_classification"]) for row in inspected)
        linkages = Counter(str(row["linkage_classification"]) for row in inspected)
        exact = counts["EXACT_EXCHANGE_TIMESTAMP"]
        reliable = counts["RELIABLE_PUBLICATION_TIMESTAMP"]
        date_only = counts["DATE_ONLY"]
        unknown = counts["UNKNOWN"] + counts["INFERRED"]
        exact_isin = linkages["EXACT_ISIN"]
        exact_symbol = linkages["EXACT_SYMBOL_DATE_VALID"]
        alias = linkages["ALIAS_RESOLVED"]
        ambiguous = linkages["AMBIGUOUS"] + linkages["UNRESOLVED"]
        stable = sum(row["stable_document_id"] == "YES" for row in inspected)
        reproducible = sum(row["reproducible_retrieval"] == "YES" for row in inspected)
        same_day = sum(
            row["same_day_causal_research_ready"] == "YES" for row in inspected
        )
        trusted = exact + reliable
        canonical = exact_isin + exact_symbol + alias
        metrics = {
            "records_inspected": total,
            "exact_exchange_timestamp_count": exact,
            "exact_exchange_timestamp_percent": _percent(exact, total),
            "reliable_publication_timestamp_count": reliable,
            "reliable_publication_timestamp_percent": _percent(reliable, total),
            "date_only_count": date_only,
            "date_only_percent": _percent(date_only, total),
            "unknown_or_inferred_count": unknown,
            "unknown_or_inferred_percent": _percent(unknown, total),
            "trusted_publication_timestamp_percent": _percent(trusted, total),
            "same_day_causal_ready_count": same_day,
            "same_day_causal_ready_percent": _percent(same_day, total),
            "exact_isin_count": exact_isin,
            "exact_isin_percent": _percent(exact_isin, total),
            "date_valid_symbol_count": exact_symbol,
            "date_valid_symbol_percent": _percent(exact_symbol, total),
            "alias_count": alias,
            "alias_percent": _percent(alias, total),
            "ambiguous_or_unresolved_count": ambiguous,
            "ambiguous_or_unresolved_percent": _percent(ambiguous, total),
            "canonical_linkage_percent": _percent(canonical, total),
            "stable_document_id_count": stable,
            "stable_document_id_percent": _percent(stable, total),
            "reproducible_retrieval_count": reproducible,
            "reproducible_retrieval_percent": _percent(reproducible, total),
        }
        rows.append({**source, **metrics})
    return rows


def evaluate_source_result(row: Mapping[str, Any]) -> str:
    if int(row["records_inspected"]) == 0:
        if row["access_status"] == "AUTOMATION_ACCESS_RESTRICTED":
            return "ACCESS_RESTRICTED"
        return "INCONCLUSIVE"
    technical_pass = all(
        float(row[field]) >= 95.0
        for field in (
            "trusted_publication_timestamp_percent",
            "canonical_linkage_percent",
            "stable_document_id_percent",
            "reproducible_retrieval_percent",
        )
    )
    if not technical_pass:
        return "PILOT_FAIL"
    if row["licensing_classification"] == "PUBLIC_RESEARCH_USE_CLEAR":
        return "PILOT_PASS"
    return "PILOT_CONDITIONAL"


def _aggregate_metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    synthetic_source = {
        "source": "ALL_SOURCES",
        "access_status": "MIXED",
        "licensing_classification": "MIXED",
    }
    metrics = calculate_source_metrics([synthetic_source], [
        {**row, "source": "ALL_SOURCES"} for row in records
    ])[0]
    return {
        key: value
        for key, value in metrics.items()
        if key not in synthetic_source
    }


def _reconciliation_rows(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in records:
        if not row.get("exchange_received_at") or not row.get("exchange_disseminated_at"):
            continue
        received = datetime.fromisoformat(str(row["exchange_received_at"]))
        disseminated = datetime.fromisoformat(str(row["exchange_disseminated_at"]))
        delta = int((disseminated - received).total_seconds())
        rows.append(
            {
                "pilot_record_id": row["pilot_record_id"],
                "source_a": row["source"],
                "timestamp_a_field": "Exchange Received Time",
                "timestamp_a": row["exchange_received_at"],
                "source_b": row["source"],
                "timestamp_b_field": "Exchange Dissemination Time",
                "timestamp_b": row["exchange_disseminated_at"],
                "difference_seconds": delta,
                "finding": "EXACT_MATCH" if delta == 0 else "SMALL_EXPLAINABLE_DIFFERENCE",
                "retained_publication_timestamp": row["exchange_disseminated_at"],
                "reason": "Receipt and public dissemination are distinct source semantics; the later dissemination time is retained.",
            }
        )
    rows.append(
        {
            "pilot_record_id": "CROSS_SOURCE-BSE",
            "source_a": "NSE_CORPORATE_ANNOUNCEMENTS",
            "timestamp_a_field": "Exchange Dissemination Time",
            "timestamp_a": "AVAILABLE_IN_BOUNDED_NSE_SAMPLE",
            "source_b": "BSE_CORPORATE_ANNOUNCEMENTS",
            "timestamp_b_field": "NOT_RETRIEVED",
            "timestamp_b": "",
            "difference_seconds": "",
            "finding": "UNKNOWN_SEMANTICS",
            "retained_publication_timestamp": "NSE_SOURCE_SPECIFIC_ONLY",
            "reason": "BSE access was restricted; no cross-exchange timestamp substitution was made.",
        }
    )
    return rows


def _licensing_rows(sources: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "source": row["source"],
            "classification": row["licensing_classification"],
            "access_status": row["access_status"],
            "evidence": (
                "NSE Terms of Use prohibit systematic or automated data collection; "
                "NSE sources therefore require permission/licensed delivery."
                if row["source"].startswith("NSE_")
                else "Public visibility did not establish permission for historical automated acquisition."
            ),
            "required_action": row["licensing_prerequisite"],
            "public_visibility_treated_as_permission": False,
        }
        for row in sources
    ]


def _acquisition_candidates(result_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        row
        for row in result_rows
        if row["pilot_result"] in {"PILOT_PASS", "PILOT_CONDITIONAL"}
    ]
    candidates.sort(
        key=lambda row: (
            -float(row["trusted_publication_timestamp_percent"]),
            -float(row["canonical_linkage_percent"]),
            -float(row["reproducible_retrieval_percent"]),
            str(row["source"]),
        )
    )
    rows: list[dict[str, Any]] = []
    for rank, row in enumerate(candidates, start=1):
        rows.append(
            {
                "rank": rank,
                "source": row["source"],
                "event_category": row["event_category"],
                "pilot_result": row["pilot_result"],
                "ranking_basis": "TIMESTAMP_IDENTITY_OFFICIAL_REPRODUCIBILITY_COVERAGE_TERMS",
                "profitability_considered": False,
                "target_date_range": f"{DEVELOPMENT_START} through {DEVELOPMENT_END}",
                "required_fields": [
                    "source_document_id", "source_reference", "symbol", "ISIN",
                    "subject", "exchange_received_at", "exchange_disseminated_at",
                    "revision_id", "retrieved_at", "raw_metadata",
                ],
                "expected_identifiers": ["source_document_id", "NSE symbol", "ISIN through date-valid membership join"],
                "timestamp_field": "Exchange Dissemination Time",
                "identity_mapping": "Official symbol -> date-valid frozen membership -> ISIN",
                "revision_handling": "Retain originals and revisions separately; link only explicit supersessions.",
                "request_strategy": "Authorized bounded pagination by security and date range; checkpoint and resume.",
                "rate_limit_policy": "Honor published limits and server backoff; no bypass or parallel bulk crawl.",
                "raw_storage_design": "Immutable response/document plus retrieval metadata and content hash.",
                "normalization_design": "Append-only normalized event rows retaining source-specific timestamps and raw lineage.",
                "licensing_prerequisite": row["licensing_prerequisite"],
            }
        )
    return rows


def _component_paths(root: Path) -> dict[str, Path]:
    base = output_root(root)
    return {
        "request_plan": base / "request_plan/family_f_pilot_request_plan_v1.json",
        "access_observations": base / "raw_samples/official_source_access_observations_v1.json",
        "raw_nse_fixture": base / "raw_samples/nse_announcements_bounded_metadata_v1.json",
        "normalized_records": base / "normalized_samples/family_f_normalized_records_v1.json",
        "timestamp_audit": base / "timestamp_audit/timestamp_semantic_audit_v1.json",
        "linkage": base / "linkage/canonical_linkage_audit_v1.json",
        "reconciliation": base / "reconciliation/timestamp_reconciliation_v1.json",
        "licensing": base / "licensing/source_licensing_assessment_v1.json",
        "results": base / "results/source_category_results_v1.json",
        "acquisition_plan": base / "results/acquisition_plan_update_v1.json",
    }


def _write_immutable_manifest(path: Path, document: Mapping[str, Any]) -> None:
    if path.is_file():
        if _read_json(path) != document:
            raise FamilyFSourcePilotImmutabilityError(
                f"Refusing to overwrite immutable Family F source-pilot manifest: {path}"
            )
        return
    write_json(path, document)


def build_family_f_official_source_pilot(root: Path) -> dict[str, Any]:
    root = Path(root).resolve()
    request_plan = build_request_plan(root)
    if request_plan["family_f_pilot_request_plan_hash"] != PILOT_REQUEST_PLAN_HASH:
        raise FamilyFSourcePilotInputError("Frozen pilot request-plan hash mismatch")
    command_01 = verify_command_01(root)
    family_e = verify_family_e_closure(root)
    manifest_path = output_root(root) / "manifests/family_f_official_source_pilot_manifest_v1.json"
    generated_at = _read_json(manifest_path)["generated_at"] if manifest_path.is_file() else utc_now()

    sources = source_access_rows()
    records = _nse_announcement_records(generated_at) + _index_notice_records(root, generated_at)
    metrics = calculate_source_metrics(sources, records)
    results = [{**row, "pilot_result": evaluate_source_result(row)} for row in metrics]
    duplicates = audit_duplicates(records)
    reconciliations = _reconciliation_rows(records)
    licensing = _licensing_rows(sources)
    candidates = _acquisition_candidates(results)
    aggregate = _aggregate_metrics(records)
    conditional = [row for row in results if row["pilot_result"] == "PILOT_CONDITIONAL"]
    passes = [row for row in results if row["pilot_result"] == "PILOT_PASS"]
    readiness = "YES" if passes else "CONDITIONAL" if conditional else "NO"
    next_stage = (
        "HISTORICAL_ACQUISITION" if passes else "LICENSE_RESOLUTION" if conditional else "SOURCE_REDESIGN"
    )

    paths = _component_paths(root)
    documents = {
        "access_observations": {
            "version": "FAMILY_F_OFFICIAL_SOURCE_ACCESS_OBSERVATIONS_V1",
            "bounded_pilot": True,
            "planned_request_count": 24,
            "successful_request_count": sum(row["successful_requests"] for row in sources),
            "restricted_or_blocked_request_count": sum(row["restricted_or_blocked_requests"] for row in sources),
            "inconclusive_request_count": sum(row["inconclusive_requests"] for row in sources),
            "sources": sources,
        },
        "raw_nse_fixture": {
            "version": "FAMILY_F_NSE_BOUNDED_RAW_METADATA_V1",
            "source": "NSE_CORPORATE_ANNOUNCEMENTS",
            "record_count": len(NSE_ANNOUNCEMENT_FIXTURE),
            "records": [
                {
                    "subject": subject,
                    "exchange_received_time": received,
                    "exchange_dissemination_time": disseminated,
                    "attachment_filename": filename,
                }
                for subject, received, disseminated, filename in NSE_ANNOUNCEMENT_FIXTURE
            ],
        },
        "normalized_records": {
            "version": "FAMILY_F_NORMALIZED_SOURCE_PILOT_RECORDS_V1",
            "record_count": len(records),
            "records": records,
        },
        "timestamp_audit": {
            "version": "FAMILY_F_TIMESTAMP_SEMANTIC_AUDIT_V1",
            "classifications": list(TIMESTAMP_CLASSIFICATIONS),
            "market_timing_buckets": list(MARKET_TIMING_BUCKETS),
            "aggregate_metrics": aggregate,
            "records": [
                {
                    key: row.get(key, "")
                    for key in (
                        "pilot_record_id", "source", "source_publication_field", "published_at",
                        "timestamp_classification", "timestamp_semantics_evidence", "market_timing",
                        "same_day_causal_research_ready",
                    )
                }
                for row in records
            ],
        },
        "linkage": {
            "version": "FAMILY_F_CANONICAL_LINKAGE_AUDIT_V1",
            "classifications": list(LINKAGE_CLASSIFICATIONS),
            "aggregate_metrics": aggregate,
            "records": [
                {
                    key: row.get(key, "")
                    for key in (
                        "pilot_record_id", "source", "symbol", "isin",
                        "linkage_classification", "linkage_evidence",
                    )
                }
                for row in records
            ],
        },
        "reconciliation": {
            "version": "FAMILY_F_TIMESTAMP_RECONCILIATION_V1",
            "findings": reconciliations,
            "silent_earlier_timestamp_selection": False,
        },
        "licensing": {
            "version": "FAMILY_F_SOURCE_LICENSING_ASSESSMENT_V1",
            "classifications": list(TERMS_CLASSIFICATIONS),
            "sources": licensing,
            "subscription_purchased": False,
        },
        "results": {
            "version": "FAMILY_F_SOURCE_CATEGORY_RESULTS_V1",
            "thresholds_percent": {
                "trusted_publication_timestamp": 95,
                "canonical_linkage": 95,
                "stable_document_identity": 95,
                "reproducible_retrieval": 95,
            },
            "allowed_results": list(SOURCE_RESULTS),
            "results": results,
            "duplicate_audit": duplicates,
            "revision_findings": {
                "explicit_revision_records_observed": 0,
                "explicit_supersession_links_observed": 0,
                "finding": "REVISION_LINEAGE_NOT_EXPOSED_IN_RETAINED_METADATA",
                "policy": "Retain original and revision timing separately whenever explicitly exposed.",
            },
        },
        "acquisition_plan": {
            "version": "FAMILY_F_HISTORICAL_ACQUISITION_PLAN_UPDATE_V1",
            "status": "PLAN_ONLY_NOT_EXECUTED",
            "FAMILY_F_HISTORICAL_ACQUISITION_READINESS": readiness,
            "FAMILY_F_NEXT_STAGE": next_stage,
            "target_date_range": {"start": DEVELOPMENT_START, "end": DEVELOPMENT_END},
            "candidates": candidates,
            "bulk_historical_ingestion_executed": False,
        },
    }
    for name, document in documents.items():
        write_json(paths[name], document)

    component_hashes = {
        str(path.relative_to(root)).replace("\\", "/"): file_sha256(path)
        for path in paths.values()
    }
    manifest_body = {
        "manifest_version": MANIFEST_VERSION,
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": generated_at,
        "baseline": {
            "milestone_commit": EXPECTED_MILESTONE_COMMIT,
            "family_f_data_readiness_hash": command_01["family_f_data_readiness_hash"],
            "family_e_closure_hash": family_e["family_e_closure_hash"],
        },
        "scope": {
            "family_id": FAMILY_ID,
            "family_status": FAMILY_STATUS,
            "data_readiness_only": True,
            "pilot_symbol_count": len(request_plan["population"]),
            "target_years": list(TARGET_YEARS),
            "source_groups_attempted": list(SOURCE_DEFINITIONS),
        },
        "request_plan": {
            "request_count": request_plan["request_count"],
            "family_f_pilot_request_plan_hash": PILOT_REQUEST_PLAN_HASH,
            "created_before_network_access": True,
        },
        "component_hashes": component_hashes,
        "decisions": {
            "HISTORICAL_EARNINGS_SURPRISE_READINESS": HISTORICAL_EARNINGS_SURPRISE_READINESS,
            "FAMILY_F_HISTORICAL_ACQUISITION_READINESS": readiness,
            "FAMILY_F_NEXT_STAGE": next_stage,
            "FAMILY_F_PREREGISTRATION_READINESS": "NO",
        },
        "safety": {
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
        },
    }
    manifest = dict(manifest_body)
    manifest["family_f_source_pilot_hash"] = canonical_hash(manifest_body)
    _write_immutable_manifest(manifest_path, manifest)

    report_root = root / "data/reports"
    timestamp_rows = [
        {
            key: row.get(key, "")
            for key in (
                "pilot_record_id", "source", "published_at", "source_publication_field",
                "timestamp_classification", "timestamp_semantics_evidence", "market_timing",
                "same_day_causal_research_ready",
            )
        }
        for row in records
    ]
    linkage_rows = [
        {
            key: row.get(key, "")
            for key in (
                "pilot_record_id", "source", "symbol", "isin", "linkage_classification",
                "linkage_evidence",
            )
        }
        for row in records
    ]
    write_csv(report_root / REPORT_NAMES[1], request_plan["requests"])
    write_csv(report_root / REPORT_NAMES[2], metrics)
    write_csv(report_root / REPORT_NAMES[3], records)
    write_csv(report_root / REPORT_NAMES[4], timestamp_rows)
    write_csv(report_root / REPORT_NAMES[5], linkage_rows)
    write_csv(report_root / REPORT_NAMES[6], reconciliations)
    write_csv(report_root / REPORT_NAMES[7], licensing)
    write_csv(report_root / REPORT_NAMES[8], results)
    write_csv(report_root / REPORT_NAMES[9], candidates)

    summary = {
        "command": COMMAND,
        "command_version": COMMAND_VERSION,
        "command_profile": COMMAND_PROFILE,
        "generated_at": generated_at,
        "family_id": FAMILY_ID,
        "family_status": FAMILY_STATUS,
        "baseline": manifest["baseline"],
        "pilot_population": request_plan["population"],
        "pilot_symbol_count": len(request_plan["population"]),
        "pilot_years": list(TARGET_YEARS),
        "source_group_count": len(SOURCE_DEFINITIONS),
        "source_groups_attempted": [row["source"] for row in SOURCE_DEFINITIONS],
        "request_count": request_plan["request_count"],
        "successful_source_requests": documents["access_observations"]["successful_request_count"],
        "restricted_or_blocked_requests": documents["access_observations"]["restricted_or_blocked_request_count"],
        "inconclusive_requests": documents["access_observations"]["inconclusive_request_count"],
        "total_records_inspected": len(records),
        "aggregate_metrics": aggregate,
        "source_metrics": metrics,
        "source_results": results,
        "timestamp_reconciliation_findings": reconciliations,
        "revision_findings": documents["results"]["revision_findings"],
        "duplicate_findings": duplicates,
        "TEXT_CLASSIFICATION_REQUIRED": "YES",
        "HISTORICAL_EARNINGS_SURPRISE_READINESS": HISTORICAL_EARNINGS_SURPRISE_READINESS,
        "FAMILY_F_HISTORICAL_ACQUISITION_READINESS": readiness,
        "FAMILY_F_NEXT_STAGE": next_stage,
        "FAMILY_F_PREREGISTRATION_READINESS": "NO",
        "acquisition_candidates": candidates,
        "family_f_pilot_request_plan_hash": PILOT_REQUEST_PLAN_HASH,
        "family_f_source_pilot_hash": manifest["family_f_source_pilot_hash"],
        "manifest": str(manifest_path.relative_to(root)).replace("\\", "/"),
        "reports": list(REPORT_NAMES),
        "documentation": "docs/strategy-family-f-official-source-pilot-v1.md",
        "safety": manifest["safety"],
        "verification": {
            "backend_targeted_tests": "NOT_RUN",
            "backend_full_tests": "NOT_RUN",
            "frontend_build": "NOT_RUN",
            "ready_for_review": False,
        },
    }
    write_json(report_root / REPORT_NAMES[0], summary)
    return summary


def finalize_family_f_official_source_pilot(
    root: Path,
    *,
    backend_targeted_tests: str,
    backend_full_tests: str,
    frontend_build: str,
) -> dict[str, Any]:
    root = Path(root).resolve()
    path = root / "data/reports/family_f_source_pilot_v1_summary.json"
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


__all__ = [
    "COMMAND_VERSION",
    "COMMAND_PROFILE",
    "MANIFEST_VERSION",
    "PILOT_REQUEST_PLAN_HASH",
    "TERMS_CLASSIFICATIONS",
    "SOURCE_RESULTS",
    "build_request_plan",
    "deterministic_pilot_population",
    "parse_source_fixture",
    "classify_market_timing",
    "classify_announcement_category",
    "audit_duplicates",
    "calculate_source_metrics",
    "evaluate_source_result",
    "source_access_rows",
    "build_family_f_official_source_pilot",
    "finalize_family_f_official_source_pilot",
]
