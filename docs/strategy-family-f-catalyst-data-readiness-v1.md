# Family F Catalyst Data Readiness V1

## Scope

`FAMILY_F_CATALYST_DATA_READINESS_V1` is a source-architecture audit for the high-level `FAMILY_F_CATALYST_MOMENTUM` concept: a point-in-time corporate or market catalyst, later combined with independent price and volume confirmation and continuation behavior. This command is `DATA_READINESS_ONLY`. It defines no strategy, entry, exit, ranking, weighting, sizing, or experiment and runs no performance research.

The desired future DEVELOPMENT window is 2022-01-01 through 2024-12-31 in the frozen point-in-time Nifty 500 universe. A data audit comes first because an effective date, accounting-period date, revised document, or download time does not prove when information became public. Without trustworthy publication time and historical identity, a catalyst study would be vulnerable to look-ahead and survivorship bias.

## Source hierarchy and inventory

The preferred hierarchy is: NSE official filings and announcements; BSE official filings where useful; SEBI or other regulator records; company investor-relations disclosures; official index-provider notices; and licensed reliable structured providers. Generic media is secondary evidence and cannot independently generate a future catalyst signal when unverified.

The repository contains two event-like datasets: official NSE corporate-action effective events and official Nifty Indices membership-change notices. It also contains a `news_events` database schema placeholder with no populated historical source and daily plus bounded five-minute price/volume infrastructure. Therefore the project has four relevant existing source implementations or placeholders, but only two populated event datasets. No local historical exchange-announcement, financial-result, analyst-consensus, rating-change, insider, bulk/block, or regulator-order dataset was found.

The NSE corporate-action layer covers effective events from 2020-01-06 through 2026-09-07 when its frozen Family B extension is combined with the base dataset. It does not retain original announcement timestamps. The Nifty notice archive has original announcement dates separate from effective dates from 2021-06-15 onward, but the normalized local records retain date only. Both are official and useful for architecture, but neither is safe for same-day causal research as stored.

Official capability candidates are NSE corporate announcements and XBRL filings, BSE corporate announcements, NSE insider and bulk/block archives, SEBI orders, Nifty Indices notices, and primary rating-agency rationales. Public web availability is not proof of bulk-use, automation, or redistribution rights. The acquisition plan requires terms review and small pilots before any multi-year retrieval. NSE licensed historical corporate-announcement delivery and a licensed point-in-time consensus product are potential later subscriptions; none is required or authorized now.

## Catalyst taxonomy and readiness

The audit covers 17 categories:

A. financial results
B. earnings surprise or material earnings change
C. corporate announcements or exchange filings
D. large order or contract wins
E. regulatory approval or rejection
F. management guidance or revision
G. mergers, acquisitions, and demergers
H. buybacks
I. dividends
J. stock splits and bonus issues
K. preferential allotment, QIP, and fundraising
L. promoter, insider, bulk, and block transactions
M. index inclusion or exclusion
N. rating upgrades or downgrades
O. board decisions and material corporate actions
P. exchange surveillance or regulatory action
Q. other material NSE/BSE filings

No category is currently `READY` under the preferred threshold of at least 95% trustworthy point-in-time timestamps, at least 95% canonical linkage, adequate presence in 2022–2024, stable semantics, acceptable licensing, and reproducible retrieval. Exchange filings, financial results, orders/contracts, regulatory events, guidance, buybacks, insider/bulk/block events, ratings, board decisions, surveillance actions, and other filings are `SOURCE_AVAILABLE_NOT_INGESTED`. Categories represented only by local corporate-action effective dates and local index notice dates are `TIMESTAMP_INSUFFICIENT` for same-day work.

`HISTORICAL_EARNINGS_SURPRISE_READINESS = NOT_AVAILABLE`. Reported revenue, profit, and EPS may be obtainable from exchange result filings, but the project has no point-in-time historical analyst-consensus vintages. No surprise value may be manufactured from later estimates or price behavior.

