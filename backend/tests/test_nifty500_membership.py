from __future__ import annotations

import json
from datetime import date

from app.services import nifty500_membership as service
from app.services.nifty500_acquisition import NIFTY500_INDEX_NAME, Nifty500Constituent
from app.services.nifty500_membership import (
    IndexMembershipEvent,
    ManualReviewItem,
    OfficialMembershipSource,
    build_membership_coverage,
    build_membership_reconciliation_rows,
    build_review_cycle_coverage,
    canonical_symbol,
    current_snapshot_events,
    dedupe_events,
    get_nifty500_members,
    identity_alias_rows,
    parse_company_symbol_row,
    parse_effective_date,
    parse_membership_events_from_text,
    parse_membership_source,
    parse_nifty500_section_rows,
    parse_special_corporate_action_event,
    parse_press_release_links,
    period_row,
    reconstruct_membership_periods,
)


PRESS_RELEASE_HTML = """
<a href='/Press_Release/ind_prs10082026.pdf' target='_blank'>Replacements in indices w.e.f. September 30, 2026</a>
<a href='/Press_Release/ind_prs07092026.pdf' target='_blank'>Changes in Nifty Fixed Income indices w.e.f. September 10 2026</a>
"""

NIFTY500_FIXTURE_TEXT = """
Replacements in indices w.e.f. September 30, 2026
NIFTY 500
Sr. No. Company Name Symbol
The following companies are being excluded:
1 Alpha Industries Ltd. ALPHA
2 3M India Ltd. 3MINDIA
The following companies are being included:
1 Beta Labs Ltd. BETA
NIFTY NEXT 50
The following companies are being excluded:
1 Other Ltd. OTHER
"""


def test_press_release_link_parser_discovers_official_pdf_sources():
    sources = parse_press_release_links(PRESS_RELEASE_HTML)

    assert len(sources) == 2
    assert sources[0].url == "https://www.niftyindices.com/Press_Release/ind_prs10082026.pdf"
    assert sources[0].announced_date == date(2026, 8, 10)


def test_title_filter_rejects_non_equity_index_documents():
    sources = [
        source for source in parse_press_release_links(PRESS_RELEASE_HTML)
        if service.is_membership_relevant_title(source.title)
    ]

    assert [source.filename for source in sources] == ["ind_prs10082026.pdf"]


def test_text_event_parser_collects_only_explicit_nifty500_events():
    source = membership_source()

    events = parse_membership_events_from_text(NIFTY500_FIXTURE_TEXT, source=source)

    assert [(event.event_type, event.symbol) for event in events] == [
        ("REMOVED", "ALPHA"),
        ("REMOVED", "3MINDIA"),
        ("ADDED", "BETA"),
    ]
    assert {event.effective_date for event in events} == {date(2026, 9, 30)}
    assert all(event.mapping_method == "EXPLICIT_SYMBOL" for event in events)


def test_effective_date_must_be_explicit_not_announced_date():
    source = membership_source(title="Index review announcement", announced=date(2026, 8, 10))
    text = """
    NIFTY 500
    The following companies are being included:
    1 Beta Labs Ltd. BETA
    """

    assert parse_membership_events_from_text(text, source=source) == []
    assert parse_effective_date("Replacements in indices w.e.f. September 30, 2026") == date(2026, 9, 30)


def test_symbol_resolution_allows_digit_prefixed_nse_symbols():
    row = parse_company_symbol_row("3M India Ltd. 3MINDIA", event_type="REMOVED")

    assert row == {
        "company_name_original": "3M India Ltd.",
        "symbol": "3MINDIA",
        "event_type": "REMOVED",
    }


def test_unresolved_rows_enter_manual_review_queue():
    parsed, unresolved = parse_nifty500_section_rows(
        [
            "The following companies are being included:",
            "1 incomplete company without official symbol",
        ]
    )
    item = ManualReviewItem(
        source_document="fixture.pdf",
        page_section="Nifty 500 section 1",
        issue="unparsed_table_row",
        suspected_event_company=unresolved[0],
        required_action="Verify company row and symbol from official PDF.",
        confidence="MEDIUM",
    )

    assert parsed == []
    assert item.issue == "unparsed_table_row"
    assert item.suspected_event_company == "incomplete company without official symbol"


def test_duplicate_events_preserve_provenance():
    first = membership_event("BETA", "ADDED", date(2024, 9, 30), source_reference="https://official/source-a.pdf")
    duplicate = membership_event("BETA", "ADDED", date(2024, 9, 30), source_reference="https://official/source-b.pdf")

    events = dedupe_events([first, duplicate])

    assert len(events) == 1
    assert "source-a.pdf" in events[0].source_reference
    assert "source-b.pdf" in events[0].source_reference


