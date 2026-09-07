from __future__ import annotations

import csv
import html
import json
import re
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from app.services.nifty500_acquisition import (
    NIFTY500_INDEX_NAME,
    NIFTY500_SOURCE_URL,
    Nifty500Constituent,
    download_nifty500_source,
    normalize_nifty500_constituents,
)

PRESS_RELEASE_INDEX_URL = "https://www.niftyindices.com/press-release"
PRESS_RELEASE_BASE_URL = "https://www.niftyindices.com"
REBALANCING_SCHEDULE_URL = "https://www.niftyindices.com/resources/index-rebalancing-schedule"
TARGET_REVIEW_MONTHS = (3, 9)
DEFAULT_HISTORY_DIR = Path(__file__).resolve().parents[3] / "data" / "reference" / "nifty500" / "history"

CURRENT_SNAPSHOT_FIELDS = [
    "symbol",
    "company_name",
    "isin",
    "industry",
    "sector",
    "membership_start",
    "source",
    "source_date",
]

MEMBERSHIP_EVENT_FIELDS = [
    "index_name",
    "company_name_original",
    "company_name_normalized",
    "symbol",
    "isin",
    "event_type",
    "announced_date",
    "effective_date",
    "source_document",
    "source_reference",
    "mapping_method",
    "mapping_confidence",
    "extraction_confidence",
    "review_status",
    "notes",
]

MEMBERSHIP_PERIOD_FIELDS = [
    "index_name",
    "symbol",
    "isin",
    "valid_from",
    "valid_to",
    "reconstruction_method",
    "source_confidence",
    "provenance",
]

SOURCE_MANIFEST_FIELDS = [
    "filename",
    "source_url",
    "published_date",
    "document_type",
    "title",
    "contains_nifty500_changes",
    "can_parse_automatically",
    "parse_status",
    "parsed_event_count",
    "notes",
]

EVENT_SUMMARY_FIELDS = [
    "cycle",
    "effective_date",
    "source_documents",
    "additions",
    "removals",
    "unresolved_rows",
    "review_status",
]

MANUAL_REVIEW_FIELDS = [
    "source_document",
    "page_section",
    "issue",
    "suspected_event_company",
    "required_action",
    "confidence",
]

IDENTITY_ALIAS_FIELDS = [
    "original_symbol",
    "canonical_symbol",
    "original_company_name",
    "canonical_instrument_id",
    "mapping_reason",
    "evidence_reference",
    "confidence",
]

RECONCILIATION_FIELDS = [
    "effective_date",
    "count_before",
    "additions",
    "removals",
    "expected_after",
    "actual_after",
    "difference",
    "applied_to_reconstruction",
    "notes",
]

LIFECYCLE_ANOMALY_FIELDS = [
    "symbol",
    "canonical_symbol",
    "event_type",
    "effective_date",
    "source_document",
    "issue",
    "notes",
]


CONTROLLED_IDENTITY_ALIASES = [
    {
        "original_symbol": "AKZOINDIA",
        "canonical_symbol": "JSWDULUX",
        "original_company_name": "Akzo Nobel India Ltd.",
        "canonical_instrument_id": "INE133A01011",
        "mapping_reason": "Official Nifty 500 lifecycle uses AKZOINDIA before the current constituent snapshot lists JSW Dulux Ltd. with the same exchange instrument identity.",
        "evidence_reference": "data/reference/nifty500/history/raw/ind_prs22082025.pdf; data/reference/nifty500/current/nifty500_constituents_normalized.csv",
        "confidence": "HIGH",
    },
    {
        "original_symbol": "GET&D",
        "canonical_symbol": "GVT&D",
        "original_company_name": "GE T&D India Ltd.",
        "canonical_instrument_id": "INE200A01026",
        "mapping_reason": "Official Nifty 500 lifecycle uses GET&D before the current constituent snapshot lists GE Vernova T&D India Ltd. as GVT&D.",
        "evidence_reference": "data/reference/nifty500/history/raw/ind_prs23082024.pdf; data/reference/nifty500/current/nifty500_constituents_normalized.csv",
        "confidence": "HIGH",
    },
    {
        "original_symbol": "GMRINFRA",
        "canonical_symbol": "GMRAIRPORT",
        "original_company_name": "GMR Infrastructure Ltd.",
        "canonical_instrument_id": "INE776C01039",
        "mapping_reason": "Official Nifty 500 lifecycle uses GMRINFRA before the current constituent snapshot lists GMR Airports Ltd. as GMRAIRPORT.",
        "evidence_reference": "data/reference/nifty500/history/raw/ind_prs05042022.pdf; data/reference/nifty500/current/nifty500_constituents_normalized.csv",
        "confidence": "HIGH",
    },
    {
        "original_symbol": "HBLPOWER",
        "canonical_symbol": "HBLENGINE",
        "original_company_name": "HBL Power Systems Ltd.",
        "canonical_instrument_id": "INE292B01021",
        "mapping_reason": "Official Nifty 500 lifecycle uses HBLPOWER before the current constituent snapshot lists HBL Engineering Ltd. as HBLENGINE.",
        "evidence_reference": "data/reference/nifty500/history/raw/ind_prs28022024.pdf; data/reference/nifty500/current/nifty500_constituents_normalized.csv",
        "confidence": "HIGH",
    },
    {
        "original_symbol": "MFL",
        "canonical_symbol": "EPIGRAL",
        "original_company_name": "Meghmani Finechem Ltd.",
        "canonical_instrument_id": "",
        "mapping_reason": "Official Nifty 500 lifecycle adds Meghmani Finechem Ltd. as MFL and later removes Epigral Ltd.; treated as one canonical identity for lifecycle counting.",
        "evidence_reference": "data/reference/nifty500/history/raw/ind_prs17022023_1.pdf; data/reference/nifty500/history/raw/ind_prs28022024.pdf",
        "confidence": "MEDIUM",
    },
    {
        "original_symbol": "SWANENERGY",
        "canonical_symbol": "SWANCORP",
        "original_company_name": "Swan Energy Ltd.",
        "canonical_instrument_id": "INE665A01038",
        "mapping_reason": "Official Nifty 500 lifecycle uses SWANENERGY before the current constituent snapshot lists Swan Corp Ltd. as SWANCORP.",
        "evidence_reference": "data/reference/nifty500/history/raw/ind_prs01092022.pdf; data/reference/nifty500/current/nifty500_constituents_normalized.csv",
        "confidence": "HIGH",
    },
    {
        "original_symbol": "ZOMATO",
        "canonical_symbol": "ETERNAL",
        "original_company_name": "Zomato Ltd.",
        "canonical_instrument_id": "INE758T01015",
        "mapping_reason": "Official Nifty 500 lifecycle uses ZOMATO before the current constituent snapshot lists Eternal Ltd. as ETERNAL.",
        "evidence_reference": "data/reference/nifty500/history/raw/ind_prs24022022_1.pdf; data/reference/nifty500/current/nifty500_constituents_normalized.csv",
        "confidence": "HIGH",
    },
]

SUPERSEDED_SOURCE_NOTES = {
    "ind_prs23082021.pdf": "Visually reviewed pages 1, 3 and 4. The PDF contains 23 Nifty 500 exclusions and 23 inclusions effective September 30, 2021, but the later official September 15, 2021 release states the August 23 REIT/InvIT inclusions were revoked and the earlier replacement list stands replaced. Events from this superseded document are not applied.",
}

SPECIAL_CORPORATE_ACTION_SOURCES = {
    "ind_prs03092026.pdf": {
        "symbol": "DUMMYHEG",
        "company_name_original": "Dummy HEG Ltd.",
        "company_name_normalized": "DUMMY HEG",
        "isin": "DUM545A01024",
        "effective_date": date(2026, 9, 7),
        "notes": "Official corporate-action adjustment for HEG Ltd. says the demerged entity HEG Graphite Ltd. with dummy symbol DUMMYHEG shall be included in Nifty 500 at zero price effective September 07, 2026.",
    },
}


@dataclass(frozen=True, slots=True)
class IndexMembershipEvent:
    index_name: str
    company_name_original: str
    company_name_normalized: str
    symbol: str
    isin: str
    event_type: str
    announced_date: date | None
    effective_date: date
    source_document: str
    source_reference: str
    mapping_method: str
    mapping_confidence: str
    extraction_confidence: str
    review_status: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class IndexMembershipPeriod:
    index_name: str
    symbol: str
    isin: str
    valid_from: date | None
    valid_to: date | None
    reconstruction_method: str
    source_confidence: str
    provenance: str


@dataclass(frozen=True, slots=True)
class OfficialMembershipSource:
    title: str
    url: str
    source_document: str
    announced_date: date | None
    filename: str = ""
    document_type: str = "PDF"
    parse_status: str = "DISCOVERED"
    contains_nifty500_changes: bool = False
    can_parse_automatically: bool = False
    parsed_event_count: int = 0
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ManualReviewItem:
    source_document: str
    page_section: str
    issue: str
    suspected_event_company: str
    required_action: str
    confidence: str