For order and contract disclosures, structured exchange categories may narrow candidates, but robust subcategory detection can still require document text. A future auditable pipeline may proceed from immutable raw filing to deterministic metadata, text extraction, versioned classifier, confidence, evidence, and human/audit trace. AI may classify a real retained source document; it must never invent a catalyst.

## Timestamp and market-session policy

Timestamp classes are `EXACT_EXCHANGE_TIMESTAMP`, `RELIABLE_PUBLICATION_TIMESTAMP`, `DATE_ONLY`, `INFERRED`, and `UNKNOWN`. Normal future research should use only the first two unless a separate conservative design is preregistered. Session buckets use Asia/Kolkata and are `PRE_OPEN`, `DURING_MARKET`, `POST_CLOSE`, `NON_TRADING_DAY`, and `DATE_ONLY_UNKNOWN_TIME`.

An event is unusable for same-day causal research unless its source timestamp can establish that the information was public before a hypothetical entry. Effective dates, financial periods, future-corrected timestamps, and download times are insufficient alone. Date-only records may support a later next-session design only after that timing convention is explicitly preregistered; no such strategy design is part of this command.

## Entity linkage and normalized model

Linkage classes are `EXACT_ISIN`, `EXACT_SYMBOL_DATE_VALID`, `ALIAS_RESOLVED`, `COMPANY_NAME_ONLY`, `AMBIGUOUS`, and `UNRESOLVED`. Future records must map source identifiers, company name, symbol, and ISIN to the frozen date-valid canonical security identity. Current identifiers must not be projected backward without an audited alias chain.

The proposed schema is: `event_id`, `source`, `source_document_id`, `published_at`, `market_timing_bucket`, `symbol`, `isin`, `canonical_security_id`, `event_category`, `event_subcategory`, `headline`, `structured_fields`, `classification_method`, `classification_version`, `classification_confidence`, `source_reliability`, `revision_id`, `supersedes_event_id`, `raw_reference`, and `ingested_at`. This is design only; no database migration was created.

Raw provenance is immutable. Revised, withdrawn, or corrected records must preserve the original publication, revision time, and chain. Primary deduplication uses `(source, source_document_id)`; a deterministic fallback uses `(source, ISIN-or-symbol, publication timestamp, event category)`. Cross-source reports about the same fact remain related records rather than destroying provenance.

## Reliability, licensing, and leakage controls

Reliability tiers are `TIER_1_OFFICIAL`, `TIER_2_PRIMARY_COMPANY`, `TIER_3_LICENSED_STRUCTURED`, `TIER_4_SECONDARY_MEDIA`, and `UNVERIFIED`; future Family F research should prefer tiers 1–3. Licensing states are `PUBLIC_OFFICIAL`, `PUBLIC_WITH_LIMITATIONS`, `LICENSED_REQUIRED`, and `UNKNOWN_LICENSE`.

Principal leakage risks are confusing effective and publication dates, replacing originals with revisions, applying current identifiers historically, treating post-close disclosures as same-session information, using future-created labels, survivorship bias, later consensus revisions, and duplicate announcements. The manifest and risk register make each control explicit.

## Price/volume readiness and current decision

Existing data can later provide daily return, daily volume, relative volume, date-valid market membership, and a next-open execution reference. Five-minute confirmation is available only for a bounded symbol set; full-Nifty-500 intraday confirmation remains unavailable. No signals were calculated.

The initial categories ranked solely by data integrity are: official exchange announcements, structured financial results excluding surprise, index notices, corporate-action announcements, official insider/bulk/block disclosures, and rating-agency disclosures. Each remains conditional on its acquisition pilot; this ranking makes no profitability claim.

`FAMILY_F_DATA_READINESS = SOURCE_ACQUISITION_REQUIRED` and `FAMILY_F_PREREGISTRATION_READINESS = NO`. The acquisition plan specifies sources, dates, fields, timestamp and identity requirements, licensing actions, and measured pilots of 5–10 point-in-time Nifty 500 symbols across 2022, 2023, and 2024. No acquisition, provider connection, subscription, bulk scrape, validation access, strategy implementation, or Strategy V2 work occurred.