def test_backward_reconstruction_direction_and_effective_date_boundaries():
    periods, reconstruction = reconstruct_membership_periods(
        current_constituents=[constituent("ALPHA"), constituent("BETA")],
        events=[
            membership_event("BETA", "ADDED", date(2024, 1, 1)),
            membership_event("OLDCO", "REMOVED", date(2024, 6, 1), isin="INE999A01010"),
        ],
        snapshot_date=date(2024, 12, 31),
        target_start_date=date(2024, 1, 1),
        target_end_date=date(2024, 12, 31),
    )

    jan_to_may = {period.symbol for period in periods if period.valid_from == date(2024, 1, 1)}
    jun_to_dec = {period.symbol for period in periods if period.valid_from == date(2024, 6, 1)}
    assert reconstruction["earliest_reconstructable_date"] == "2024-01-01"
    assert "BETA" in jan_to_may
    assert "OLDCO" in jan_to_may
    assert "OLDCO" not in jun_to_dec


def test_query_returns_partial_history_and_does_not_fallback_before_verified_range(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()
    periods, reconstruction = reconstruct_membership_periods(
        current_constituents=[constituent("ALPHA"), constituent("BETA")],
        events=[
            membership_event("BETA", "ADDED", date(2024, 1, 1)),
            membership_event("OLDCO", "REMOVED", date(2024, 6, 1), isin="INE999A01010"),
        ],
        snapshot_date=date(2024, 12, 31),
        target_start_date=date(2024, 1, 1),
        target_end_date=date(2024, 12, 31),
    )
    service.write_csv(
        history_dir / "membership_periods.csv",
        [period_row(period) for period in periods],
        service.MEMBERSHIP_PERIOD_FIELDS,
    )
    (history_dir / "membership_coverage.json").write_text(
        json.dumps(
            {
                "survivorship_bias_status": "PARTIAL_HISTORY",
                "reconstruction": reconstruction,
            }
        ),
        encoding="utf-8",
    )

    before_removal = get_nifty500_members(as_of_date=date(2024, 5, 31), history_dir=history_dir, verbose=True)
    on_removal = get_nifty500_members(as_of_date=date(2024, 6, 1), history_dir=history_dir, verbose=True)
    outside = get_nifty500_members(as_of_date=date(2023, 12, 31), history_dir=history_dir, verbose=True)

    assert before_removal.membership_status == "PARTIAL_HISTORY"
    assert before_removal.source_confidence == "OFFICIAL_EVENTS_PARTIAL"
    assert "OLDCO" in before_removal.symbols
    assert "OLDCO" not in on_removal.symbols
    assert outside.membership_status == "OUTSIDE_VERIFIED_RANGE"
    assert outside.member_count == 0
    assert "current snapshot was not substituted" in outside.provenance_summary


def test_review_cycle_coverage_tracks_expected_and_parsed_cycles():
    cycles = build_review_cycle_coverage(
        target_start_date=date(2024, 1, 1),
        target_end_date=date(2024, 12, 31),
        sources=[
            membership_source(title="Replacements in indices w.e.f. March 28, 2024"),
            membership_source(title="Replacements in indices w.e.f. September 30, 2024"),
        ],
        events=[
            membership_event("BETA", "ADDED", date(2024, 3, 28)),
            membership_event("ALPHA", "REMOVED", date(2024, 9, 30)),
        ],
        manual_review_items=[],
    )

    assert [cycle["cycle"] for cycle in cycles] == ["2024-03", "2024-09"]
    assert all(cycle["source_found"] for cycle in cycles)
    assert all(cycle["parsed"] for cycle in cycles)


def test_superseded_august_2021_pdf_is_resolved_without_events_or_manual_review():
    source = membership_source(
        title="Revision in criteria and replacements in indices",
        announced=date(2021, 8, 23),
        filename="ind_prs23082021.pdf",
    )

    result = parse_membership_source(source, constituents=[])

    assert result.source.parse_status == "SUPERSEDED_BY_LATER_OFFICIAL_RELEASE"
    assert result.source.contains_nifty500_changes is True
    assert result.events == ()
    assert result.manual_review_items == ()
    assert "stands replaced" in result.source.notes


def test_special_heg_dummy_current_count_event_is_parsed():
    source = membership_source(
        title="Corporate Action Adjustment for HEG Ltd. in Nifty indices",
        announced=date(2026, 9, 3),
        filename="ind_prs03092026.pdf",
    )
    text = """
    dummy Symbol DUMMYHEG shall be included at zero price without divisor adjustment
    effective from September 07, 2026.
    1 Nifty 500
    """

    event = parse_special_corporate_action_event(source, text)

    assert event is not None
    assert event.symbol == "DUMMYHEG"
    assert event.event_type == "ADDED"
    assert event.effective_date == date(2026, 9, 7)


def test_identity_alias_mapping_keeps_original_and_canonical_symbols_distinct():
    aliases = identity_alias_rows()

    assert canonical_symbol("ZOMATO", aliases) == "ETERNAL"
    assert canonical_symbol("GMRINFRA", aliases) == "GMRAIRPORT"
    assert canonical_symbol("RELIANCE", aliases) == "RELIANCE"


def test_current_501_count_handling_removes_dummy_before_effective_date():
    periods, _ = reconstruct_membership_periods(
        current_constituents=[constituent("ALPHA"), constituent("DUMMYHEG")],
        events=[
            membership_event("DUMMYHEG", "ADDED", date(2026, 9, 7)),
            membership_event("ALPHA", "ADDED", date(2026, 9, 1)),
        ],
        snapshot_date=date(2026, 9, 7),
        target_start_date=date(2026, 9, 1),
        target_end_date=date(2026, 9, 7),
    )

    assert service.count_members_on(periods, date(2026, 9, 7)) == 2
    assert service.count_members_on(periods, date(2026, 9, 6)) == 1


def test_duplicate_add_without_remove_detection():
    _, reconstruction = reconstruct_membership_periods(
        current_constituents=[constituent("IREDA")],
        events=[
            membership_event("IREDA", "ADDED", date(2024, 9, 30)),
            membership_event("IREDA", "ADDED", date(2024, 3, 28)),
        ],
        snapshot_date=date(2024, 12, 31),
        target_start_date=date(2024, 1, 1),
        target_end_date=date(2024, 12, 31),
    )

    assert any(
        anomaly["issue"] == "add_not_active_after_effective_date"
        for anomaly in reconstruction["event_application_anomalies"]
    )


def test_remove_without_add_detection():
    _, reconstruction = reconstruct_membership_periods(
        current_constituents=[],
        events=[
            membership_event("VGUARD", "REMOVED", date(2026, 3, 30)),
            membership_event("VGUARD", "REMOVED", date(2024, 3, 28)),
        ],
        snapshot_date=date(2026, 9, 7),
        target_start_date=date(2024, 1, 1),
        target_end_date=date(2026, 9, 7),
    )

    assert any(
        anomaly["issue"] == "remove_already_active_after_effective_date"
        for anomaly in reconstruction["event_application_anomalies"]
    )


def test_count_reconciliation_marks_before_after_review_date_state():
    periods, reconstruction = reconstruct_membership_periods(
        current_constituents=[constituent("ALPHA"), constituent("GAMMA")],
        events=[
            membership_event("GAMMA", "ADDED", date(2024, 9, 30)),
            membership_event("BETA", "REMOVED", date(2024, 9, 30)),
            membership_event("BETA", "ADDED", date(2024, 6, 1)),
            membership_event("OLDCO", "REMOVED", date(2024, 6, 1)),
        ],
        snapshot_date=date(2024, 12, 31),
        target_start_date=date(2024, 1, 1),
        target_end_date=date(2024, 12, 31),
    )
    rows = build_membership_reconciliation_rows(
        events=[
            membership_event("GAMMA", "ADDED", date(2024, 9, 30)),
            membership_event("BETA", "REMOVED", date(2024, 9, 30)),
            membership_event("BETA", "ADDED", date(2024, 6, 1)),
            membership_event("OLDCO", "REMOVED", date(2024, 6, 1)),
        ],
        periods=periods,
        reconstruction=reconstruction,
        target_start_date=date(2024, 1, 1),
        target_end_date=date(2024, 12, 31),
    )

    september = [row for row in rows if row["effective_date"] == "2024-09-30"][0]
    assert september["count_before"] == 2
    assert september["actual_after"] == 2
    assert september["difference"] == 0


def test_coverage_status_remains_partial_until_cycles_are_fully_reconciled():
    coverage = build_membership_coverage(
        events=[
            *current_snapshot_events([constituent("ALPHA")], source_metadata=source_metadata()),
            membership_event("BETA", "ADDED", date(2024, 9, 30)),
        ],
        periods=[],
        sources=[membership_source()],
        manual_review_items=[
            ManualReviewItem(
                source_document="fixture.pdf",
                page_section="document",
                issue="pdf_text_extraction_empty",
                suspected_event_company="",
                required_action="Manual review required.",
                confidence="HIGH",
            )
        ],
        constituents=[constituent("ALPHA")],
        source_metadata=source_metadata(),
        reconstruction={
            "method": "BACKWARD_RECONSTRUCTED_FROM_CURRENT_SNAPSHOT",
            "earliest_reconstructable_date": "2024-09-30",
            "latest_reconstructable_date": "2024-12-31",
        },
        review_cycles=[
            {"cycle": "2024-03", "parsed": False},
            {"cycle": "2024-09", "parsed": True},
        ],
        identity_aliases=[],
        reconciliation_rows=[],
        target_start_date=date(2024, 1, 1),
        target_end_date=date(2024, 12, 31),
    )

    assert coverage["survivorship_bias_status"] == "PARTIAL_HISTORY"
    assert coverage["review_cycle_coverage"]["expected_cycles"] == 2
    assert coverage["review_cycle_coverage"]["covered_cycles"] == 1
    assert coverage["manual_review"]["items_remaining"] == 1


def test_final_status_can_only_promote_when_reconciliation_is_clean():
    coverage = build_membership_coverage(
        events=[
            *current_snapshot_events([constituent("ALPHA")], source_metadata=source_metadata()),
            membership_event("BETA", "ADDED", date(2024, 9, 30)),
            membership_event("OLDCO", "REMOVED", date(2024, 9, 30)),
        ],
        periods=[],
        sources=[membership_source()],
        manual_review_items=[],
        constituents=[constituent("ALPHA")],
        source_metadata=source_metadata(),
        reconstruction={
            "method": "BACKWARD_RECONSTRUCTED_FROM_CURRENT_SNAPSHOT",
            "earliest_reconstructable_date": "2024-09-30",
            "latest_reconstructable_date": "2024-12-31",
            "event_application_anomalies": [],
        },
        review_cycles=[
            {"cycle": "2024-09", "parsed": True},
        ],
        identity_aliases=[],
        reconciliation_rows=[
            {
                "effective_date": "2024-09-30",
                "count_before": 1,
                "additions": 1,
                "removals": 1,
                "expected_after": 1,
                "actual_after": 1,
                "difference": 0,
            }
        ],
        target_start_date=date(2024, 9, 1),
        target_end_date=date(2024, 12, 31),
    )

    assert coverage["survivorship_bias_status"] == "SURVIVORSHIP_SAFE"


def membership_source(
    *,
    title: str = "Replacements in indices w.e.f. September 30, 2026",
    announced: date = date(2026, 8, 10),
    filename: str = "fixture.pdf",
) -> OfficialMembershipSource:
    return OfficialMembershipSource(
        title=title,
        url=f"https://www.niftyindices.com/Press_Release/{filename}",
        source_document=filename,
        announced_date=announced,
        filename=filename,
    )


def membership_event(
    symbol: str,
    event_type: str,
    effective_date: date,
    *,
    isin: str = "INE000A01010",
    source_reference: str = "https://www.niftyindices.com/Press_Release/fixture.pdf",
) -> IndexMembershipEvent:
    return IndexMembershipEvent(
        index_name=NIFTY500_INDEX_NAME,
        company_name_original=f"{symbol} Ltd.",
        company_name_normalized=f"{symbol} LTD",
        symbol=symbol,
        isin=isin,
        event_type=event_type,
        announced_date=date(2024, 8, 20),
        effective_date=effective_date,
        source_document="fixture.pdf",
        source_reference=source_reference,
        mapping_method="EXPLICIT_SYMBOL",
        mapping_confidence="HIGH",
        extraction_confidence="HIGH",
        review_status="PARSED",
        notes="Fixture",
    )


def constituent(symbol: str) -> Nifty500Constituent:
    return Nifty500Constituent(
        trading_symbol=symbol,
        company_name=f"{symbol} Ltd.",
        isin=f"INE{symbol[:3].ljust(3, 'X')}A01010",
        sector="",
        industry="Fixture",
        index_name=NIFTY500_INDEX_NAME,
        source="https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
        source_date="2024-12-31",
    )


def source_metadata() -> dict[str, str]:
    return {
        "source_url": "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
        "source": "Nifty Indices official constituent CSV",
        "source_date": "2024-12-31",
        "downloaded_at": "2024-12-31T00:00:00+00:00",
    }