@dataclass(frozen=True, slots=True)
class ParsedDocumentResult:
    source: OfficialMembershipSource
    events: tuple[IndexMembershipEvent, ...]
    manual_review_items: tuple[ManualReviewItem, ...]


@dataclass(frozen=True, slots=True)
class MembershipQueryResult:
    as_of_date: date
    membership_status: str
    source_confidence: str
    member_count: int
    symbols: tuple[str, ...]
    provenance_summary: str
    earliest_reconstructable_date: date | None
    latest_reconstructable_date: date | None
    reconstructed_from_official_events: bool


def build_membership_foundation(
    *,
    output_dir: Path,
    target_start_date: date | None = None,
    target_end_date: date | None = None,
    max_press_release_sources: int | None = None,
    download_source_documents: bool = True,
    refresh_press_release_index: bool = False,
    request_delay_seconds: float = 0.05,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    target_end_date = target_end_date or datetime.now().date()
    target_start_date = target_start_date or subtract_years(target_end_date, 5)

    reference_dir = output_dir / "reference" / "nifty500"
    current_dir = reference_dir / "current"
    history_dir = reference_dir / "history"
    raw_history_dir = history_dir / "raw"
    reports_dir = output_dir / "reports"
    docs_dir = output_dir.parent / "docs" if output_dir.name == "data" else output_dir / "docs"

    raw_csv, source_metadata = download_nifty500_source(timeout_seconds=timeout_seconds)
    constituents = normalize_nifty500_constituents(
        raw_csv,
        source_date=source_metadata["source_date"],
        source_url=source_metadata["source_url"],
    )
    write_current_snapshot(
        raw_csv=raw_csv,
        constituents=constituents,
        source_metadata=source_metadata,
        current_dir=current_dir,
    )

    discovered_sources = discover_historical_membership_sources(
        raw_history_dir=raw_history_dir,
        target_start_date=target_start_date,
        target_end_date=target_end_date,
        max_sources=max_press_release_sources,
        download_documents=download_source_documents,
        refresh_index=refresh_press_release_index,
        request_delay_seconds=request_delay_seconds,
        timeout_seconds=timeout_seconds,
    )
    parsed_results = [
        parse_membership_source(source, constituents=constituents)
        for source in discovered_sources
    ]
    parsed_sources = [result.source for result in parsed_results]
    manual_review_items = [
        item for result in parsed_results for item in result.manual_review_items
    ]
    extracted_events = [
        event for result in parsed_results for event in result.events
    ]
    identity_aliases = identity_alias_rows()
    current_events = current_snapshot_events(constituents, source_metadata=source_metadata)
    events = dedupe_events([*current_events, *extracted_events])
    periods, reconstruction = reconstruct_membership_periods(
        current_constituents=constituents,
        events=events,
        snapshot_date=date.fromisoformat(source_metadata["source_date"]),
        target_start_date=target_start_date,
        target_end_date=target_end_date,
        identity_aliases=identity_aliases,
    )
    reconciliation_rows = build_membership_reconciliation_rows(
        events=events,
        periods=periods,
        reconstruction=reconstruction,
        target_start_date=target_start_date,
        target_end_date=target_end_date,
    )
    review_cycles = build_review_cycle_coverage(
        target_start_date=target_start_date,
        target_end_date=target_end_date,
        sources=parsed_sources,
        events=events,
        manual_review_items=manual_review_items,
    )
    coverage = build_membership_coverage(
        events=events,
        periods=periods,
        sources=parsed_sources,
        manual_review_items=manual_review_items,
        constituents=constituents,
        source_metadata=source_metadata,
        reconstruction=reconstruction,
        review_cycles=review_cycles,
        identity_aliases=identity_aliases,
        reconciliation_rows=reconciliation_rows,
        target_start_date=target_start_date,
        target_end_date=target_end_date,
    )

    history_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    write_csv(history_dir / "membership_events.csv", [event_row(event) for event in events], MEMBERSHIP_EVENT_FIELDS)
    write_csv(history_dir / "membership_periods.csv", [period_row(period) for period in periods], MEMBERSHIP_PERIOD_FIELDS)
    write_csv(history_dir / "membership_source_manifest.csv", [source_manifest_row(source) for source in parsed_sources], SOURCE_MANIFEST_FIELDS)
    write_csv(history_dir / "membership_sources.csv", [source_manifest_row(source) for source in parsed_sources], SOURCE_MANIFEST_FIELDS)
    write_csv(history_dir / "membership_identity_aliases.csv", identity_aliases, IDENTITY_ALIAS_FIELDS)
    write_csv(reports_dir / "nifty500_membership_events_summary.csv", event_summary_rows(events, manual_review_items), EVENT_SUMMARY_FIELDS)
    write_csv(reports_dir / "nifty500_membership_manual_review.csv", [asdict(item) for item in manual_review_items], MANUAL_REVIEW_FIELDS)
    write_csv(reports_dir / "nifty500_membership_reconciliation.csv", reconciliation_rows, RECONCILIATION_FIELDS)
    coverage_path = history_dir / "membership_coverage.json"
    coverage_path.write_text(json.dumps(json_safe(coverage), indent=2), encoding="utf-8")
    reports_path = reports_dir / "nifty500_membership_coverage.json"
    reports_path.write_text(json.dumps(json_safe(coverage), indent=2), encoding="utf-8")
    reconciliation_path = reports_dir / "nifty500_membership_reconciliation.json"
    reconciliation_path.write_text(json.dumps(json_safe(coverage["reconciliation"]), indent=2), encoding="utf-8")
    write_membership_markdown_report(
        coverage=coverage,
        path=docs_dir / "nifty500-point-in-time-membership.md",
    )
    write_membership_reconciliation_report(
        coverage=coverage,
        path=docs_dir / "nifty500-membership-reconciliation.md",
    )
    return coverage


def write_current_snapshot(
    *,
    raw_csv: str,
    constituents: Sequence[Nifty500Constituent],
    source_metadata: dict[str, Any],
    current_dir: Path,
) -> None:
    current_dir.mkdir(parents=True, exist_ok=True)
    (current_dir / "nifty500_constituents_raw.csv").write_text(raw_csv, encoding="utf-8")
    rows = [
        {
            "symbol": constituent.trading_symbol,
            "company_name": constituent.company_name,
            "isin": constituent.isin,
            "industry": constituent.industry,
            "sector": constituent.sector,
            "membership_start": "",
            "source": constituent.source,
            "source_date": constituent.source_date,
        }
        for constituent in constituents
    ]
    write_csv(current_dir / "nifty500_constituents_normalized.csv", rows, CURRENT_SNAPSHOT_FIELDS)
    (current_dir / "nifty500_source_metadata.json").write_text(
        json.dumps(json_safe({**source_metadata, "constituent_count": len(constituents)}), indent=2),
        encoding="utf-8",
    )


def discover_historical_membership_sources(
    *,
    raw_history_dir: Path,
    target_start_date: date,
    target_end_date: date,
    max_sources: int | None = None,
    download_documents: bool = True,
    refresh_index: bool = False,
    request_delay_seconds: float = 0.05,
    timeout_seconds: int = 30,
) -> list[OfficialMembershipSource]:
    raw_history_dir.mkdir(parents=True, exist_ok=True)
    index_path = raw_history_dir / "press_release_index.html"
    if index_path.exists() and not refresh_index:
        index_html = index_path.read_text(encoding="utf-8", errors="replace")
    else:
        index_html = download_text(PRESS_RELEASE_INDEX_URL, timeout_seconds=timeout_seconds)
        index_path.write_text(index_html, encoding="utf-8")

    discovery_start = target_start_date - timedelta(days=120)
    discovery_end = target_end_date + timedelta(days=120)
    sources = [
        source
        for source in parse_press_release_links(index_html)
        if source.announced_date is not None
        and discovery_start <= source.announced_date <= discovery_end
        and is_membership_relevant_title(source.title)
    ]
    sources.sort(key=lambda source: (source.announced_date or date.min, source.url))
    if max_sources is not None and max_sources > 0:
        sources = sources[:max_sources]

    if not download_documents:
        return sources

    downloaded: list[OfficialMembershipSource] = []
    for source in sources:
        document_path = raw_history_dir / safe_filename(source.filename or Path(source.url).name)
        if document_path.exists() and is_pdf_file(document_path):
            downloaded.append(replace(source, source_document=str(document_path), parse_status="DOWNLOADED"))
            continue

        try:
            document_path.write_bytes(download_bytes(source.url, timeout_seconds=timeout_seconds))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            downloaded.append(
                replace(
                    source,
                    source_document=str(document_path) if document_path.exists() else "",
                    parse_status="DOWNLOAD_FAILED",
                    notes=exc.__class__.__name__,
                )
            )
            continue

        if request_delay_seconds > 0:
            time.sleep(request_delay_seconds)

        if is_pdf_file(document_path):
            downloaded.append(replace(source, source_document=str(document_path), parse_status="DOWNLOADED"))
        else:
            downloaded.append(
                replace(
                    source,
                    source_document=str(document_path),
                    parse_status="INVALID_PDF",
                    notes="Official URL did not return a PDF payload.",
                )
            )
    return downloaded


def parse_press_release_links(index_html: str) -> list[OfficialMembershipSource]:
    pattern = re.compile(
        r"<a\s+href=['\"](?P<href>/Press_Release/[^'\"]+)['\"][^>]*>(?P<title>.*?)</a>",
        re.IGNORECASE | re.DOTALL,
    )
    sources: list[OfficialMembershipSource] = []
    seen: set[str] = set()
    for match in pattern.finditer(index_html):
        href = html.unescape(match.group("href")).strip()
        title = re.sub(r"\s+", " ", html.unescape(match.group("title"))).strip()
        if not href.lower().endswith(".pdf") or href in seen:
            continue
        seen.add(href)
        url = f"{PRESS_RELEASE_BASE_URL}{href}"
        filename = safe_filename(Path(href).name)
        sources.append(
            OfficialMembershipSource(
                title=title,
                url=url,
                source_document="",
                announced_date=announcement_date_from_path(href),
                filename=filename,
                parse_status="DISCOVERED",
            )
        )
    return sources


def is_membership_relevant_title(title: str) -> bool:
    lowered = title.lower()
    excluded_phrases = (
        "fixed income",
        "sme emerge",
        "nifty ipo",
        "ipo index",
        "nifty waves",
        "nifty aif",
        "launches",
        "higher frequency",
        "methodology",
        "tracking error",
        "nifty smallcap 500",
        "nifty fpi",
        "nifty reits",
        "nifty bharat bond",
        "government bond",
        "corporate bond",
        "banking and psu bond",
    )
    if any(phrase in lowered for phrase in excluded_phrases):
        return False
    if "nifty 500" in lowered:
        return True
    keywords = (
        "replacement in indices",
        "replacements in indices",
        "replacements in nifty indices",
        "index maintenance sub-committee",
        "maintenance sub-committee",
        "exclusion of",
        "corporate adjustment",
        "corporate action adjustment",
        "revision in criteria",
    )
    return any(keyword in lowered for keyword in keywords)


def parse_membership_source(
    source: OfficialMembershipSource,
    *,
    constituents: Sequence[Nifty500Constituent],
) -> ParsedDocumentResult:
    source_name = source.filename or Path(source.source_document).name
    if source_name in SUPERSEDED_SOURCE_NOTES:
        return ParsedDocumentResult(
            source=replace(
                source,
                parse_status="SUPERSEDED_BY_LATER_OFFICIAL_RELEASE",
                contains_nifty500_changes=True,
                can_parse_automatically=False,
                parsed_event_count=0,
                notes=SUPERSEDED_SOURCE_NOTES[source_name],
            ),
            events=(),
            manual_review_items=(),
        )

    if not source.source_document:
        return ParsedDocumentResult(
            source=replace(source, parse_status="DOWNLOAD_FAILED"),
            events=(),
            manual_review_items=(
                ManualReviewItem(
                    source_document=source.url,
                    page_section="document",
                    issue="source_document_missing",
                    suspected_event_company="",
                    required_action="Download official PDF and rerun parser.",
                    confidence="HIGH",
                ),
            ),
        )

    document_path = Path(source.source_document)
    if not is_pdf_file(document_path):
        return ParsedDocumentResult(
            source=replace(source, parse_status="INVALID_PDF"),
            events=(),
            manual_review_items=(
                ManualReviewItem(
                    source_document=str(document_path),
                    page_section="document",
                    issue="invalid_pdf_payload",
                    suspected_event_company="",
                    required_action="Verify official source URL and replace non-PDF payload.",
                    confidence="HIGH",
                ),
            ),
        )

    text = extract_pdf_text_if_available(document_path)
    if not text.strip():
        return ParsedDocumentResult(
            source=replace(source, parse_status="MANUAL_REVIEW_REQUIRED", notes="PDF text extraction returned no text."),
            events=(),
            manual_review_items=(
                ManualReviewItem(
                    source_document=str(document_path),
                    page_section="document",
                    issue="pdf_text_extraction_empty",
                    suspected_event_company="",
                    required_action="Manually review or apply OCR only if direct text extraction is impossible.",
                    confidence="HIGH",
                ),
            ),
        )

    special_event = parse_special_corporate_action_event(source, text)
    if special_event is not None:
        return ParsedDocumentResult(
            source=replace(
                source,
                parse_status="PARSED",
                contains_nifty500_changes=True,
                can_parse_automatically=True,
                parsed_event_count=1,
                notes=special_event.notes,
            ),
            events=(special_event,),
            manual_review_items=(),
        )

    sections = extract_nifty500_sections(text)
    if not sections:
        parse_status = "NO_NIFTY500_CHANGES"
        return ParsedDocumentResult(
            source=replace(
                source,
                parse_status=parse_status,
                contains_nifty500_changes=False,
                can_parse_automatically=True,
                parsed_event_count=0,
                notes="No exact Nifty 500 membership-change section found.",
            ),
            events=(),
            manual_review_items=(),
        )

    effective_date = parse_effective_date(text) or parse_effective_date(source.title)
    if effective_date is None:
        return ParsedDocumentResult(
            source=replace(source, parse_status="MANUAL_REVIEW_REQUIRED", contains_nifty500_changes=True),
            events=(),
            manual_review_items=(
                ManualReviewItem(
                    source_document=str(document_path),
                    page_section="Nifty 500",
                    issue="effective_date_missing",
                    suspected_event_company="",
                    required_action="Read official PDF and record explicit effective date.",
                    confidence="HIGH",
                ),
            ),
        )

    current_lookup = {
        constituent.trading_symbol: constituent
        for constituent in constituents
    }
    events: list[IndexMembershipEvent] = []
    review_items: list[ManualReviewItem] = []
    for section_index, section in enumerate(sections, start=1):
        parsed_rows, unresolved = parse_nifty500_section_rows(section)
        for row in parsed_rows:
            constituent = current_lookup.get(row["symbol"])
            events.append(
                IndexMembershipEvent(
                    index_name=NIFTY500_INDEX_NAME,
                    company_name_original=row["company_name_original"],
                    company_name_normalized=normalize_company_name(row["company_name_original"]),
                    symbol=row["symbol"],
                    isin=constituent.isin if constituent else "",
                    event_type=row["event_type"],
                    announced_date=source.announced_date,
                    effective_date=effective_date,
                    source_document=str(document_path),
                    source_reference=source.url,
                    mapping_method="EXPLICIT_SYMBOL",
                    mapping_confidence="HIGH",
                    extraction_confidence="HIGH",
                    review_status="PARSED",
                    notes=source.title,
                )
            )
        for raw in unresolved:
            review_items.append(
                ManualReviewItem(
                    source_document=str(document_path),
                    page_section=f"Nifty 500 section {section_index}",
                    issue="unparsed_table_row",
                    suspected_event_company=raw,
                    required_action="Verify company row and symbol from official PDF.",
                    confidence="MEDIUM",
                )
            )

    parse_status = "PARSED" if events and not review_items else "PARSED_WITH_REVIEW"
    return ParsedDocumentResult(
        source=replace(
            source,
            parse_status=parse_status,
            contains_nifty500_changes=bool(events or review_items),
            can_parse_automatically=bool(events),
            parsed_event_count=len(events),
            notes=f"Parsed {len(events)} Nifty 500 event rows.",
        ),
        events=tuple(events),
        manual_review_items=tuple(review_items),
    )


def parse_special_corporate_action_event(
    source: OfficialMembershipSource,
    text: str,
) -> IndexMembershipEvent | None:
    source_name = source.filename or Path(source.source_document).name
    special = SPECIAL_CORPORATE_ACTION_SOURCES.get(source_name)
    if special is None:
        return None

    if special["symbol"] not in text or not re.search(r"\bNifty\s+500\b", text, flags=re.IGNORECASE):
        return None

    effective_date = parse_effective_date(text) or special["effective_date"]
    return IndexMembershipEvent(
        index_name=NIFTY500_INDEX_NAME,
        company_name_original=special["company_name_original"],
        company_name_normalized=special["company_name_normalized"],
        symbol=special["symbol"],
        isin=special["isin"],
        event_type="ADDED",
        announced_date=source.announced_date,
        effective_date=effective_date,
        source_document=source.source_document,
        source_reference=source.url,
        mapping_method="SPECIAL_CORPORATE_ACTION_SYMBOL",
        mapping_confidence="HIGH",
        extraction_confidence="HIGH",
        review_status="PARSED",
        notes=special["notes"],
    )


def extract_pdf_text_if_available(path: Path) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return ""

    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def extract_nifty500_sections(text: str) -> list[list[str]]:
    lines = normalized_lines(text)
    sections: list[list[str]] = []
    start_indexes = [
        index for index, line in enumerate(lines) if is_exact_nifty500_heading(line)
    ]
    for start_index in start_indexes:
        section: list[str] = []
        for line in lines[start_index + 1 :]:
            if is_next_index_heading(line):
                break
            section.append(line)
        if any("excluded" in line.lower() or "included" in line.lower() for line in section):
            sections.append(section)
    return sections


def parse_membership_events_from_text(
    text: str,
    *,
    source: OfficialMembershipSource,
) -> list[IndexMembershipEvent]:
    effective_date = parse_effective_date(text) or parse_effective_date(source.title)
    if effective_date is None:
        return []

    events: list[IndexMembershipEvent] = []
    for section in extract_nifty500_sections(text):
        parsed_rows, _ = parse_nifty500_section_rows(section)
        for row in parsed_rows:
            events.append(
                IndexMembershipEvent(
                    index_name=NIFTY500_INDEX_NAME,
                    company_name_original=row["company_name_original"],
                    company_name_normalized=normalize_company_name(row["company_name_original"]),
                    symbol=row["symbol"],
                    isin="",
                    event_type=row["event_type"],
                    announced_date=source.announced_date,
                    effective_date=effective_date,
                    source_document=source.source_document,
                    source_reference=source.url,
                    mapping_method="EXPLICIT_SYMBOL",
                    mapping_confidence="HIGH",
                    extraction_confidence="HIGH",
                    review_status="PARSED",
                    notes=source.title,
                )
            )
    return events


def parse_nifty500_section_rows(section_lines: Sequence[str]) -> tuple[list[dict[str, str]], list[str]]:
    parsed: list[dict[str, str]] = []
    unresolved: list[str] = []
    event_type = ""
    current_buffer = ""

    def flush() -> None:
        nonlocal current_buffer
        if not current_buffer.strip():
            return
        row = parse_company_symbol_row(current_buffer, event_type=event_type)
        if row is None:
            unresolved.append(current_buffer.strip())
        else:
            parsed.append(row)
        current_buffer = ""

    for raw_line in section_lines:
        line = clean_line(raw_line)
        if not line:
            continue
        lowered = line.lower()
        if "being excluded" in lowered or "being removed" in lowered:
            flush()
            event_type = "REMOVED"
            continue
        if "being included" in lowered or "being added" in lowered:
            flush()
            event_type = "ADDED"
            continue
        if should_skip_table_line(line):
            continue
        row_start = re.match(r"^(?P<number>\d{1,3})\s+(?P<body>.+)$", line)
        if row_start:
            flush()
            current_buffer = row_start.group("body")
            if row_has_symbol(current_buffer):
                flush()
            continue
        if current_buffer:
            current_buffer = f"{current_buffer} {line}"
            if row_has_symbol(current_buffer):
                flush()
    flush()
    return parsed, unresolved


def parse_company_symbol_row(row_text: str, *, event_type: str) -> dict[str, str] | None:
    if event_type not in {"ADDED", "REMOVED"}:
        return None
    row_text = clean_line(row_text).replace("\u2013", "-")
    match = re.match(r"^(?P<company>.+?)\s+(?P<symbol>[A-Z0-9][A-Z0-9&.-]{1,24})\*?$", row_text)
    if not match:
        return None
    symbol = match.group("symbol").strip().strip("*").upper()
    company = match.group("company").strip().strip("*")
    if not re.search(r"[A-Z]", symbol) or symbol in {"LTD", "LIMITED", "INDIA", "FUND", "REIT"}:
        return None
    return {
        "company_name_original": company,
        "symbol": symbol,
        "event_type": event_type,
    }


def row_has_symbol(row_text: str) -> bool:
    return parse_company_symbol_row(row_text, event_type="ADDED") is not None


def should_skip_table_line(line: str) -> bool:
    lowered = line.lower()
    skip_prefixes = (
        "sr. no.",
        "sr no",
        "company name symbol",
        "note:",
        "notes:",
        "the above replacement",
        "the above replacements",
        "for more information",
        "about nse indices",
        "press release",
        "mumbai,",
    )
    return (
        any(lowered.startswith(prefix) for prefix in skip_prefixes)
        or lowered.startswith("*")
        or "shall become effective" in lowered
    )


def current_snapshot_events(
    constituents: Sequence[Nifty500Constituent],
    *,
    source_metadata: dict[str, Any],
) -> list[IndexMembershipEvent]:
    source_date = date.fromisoformat(source_metadata["source_date"])
    source_url = str(source_metadata.get("source_url") or NIFTY500_SOURCE_URL)
    return [
        IndexMembershipEvent(
            index_name=NIFTY500_INDEX_NAME,
            company_name_original=constituent.company_name,
            company_name_normalized=normalize_company_name(constituent.company_name),
            symbol=constituent.trading_symbol,
            isin=constituent.isin,
            event_type="CURRENT_SNAPSHOT",
            announced_date=None,
            effective_date=source_date,
            source_document="data/reference/nifty500/current/nifty500_constituents_raw.csv",
            source_reference=source_url,
            mapping_method="OFFICIAL_CURRENT_SNAPSHOT",
            mapping_confidence="HIGH",
            extraction_confidence="HIGH",
            review_status="PARSED",
            notes="Current snapshot only; does not prove historical start date.",
        )
        for constituent in constituents
    ]


def identity_alias_rows() -> list[dict[str, str]]:
    return [dict(row) for row in CONTROLLED_IDENTITY_ALIASES]


def identity_alias_map(identity_aliases: Sequence[dict[str, str]] | None = None) -> dict[str, str]:
    return {
        row["original_symbol"].upper(): row["canonical_symbol"].upper()
        for row in (identity_aliases or CONTROLLED_IDENTITY_ALIASES)
    }


def canonical_symbol(
    symbol: str,
    identity_aliases: Sequence[dict[str, str]] | None = None,
) -> str:
    normalized = symbol.strip().upper()
    return identity_alias_map(identity_aliases).get(normalized, normalized)


def reconstruct_membership_periods(
    *,
    current_constituents: Sequence[Nifty500Constituent],
    events: Sequence[IndexMembershipEvent],
    snapshot_date: date,
    target_start_date: date,
    target_end_date: date,
    identity_aliases: Sequence[dict[str, str]] | None = None,
) -> tuple[list[IndexMembershipPeriod], dict[str, Any]]:
    active: dict[str, tuple[str, str]] = {
        canonical_symbol(constituent.trading_symbol, identity_aliases): (constituent.isin, "current_snapshot")
        for constituent in current_constituents
    }
    event_groups: dict[date, list[IndexMembershipEvent]] = defaultdict(list)
    for event in events:
        if event.event_type in {"ADDED", "REMOVED"} and target_start_date <= event.effective_date <= min(snapshot_date, target_end_date):
            event_groups[event.effective_date].append(event)

    effective_dates = sorted(event_groups, reverse=True)
    application_anomalies: list[dict[str, Any]] = []
    if not effective_dates:
        periods = [
            IndexMembershipPeriod(
                index_name=NIFTY500_INDEX_NAME,
                symbol=canonical_symbol(constituent.trading_symbol, identity_aliases),
                isin=constituent.isin,
                valid_from=snapshot_date,
                valid_to=None,
                reconstruction_method="CURRENT_SNAPSHOT_ONLY",
                source_confidence="CURRENT_ONLY",
                provenance=NIFTY500_SOURCE_URL,
            )
            for constituent in current_constituents
        ]
        return periods, {
            "method": "CURRENT_SNAPSHOT_ONLY",
            "earliest_reconstructable_date": snapshot_date.isoformat(),
            "latest_reconstructable_date": snapshot_date.isoformat(),
            "events_used": 0,
            "interval_count": 1,
            "event_application_anomalies": [],
        }

    period_rows: list[IndexMembershipPeriod] = []
    interval_end = min(snapshot_date, target_end_date)
    for effective_date in effective_dates:
        interval_start = effective_date
        if interval_start <= interval_end:
            period_rows.extend(
                period_rows_for_active_set(
                    active,
                    valid_from=interval_start,
                    valid_to=interval_end,
                    method="BACKWARD_RECONSTRUCTED_FROM_CURRENT_SNAPSHOT",
                    source_confidence="OFFICIAL_EVENTS_PARTIAL",
                )
            )

        for event in event_groups[effective_date]:
            resolved_symbol = canonical_symbol(event.symbol, identity_aliases)
            if event.event_type == "ADDED":
                if resolved_symbol not in active:
                    application_anomalies.append(
                        event_application_anomaly(
                            event,
                            canonical=resolved_symbol,
                            issue="add_not_active_after_effective_date",
                            notes="Backward reconstruction could not remove this ADD because the canonical identity was not active in the later interval. This usually indicates a duplicate ADD, missing later REMOVE, or unresolved symbol identity change.",
                        )
                    )
                active.pop(resolved_symbol, None)
            elif event.event_type == "REMOVED":
                if resolved_symbol in active:
                    application_anomalies.append(
                        event_application_anomaly(
                            event,
                            canonical=resolved_symbol,
                            issue="remove_already_active_after_effective_date",
                            notes="Backward reconstruction found this REMOVED identity already active in the later interval. This usually indicates a missing later ADD, repeated REMOVE, or current snapshot conflict.",
                        )
                    )
                active[resolved_symbol] = (event.isin, event.source_reference)

        interval_end = effective_date - timedelta(days=1)

    earliest = min(effective_dates)
    clipped_periods = [
        row for row in period_rows if row.valid_from is not None and row.valid_from <= target_end_date
    ]
    return merge_period_rows(clipped_periods), {
        "method": "BACKWARD_RECONSTRUCTED_FROM_CURRENT_SNAPSHOT",
        "earliest_reconstructable_date": earliest.isoformat(),
        "latest_reconstructable_date": min(snapshot_date, target_end_date).isoformat(),
        "events_used": sum(len(rows) for rows in event_groups.values()),
        "interval_count": len(effective_dates),
        "event_application_anomalies": application_anomalies,
    }


def event_application_anomaly(
    event: IndexMembershipEvent,
    *,
    canonical: str,
    issue: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "symbol": event.symbol,
        "canonical_symbol": canonical,
        "event_type": event.event_type,
        "effective_date": event.effective_date.isoformat(),
        "source_document": Path(event.source_document).name,
        "issue": issue,
        "notes": notes,
    }


def period_rows_for_active_set(
    active: dict[str, tuple[str, str]],
    *,
    valid_from: date,
    valid_to: date,
    method: str,
    source_confidence: str,
) -> list[IndexMembershipPeriod]:
    return [
        IndexMembershipPeriod(
            index_name=NIFTY500_INDEX_NAME,
            symbol=symbol,
            isin=isin,
            valid_from=valid_from,
            valid_to=valid_to,
            reconstruction_method=method,
            source_confidence=source_confidence,
            provenance=provenance,
        )
        for symbol, (isin, provenance) in sorted(active.items())
    ]


def merge_period_rows(periods: Sequence[IndexMembershipPeriod]) -> list[IndexMembershipPeriod]:
    grouped: dict[tuple[str, str, str, str], list[IndexMembershipPeriod]] = defaultdict(list)
    for period in periods:
        grouped[
            (
                period.symbol,
                period.isin,
                period.reconstruction_method,
                period.source_confidence,
            )
        ].append(period)

    merged: list[IndexMembershipPeriod] = []
    for (symbol, isin, method, confidence), rows in grouped.items():
        rows = sorted(rows, key=lambda row: row.valid_from or date.min)
        current = rows[0]
        for row in rows[1:]:
            if (
                current.valid_to is not None
                and row.valid_from is not None
                and current.valid_to + timedelta(days=1) == row.valid_from
                and current.provenance == row.provenance
            ):
                current = replace(current, valid_to=row.valid_to)
                continue
            merged.append(current)
            current = row
        merged.append(current)
    return sorted(merged, key=lambda row: (row.symbol, row.valid_from or date.min, row.valid_to or date.max))


def query_nifty500_members(
    *,
    as_of_date: date,
    history_dir: Path | None = None,
    verbose: bool = False,
) -> MembershipQueryResult:
    history_dir = history_dir or DEFAULT_HISTORY_DIR
    coverage_path = history_dir / "membership_coverage.json"
    periods_path = history_dir / "membership_periods.csv"
    coverage = json.loads(coverage_path.read_text(encoding="utf-8")) if coverage_path.exists() else {}
    reconstruction = coverage.get("reconstruction", {})
    earliest = parse_optional_date(reconstruction.get("earliest_reconstructable_date"))
    latest = parse_optional_date(reconstruction.get("latest_reconstructable_date"))

    if earliest and as_of_date < earliest:
        return MembershipQueryResult(
            as_of_date=as_of_date,
            membership_status="OUTSIDE_VERIFIED_RANGE",
            source_confidence="NONE",
            member_count=0,
            symbols=(),
            provenance_summary="Date predates the earliest reconstructed official membership event; current snapshot was not substituted.",
            earliest_reconstructable_date=earliest,
            latest_reconstructable_date=latest,
            reconstructed_from_official_events=False,
        )

    if latest and as_of_date > latest:
        return MembershipQueryResult(
            as_of_date=as_of_date,
            membership_status="OUTSIDE_VERIFIED_RANGE",
            source_confidence="NONE",
            member_count=0,
            symbols=(),
            provenance_summary="Date is after the latest verified snapshot/reconstruction range.",
            earliest_reconstructable_date=earliest,
            latest_reconstructable_date=latest,
            reconstructed_from_official_events=False,
        )

    periods = read_membership_periods(periods_path)
    active_periods = [
        period
        for period in periods
        if (period.valid_from is None or period.valid_from <= as_of_date)
        and (period.valid_to is None or as_of_date <= period.valid_to)
    ]
    status = coverage.get("survivorship_bias_status") or "INCONCLUSIVE"
    reconstructed = any(
        period.reconstruction_method.startswith("BACKWARD_RECONSTRUCTED")
        for period in active_periods
    )

    if not active_periods:
        source_confidence = "NONE"
        provenance = "No membership evidence available for this date; current snapshot was not substituted."
    else:
        confidence_counts = Counter(period.source_confidence for period in active_periods)
        source_confidence = ",".join(sorted(confidence_counts))
        provenance = "; ".join(f"{key}: {value}" for key, value in sorted(confidence_counts.items()))

    symbols = tuple(sorted(period.symbol for period in active_periods))
    visible_symbols = symbols if verbose else symbols[:25]
    return MembershipQueryResult(
        as_of_date=as_of_date,
        membership_status=status,
        source_confidence=source_confidence,
        member_count=len(symbols),
        symbols=visible_symbols,
        provenance_summary=provenance,
        earliest_reconstructable_date=earliest,
        latest_reconstructable_date=latest,
        reconstructed_from_official_events=reconstructed,
    )


def get_nifty500_members(
    *,
    as_of_date: date,
    history_dir: Path | None = None,
    verbose: bool = False,
) -> MembershipQueryResult:
    return query_nifty500_members(
        as_of_date=as_of_date,
        history_dir=history_dir,
        verbose=verbose,
    )


def build_membership_reconciliation_rows(
    *,
    events: Sequence[IndexMembershipEvent],
    periods: Sequence[IndexMembershipPeriod],
    reconstruction: dict[str, Any],
    target_start_date: date,
    target_end_date: date,
) -> list[dict[str, Any]]:
    effective_dates = sorted(
        {
            event.effective_date
            for event in events
            if event.event_type in {"ADDED", "REMOVED"} and target_start_date <= event.effective_date <= target_end_date
        }
    )
    rows: list[dict[str, Any]] = []
    for effective_date in effective_dates:
        additions = sum(
            1
            for event in events
            if event.event_type == "ADDED" and event.effective_date == effective_date
        )
        removals = sum(
            1
            for event in events
            if event.event_type == "REMOVED" and event.effective_date == effective_date
        )
        count_before = count_members_on(periods, effective_date - timedelta(days=1))
        actual_after = count_members_on(periods, effective_date)
        expected_after: int | None = None
        difference: int | None = None
        if count_before is not None:
            expected_after = count_before + additions - removals
        if expected_after is not None and actual_after is not None:
            difference = actual_after - expected_after

        rows.append(
            {
                "effective_date": effective_date.isoformat(),
                "count_before": count_before if count_before is not None else "",
                "additions": additions,
                "removals": removals,
                "expected_after": expected_after if expected_after is not None else "",
                "actual_after": actual_after if actual_after is not None else "",
                "difference": difference if difference is not None else "",
                "applied_to_reconstruction": effective_date <= parse_optional_date(reconstruction.get("latest_reconstructable_date")),
                "notes": reconciliation_note(effective_date, reconstruction, difference),
            }
        )
    return rows


def standard_query_counts(
    *,
    periods: Sequence[IndexMembershipPeriod],
    status: str,
    reconstruction: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    query_dates = (
        date(2026, 9, 7),
        date(2025, 6, 15),
        date(2024, 6, 15),
        date(2023, 6, 15),
        date(2022, 6, 15),
    )
    earliest = parse_optional_date(reconstruction.get("earliest_reconstructable_date"))
    latest = parse_optional_date(reconstruction.get("latest_reconstructable_date"))
    rows: dict[str, dict[str, Any]] = {}
    for query_date in query_dates:
        if earliest and query_date < earliest:
            rows[query_date.isoformat()] = {
                "member_count": 0,
                "membership_status": "OUTSIDE_VERIFIED_RANGE",
                "source_confidence": "NONE",
            }
            continue
        if latest and query_date > latest:
            rows[query_date.isoformat()] = {
                "member_count": 0,
                "membership_status": "OUTSIDE_VERIFIED_RANGE",
                "source_confidence": "NONE",
            }
            continue

        active_periods = [
            period
            for period in periods
            if (period.valid_from is None or period.valid_from <= query_date)
            and (period.valid_to is None or query_date <= period.valid_to)
        ]
        confidence_counts = Counter(period.source_confidence for period in active_periods)
        rows[query_date.isoformat()] = {
            "member_count": len(active_periods),
            "membership_status": status,
            "source_confidence": ",".join(sorted(confidence_counts)) if confidence_counts else "NONE",
        }
    return rows


def count_members_on(periods: Sequence[IndexMembershipPeriod], as_of_date: date) -> int | None:
    if not periods:
        return None
    earliest = min((period.valid_from for period in periods if period.valid_from), default=None)
    latest_candidates = [period.valid_to for period in periods if period.valid_to]
    latest = max(latest_candidates) if latest_candidates else None
    if earliest and as_of_date < earliest:
        return None
    if latest and as_of_date > latest:
        return None
    return sum(
        1
        for period in periods
        if (period.valid_from is None or period.valid_from <= as_of_date)
        and (period.valid_to is None or as_of_date <= period.valid_to)
    )


def reconciliation_note(
    effective_date: date,
    reconstruction: dict[str, Any],
    difference: int | None,
) -> str:
    latest = parse_optional_date(reconstruction.get("latest_reconstructable_date"))
    if latest and effective_date > latest:
        return "Future official event discovered but not applied to the current as-of reconstruction."
    if difference is None:
        return "Count before this date is outside the reconstructed coverage range."
    if difference:
        return "Count difference remains; see lifecycle anomalies and identity alias notes."
    return "Count reconciles against applied event totals for this effective date."


def build_review_cycle_coverage(
    *,
    target_start_date: date,
    target_end_date: date,
    sources: Sequence[OfficialMembershipSource],
    events: Sequence[IndexMembershipEvent],
    manual_review_items: Sequence[ManualReviewItem],
) -> list[dict[str, Any]]:
    event_groups: dict[tuple[int, int], list[IndexMembershipEvent]] = defaultdict(list)
    for event in events:
        if event.event_type in {"ADDED", "REMOVED"}:
            event_groups[(event.effective_date.year, event.effective_date.month)].append(event)

    source_groups: dict[tuple[int, int], list[OfficialMembershipSource]] = defaultdict(list)
    for source in sources:
        effective = source_effective_date(source)
        if effective is not None:
            source_groups[(effective.year, effective.month)].append(source)

    sources_by_document = {
        Path(source.source_document).name: source
        for source in sources
        if source.source_document
    }
    manual_groups: dict[tuple[int, int], int] = defaultdict(int)
    for item in manual_review_items:
        source = sources_by_document.get(Path(item.source_document).name)
        effective = source_effective_date(source) if source else None
        if effective is None:
            effective = announcement_date_from_path(item.source_document)
        if effective is not None:
            manual_groups[(effective.year, effective.month)] += 1

    cycles: list[dict[str, Any]] = []
    for year in range(target_start_date.year, target_end_date.year + 1):
        for month in TARGET_REVIEW_MONTHS:
            cycle_date = date(year, month, 1)
            if cycle_date < date(target_start_date.year, target_start_date.month, 1):
                continue
            if cycle_date > date(target_end_date.year, target_end_date.month, 1):
                continue
            key = (year, month)
            cycle_events = event_groups.get(key, [])
            cycle_sources = source_groups.get(key, [])
            source_documents = {
                Path(source.source_document).name
                for source in cycle_sources
                if source.source_document
            }
            source_documents.update(
                Path(event.source_document).name
                for event in cycle_events
                if event.source_document
            )
            cycles.append(
                {
                    "cycle": f"{year}-{month:02d}",
                    "source_found": bool(cycle_sources or cycle_events),
                    "parsed": bool(cycle_events),
                    "effective_dates": sorted({event.effective_date.isoformat() for event in cycle_events}),
                    "additions": sum(1 for event in cycle_events if event.event_type == "ADDED"),
                    "removals": sum(1 for event in cycle_events if event.event_type == "REMOVED"),
                    "unresolved_rows": manual_groups.get(key, 0),
                    "source_documents": sorted(source_documents),
                }
            )
    return cycles


def source_effective_date(source: OfficialMembershipSource) -> date | None:
    source_name = source.filename or Path(source.source_document).name
    if source_name == "ind_prs23082021.pdf":
        return date(2021, 9, 30)
    special = SPECIAL_CORPORATE_ACTION_SOURCES.get(source_name)
    if special:
        return special["effective_date"]
    return parse_effective_date(source.title)


def build_membership_coverage(
    *,
    events: Sequence[IndexMembershipEvent],
    periods: Sequence[IndexMembershipPeriod],
    sources: Sequence[OfficialMembershipSource],
    manual_review_items: Sequence[ManualReviewItem],
    constituents: Sequence[Nifty500Constituent],
    source_metadata: dict[str, Any],
    reconstruction: dict[str, Any],
    review_cycles: Sequence[dict[str, Any]],
    identity_aliases: Sequence[dict[str, str]],
    reconciliation_rows: Sequence[dict[str, Any]],
    target_start_date: date,
    target_end_date: date,
) -> dict[str, Any]:
    event_counts = Counter(event.event_type for event in events)
    source_counts = Counter(source.parse_status for source in sources)
    parsed_historical_events = event_counts["ADDED"] + event_counts["REMOVED"]
    cycles_expected = len(review_cycles)
    cycles_covered = sum(1 for cycle in review_cycles if cycle["parsed"])
    lifecycle_anomalies = reconstruction.get("event_application_anomalies", [])
    count_differences = [
        row for row in reconciliation_rows
        if row.get("difference") not in {"", 0, "0", None}
    ]
    unresolved_mappings = sum(
        1
        for event in events
        if event.event_type in {"ADDED", "REMOVED"} and event.mapping_confidence != "HIGH"
    )

    if parsed_historical_events == 0 and event_counts["CURRENT_SNAPSHOT"] > 0:
        status = "CURRENT_ONLY"
    elif (
        parsed_historical_events > 0
        and cycles_expected == cycles_covered
        and not manual_review_items
        and not lifecycle_anomalies
        and not count_differences
        and unresolved_mappings == 0
    ):
        status = "SURVIVORSHIP_SAFE"
    elif parsed_historical_events > 0:
        status = "PARTIAL_HISTORY"
    else:
        status = "INCONCLUSIVE"

    return {
        "phase": "Step 02.3D-Fix",
        "task": "Historical Nifty 500 membership reconstruction from official index review documents",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "official_sources": {
            "current_constituents": NIFTY500_SOURCE_URL,
            "press_release_index": PRESS_RELEASE_INDEX_URL,
            "index_rebalancing_schedule": REBALANCING_SCHEDULE_URL,
        },
        "target_date_range": {
            "start_date": target_start_date.isoformat(),
            "end_date": target_end_date.isoformat(),
        },
        "current_snapshot": {
            "source_date": source_metadata["source_date"],
            "constituent_count": len(constituents),
            "source": source_metadata,
        },
        "official_documents": {
            "inventoried": len(sources),
            "containing_nifty500_changes": sum(1 for source in sources if source.contains_nifty500_changes),
            "successfully_parsed": sum(1 for source in sources if source.parse_status == "PARSED"),
            "parsed_with_review": sum(1 for source in sources if source.parse_status == "PARSED_WITH_REVIEW"),
            "requiring_manual_review": len({item.source_document for item in manual_review_items}),
            "parse_status_counts": dict(source_counts),
        },
        "membership_events": {
            "total": len(events),
            "additions": event_counts["ADDED"],
            "removals": event_counts["REMOVED"],
            "current_snapshot": event_counts["CURRENT_SNAPSHOT"],
            "earliest_effective_event_date": earliest_event_date(events),
            "latest_effective_event_date": latest_event_date(events),
        },
        "membership_periods": {
            "total": len(periods),
            "coverage_start": reconstruction.get("earliest_reconstructable_date"),
            "coverage_end": reconstruction.get("latest_reconstructable_date"),
        },
        "review_cycle_coverage": {
            "expected_cycles": cycles_expected,
            "covered_cycles": cycles_covered,
            "timeline": list(review_cycles),
        },
        "symbol_resolution": {
            "mapping_method": "EXPLICIT_SYMBOL where official PDF provides symbol; current snapshot lookup used only for ISIN enrichment.",
            "unresolved_company_symbol_mappings": unresolved_mappings,
            "identity_alias_count": len(identity_aliases),
            "identity_aliases_path": "data/reference/nifty500/history/membership_identity_aliases.csv",
            "identity_aliases": list(identity_aliases),
        },
        "manual_review": {
            "items_remaining": len(manual_review_items),
            "path": "data/reports/nifty500_membership_manual_review.csv",
        },
        "reconstruction": reconstruction,
        "reconciliation": {
            "current_snapshot_explanation": "The official current constituent CSV dated 2026-09-07 contains 501 unique symbols and 501 unique ISINs. The extra constituent is DUMMYHEG, a dummy symbol for the HEG Ltd. demerger, supported by the official September 03, 2026 corporate-action press release effective September 07, 2026.",
            "unresolved_pdf_result": SUPERSEDED_SOURCE_NOTES["ind_prs23082021.pdf"],
            "rows": list(reconciliation_rows),
            "rows_with_count_differences": len(count_differences),
            "event_application_anomalies": lifecycle_anomalies,
            "previous_query_counts": {
                "2026-09-07": 501,
                "2025-06-15": 502,
                "2024-06-15": 502,
                "2023-06-15": 503,
                "2022-06-15": 505,
            },
            "updated_query_counts": standard_query_counts(
                periods=periods,
                status=status,
                reconstruction=reconstruction,
            ),
        },
        "survivorship_bias_status": status,
        "known_gaps": known_membership_gaps(
            status,
            cycles_expected,
            cycles_covered,
            manual_review_items,
            lifecycle_anomalies,
            count_differences,
        ),
        "storage": {
            "current_snapshot_path": "data/reference/nifty500/current/",
            "history_path": "data/reference/nifty500/history/",
            "source_manifest_csv": "data/reference/nifty500/history/membership_source_manifest.csv",
            "events_csv": "data/reference/nifty500/history/membership_events.csv",
            "periods_csv": "data/reference/nifty500/history/membership_periods.csv",
            "coverage_json": "data/reference/nifty500/history/membership_coverage.json",
            "report_json": "data/reports/nifty500_membership_coverage.json",
            "events_summary_csv": "data/reports/nifty500_membership_events_summary.csv",
            "manual_review_csv": "data/reports/nifty500_membership_manual_review.csv",
            "reconciliation_csv": "data/reports/nifty500_membership_reconciliation.csv",
            "reconciliation_json": "data/reports/nifty500_membership_reconciliation.json",
            "identity_aliases_csv": "data/reference/nifty500/history/membership_identity_aliases.csv",
        },
        "safety": {
            "orders_placed": 0,
            "remote_migrations_applied": 0,
            "supabase_bulk_records_persisted": 0,
            "strategy_calculations_executed": 0,
        },
    }


def known_membership_gaps(
    status: str,
    cycles_expected: int,
    cycles_covered: int,
    manual_review_items: Sequence[ManualReviewItem],
    lifecycle_anomalies: Sequence[dict[str, Any]],
    count_differences: Sequence[dict[str, Any]],
) -> list[str]:
    gaps: list[str] = []
    if status != "SURVIVORSHIP_SAFE":
        gaps.append("Historical membership is reconstructed from parsed official documents but has not been manually reconciled end to end.")
    if cycles_covered < cycles_expected:
        gaps.append(f"Expected semi-annual review cycles covered: {cycles_covered}/{cycles_expected}.")
    if manual_review_items:
        gaps.append("Some official PDFs/rows require manual review before survivorship-safe status can be claimed.")
    if lifecycle_anomalies:
        gaps.append(f"Lifecycle anomalies remain unresolved: {len(lifecycle_anomalies)} event applications need review.")
    if count_differences:
        gaps.append(f"Count reconciliation differences remain on {len(count_differences)} effective dates.")
    return gaps


def write_membership_markdown_report(*, coverage: dict[str, Any], path: Path) -> None:
    docs = coverage["official_documents"]
    events = coverage["membership_events"]
    periods = coverage["membership_periods"]
    cycles = coverage["review_cycle_coverage"]
    current = coverage["current_snapshot"]
    markdown = "\n".join(
        [
            "# Nifty 500 Point-in-Time Membership",
            "",
            "Current phase: Step 02.3D-Fix - historical membership reconstruction",
            "",
            "## Official Sources",
            "",
            f"- Current constituent CSV: {coverage['official_sources']['current_constituents']}",
            f"- Press-release index: {coverage['official_sources']['press_release_index']}",
            f"- Index rebalancing schedule reference: {coverage['official_sources']['index_rebalancing_schedule']}",
            f"- Official documents inventoried: {docs['inventoried']}",
            f"- Documents containing Nifty 500 changes: {docs['containing_nifty500_changes']}",
            f"- Documents successfully parsed: {docs['successfully_parsed']}",
            f"- Documents parsed with review items: {docs['parsed_with_review']}",
            f"- Documents requiring manual review: {docs['requiring_manual_review']}",
            "",
            "## Current Snapshot",
            "",
            f"- Source date: {current['source_date']}",
            f"- Current constituent snapshot count: {current['constituent_count']}",
            "",
            "## Extracted Events",
            "",
            f"- ADD events: {events['additions']}",
            f"- REMOVE events: {events['removals']}",
            f"- Earliest effective event date: {events['earliest_effective_event_date']}",
            f"- Latest effective event date: {events['latest_effective_event_date']}",
            "",
            "## Review Cycle Coverage",
            "",
            f"- Expected semi-annual cycles: {cycles['expected_cycles']}",
            f"- Covered cycles: {cycles['covered_cycles']}",
            *[
                f"- {cycle['cycle']}: source_found={cycle['source_found']}, parsed={cycle['parsed']}, effective_dates={','.join(cycle['effective_dates']) or 'none'}, additions={cycle['additions']}, removals={cycle['removals']}, unresolved_rows={cycle['unresolved_rows']}"
                for cycle in cycles["timeline"]
            ],
            "",
            "## Reconstruction",
            "",
            f"- Method: {coverage['reconstruction']['method']}",
            f"- Earliest reliable date: {periods['coverage_start']}",
            f"- Latest reliable date: {periods['coverage_end']}",
            f"- Membership periods available: {periods['total']}",
            f"- Unresolved company/symbol mappings: {coverage['symbol_resolution']['unresolved_company_symbol_mappings']}",
            f"- Controlled identity aliases: {coverage['symbol_resolution']['identity_alias_count']}",
            f"- Reconciliation differences: {coverage['reconciliation']['rows_with_count_differences']}",
            f"- Lifecycle anomalies: {len(coverage['reconciliation']['event_application_anomalies'])}",
            "",
            "## Point-In-Time Query Capability",
            "",
            "- `get_nifty500_members(as_of_date)` returns symbol set, count, coverage status, confidence, and reconstructable date bounds.",
            "- It does not silently substitute current constituents for dates outside verified range.",
            "- Use `python scripts/query_nifty500_membership.py --date YYYY-MM-DD` for diagnostics.",
            "",
            "## Survivorship Bias Status",
            "",
            f"- Status: {coverage['survivorship_bias_status']}",
            "",
            "## Limitations",
            "",
            *[f"- {gap}" for gap in coverage["known_gaps"]],
            "",
            "## Safety",
            "",
            "- ZERO order endpoints were called.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "- ZERO strategy calculations were executed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def write_membership_reconciliation_report(*, coverage: dict[str, Any], path: Path) -> None:
    docs = coverage["official_documents"]
    events = coverage["membership_events"]
    periods = coverage["membership_periods"]
    reconciliation = coverage["reconciliation"]
    anomalies = reconciliation["event_application_anomalies"]
    alias_rows = coverage["symbol_resolution"]["identity_aliases"]
    count_diffs = [
        row for row in reconciliation["rows"]
        if row.get("difference") not in {"", 0, "0", None}
    ]
    first_diff = count_diffs[0] if count_diffs else None
    markdown = "\n".join(
        [
            "# Nifty 500 Membership Reconciliation",
            "",
            "Current phase: Step 02.3D-Fix / Command 02 - count drift reconciliation",
            "",
            "## Unresolved PDF Review",
            "",
            f"- `ind_prs23082021.pdf`: {reconciliation['unresolved_pdf_result']}",
            "- OCR was not used; visual inspection of rendered pages was sufficient.",
            "",
            "## Official Current Count",
            "",
            f"- Current snapshot source date: {coverage['current_snapshot']['source_date']}",
            f"- Current snapshot row count: {coverage['current_snapshot']['constituent_count']}",
            f"- Explanation: {reconciliation['current_snapshot_explanation']}",
            "",
            "## Root Causes",
            "",
            "- Current 501 count is explained by the official DUMMYHEG demerger adjustment effective 2026-09-07.",
            "- Several historical rows use earlier symbols/names that map to current official constituent identities; these are captured in `membership_identity_aliases.csv`.",
            "- Remaining count drift is tied to official lifecycle inconsistencies that need manual source reconciliation, especially repeated or missing add/remove events.",
            "",
            "## Identity Aliases",
            "",
            *[
                f"- {row['original_symbol']} -> {row['canonical_symbol']}: {row['mapping_reason']}"
                for row in alias_rows
            ],
            "",
            "## Event Extraction",
            "",
            f"- Official documents inventoried: {docs['inventoried']}",
            f"- Documents containing Nifty 500 changes: {docs['containing_nifty500_changes']}",
            f"- Historical ADD events: {events['additions']}",
            f"- Historical REMOVE events: {events['removals']}",
            f"- Current snapshot events: {events['current_snapshot']}",
            f"- Effective event range: {events['earliest_effective_event_date']} to {events['latest_effective_event_date']}",
            "",
            "## Reconciliation Summary",
            "",
            f"- Reconstructed coverage: {periods['coverage_start']} to {periods['coverage_end']}",
            f"- Rows with count differences: {reconciliation['rows_with_count_differences']}",
            f"- First count difference: {first_diff['effective_date'] if first_diff else 'none'}",
            f"- Lifecycle anomalies remaining: {len(anomalies)}",
            "",
            "## Per-Effective-Date Reconciliation",
            "",
            "| effective_date | count_before | additions | removals | expected_after | actual_after | difference | notes |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            *[
                f"| {row['effective_date']} | {row['count_before']} | {row['additions']} | {row['removals']} | {row['expected_after']} | {row['actual_after']} | {row['difference']} | {row['notes']} |"
                for row in reconciliation["rows"]
            ],
            "",
            "## Lifecycle Anomalies",
            "",
            *(
                [
                    f"- {row['effective_date']} {row['event_type']} {row['symbol']} ({row['canonical_symbol']}): {row['issue']} from {row['source_document']}"
                    for row in anomalies
                ]
                or ["- None"]
            ),
            "",
            "## Query Counts",
            "",
            "| date | before_command_02 | after_command_02 | status |",
            "| --- | ---: | ---: | --- |",
            *query_count_markdown_rows(coverage),
            "",
            "## Final Status",
            "",
            f"- Survivorship-bias status: {coverage['survivorship_bias_status']}",
            "",
            "## Remaining Limitations",
            "",
            *[f"- {gap}" for gap in coverage["known_gaps"]],
            "",
            "## Safety",
            "",
            "- ZERO order endpoints were called.",
            "- ZERO remote migrations were applied.",
            "- ZERO bulk records were persisted to Supabase.",
            "- ZERO strategy, indicator, backtest, or signal calculations were executed.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")


def query_count_markdown_rows(coverage: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    for date_text, previous_count in coverage["reconciliation"]["previous_query_counts"].items():
        updated = coverage["reconciliation"]["updated_query_counts"].get(date_text, {})
        rows.append(
            f"| {date_text} | {previous_count} | {updated.get('member_count', '')} | {updated.get('membership_status', '')} |"
        )
    return rows


def read_membership_periods(path: Path) -> list[IndexMembershipPeriod]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        return [
            IndexMembershipPeriod(
                index_name=row["index_name"],
                symbol=row["symbol"],
                isin=row.get("isin") or "",
                valid_from=parse_optional_date(row.get("valid_from")),
                valid_to=parse_optional_date(row.get("valid_to")),
                reconstruction_method=row.get("reconstruction_method") or "",
                source_confidence=row.get("source_confidence") or "",
                provenance=row.get("provenance") or "",
            )
            for row in reader
        ]


def event_summary_rows(
    events: Sequence[IndexMembershipEvent],
    manual_review_items: Sequence[ManualReviewItem],
) -> list[dict[str, Any]]:
    grouped: dict[date, list[IndexMembershipEvent]] = defaultdict(list)
    for event in events:
        if event.event_type in {"ADDED", "REMOVED"}:
            grouped[event.effective_date].append(event)

    manual_by_document = Counter(Path(item.source_document).name for item in manual_review_items)
    rows: list[dict[str, Any]] = []
    for effective_date, event_rows_for_date in sorted(grouped.items()):
        source_documents = sorted({Path(event.source_document).name for event in event_rows_for_date})
        unresolved_rows = sum(manual_by_document.get(source_document, 0) for source_document in source_documents)
        rows.append(
            {
                "cycle": f"{effective_date.year}-{effective_date.month:02d}",
                "effective_date": effective_date.isoformat(),
                "source_documents": "; ".join(source_documents),
                "additions": sum(1 for event in event_rows_for_date if event.event_type == "ADDED"),
                "removals": sum(1 for event in event_rows_for_date if event.event_type == "REMOVED"),
                "unresolved_rows": unresolved_rows,
                "review_status": "PARSED_WITH_REVIEW" if unresolved_rows else "PARSED",
            }
        )
    return rows


def dedupe_events(events: Iterable[IndexMembershipEvent]) -> list[IndexMembershipEvent]:
    seen: dict[tuple[str, str, str, date], IndexMembershipEvent] = {}
    for event in events:
        key = (event.index_name, event.symbol, event.event_type, event.effective_date)
        existing = seen.get(key)
        if existing is None:
            seen[key] = event
            continue
        provenance = existing.source_reference
        if event.source_reference not in provenance:
            provenance = f"{provenance}; {event.source_reference}"
        notes = existing.notes
        if event.notes and event.notes not in notes:
            notes = f"{notes}; duplicate source: {event.notes}" if notes else event.notes
        seen[key] = replace(existing, source_reference=provenance, notes=notes)
    return sorted(seen.values(), key=lambda row: (row.effective_date, row.event_type, row.symbol))


def event_row(event: IndexMembershipEvent) -> dict[str, Any]:
    row = asdict(event)
    row["announced_date"] = event.announced_date.isoformat() if event.announced_date else ""
    row["effective_date"] = event.effective_date.isoformat()
    return row


def period_row(period: IndexMembershipPeriod) -> dict[str, Any]:
    row = asdict(period)
    row["valid_from"] = period.valid_from.isoformat() if period.valid_from else ""
    row["valid_to"] = period.valid_to.isoformat() if period.valid_to else ""
    return row


def source_manifest_row(source: OfficialMembershipSource) -> dict[str, Any]:
    return {
        "filename": source.filename or Path(source.source_document).name,
        "source_url": source.url,
        "published_date": source.announced_date.isoformat() if source.announced_date else "",
        "document_type": source.document_type,
        "title": source.title,
        "contains_nifty500_changes": source.contains_nifty500_changes,
        "can_parse_automatically": source.can_parse_automatically,
        "parse_status": source.parse_status,
        "parsed_event_count": source.parsed_event_count,
        "notes": source.notes,
    }


def parse_effective_date(text: str) -> date | None:
    patterns = (
        r"effective\s+from\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        r"w\.?\s*e\.?\s*f\.?\s*(?:from)?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4})",
        r"w\.?\s*e\.?\s*f\.?\s*(?:from)?\s*(\d{1,2}[-\s][A-Za-z]{3,9}[-\s]\d{4})",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        parsed = parse_date_text(match.group(1))
        if parsed is not None:
            return parsed
    return None


def parse_date_text(value: str) -> date | None:
    raw = value.strip().replace(",", "").replace("-", " ")
    for fmt in ("%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def announcement_date_from_path(path: str) -> date | None:
    match = re.search(r"ind_prs(?P<day>\d{2})(?P<month>\d{2})(?P<year>\d{4})", path)
    if not match:
        return None
    try:
        return date(
            int(match.group("year")),
            int(match.group("month")),
            int(match.group("day")),
        )
    except ValueError:
        return None


def earliest_event_date(events: Sequence[IndexMembershipEvent]) -> str:
    dates = [event.effective_date for event in events if event.event_type in {"ADDED", "REMOVED"}]
    return min(dates).isoformat() if dates else ""


def latest_event_date(events: Sequence[IndexMembershipEvent]) -> str:
    dates = [event.effective_date for event in events if event.event_type in {"ADDED", "REMOVED"}]
    return max(dates).isoformat() if dates else ""


def normalized_lines(text: str) -> list[str]:
    return [clean_line(line) for line in text.replace("\r", "\n").splitlines()]


def clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\ufeff", " ")).strip()


def is_exact_nifty500_heading(line: str) -> bool:
    stripped = re.sub(r"^[A-Za-z0-9]+[).]\s*", "", clean_line(line)).strip()
    return re.fullmatch(r"NIFTY\s*500", stripped, flags=re.IGNORECASE) is not None


def is_next_index_heading(line: str) -> bool:
    cleaned = clean_line(line)
    stripped = re.sub(r"^[A-Za-z0-9]+[).]\s*", "", cleaned).strip()
    if is_exact_nifty500_heading(cleaned):
        return False
    return re.match(r"^NIFTY\s+[A-Za-z0-9]", stripped, flags=re.IGNORECASE) is not None


def normalize_company_name(value: str) -> str:
    cleaned = clean_line(value).strip("*")
    replacements = {
        "&": "and",
        ".": "",
        "'": "",
        "\u2019": "",
        "-": " ",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    cleaned = re.sub(r"\b(limited|ltd)\b", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip().upper()


def parse_optional_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def is_pdf_file(path: Path) -> bool:
    try:
        return path.exists() and path.read_bytes()[:5] == b"%PDF-"
    except OSError:
        return False


def subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def download_text(url: str, *, timeout_seconds: int) -> str:
    return download_bytes(url, timeout_seconds=timeout_seconds).decode("utf-8", errors="replace")


def download_bytes(url: str, *, timeout_seconds: int) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/pdf,text/csv,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def write_csv(path: Path, rows: Sequence[dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(json_safe(row))


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "source.pdf"


def json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    return value
