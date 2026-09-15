# Family F Official-Source Pilot V1

## Scope and decision

`FAMILY_F_OFFICIAL_SOURCE_PILOT_V1` / `CATALYST_TIMESTAMP_LINKAGE_PILOT_V1` is a small source-quality pilot. It asks whether official historical sources can support trustworthy point-in-time timestamps, reproducible documents, and canonical security linkage. It does not define a Family F strategy, trading parameters, catalyst weights, signals, or price outcomes. Family F remains `DATA_READINESS_ONLY` and preregistration readiness remains `NO`.

The pilot result is `FAMILY_F_HISTORICAL_ACQUISITION_READINESS = CONDITIONAL`, with `FAMILY_F_NEXT_STAGE = LICENSE_RESOLUTION`. NSE corporate announcements passed the technical timestamp, linkage, document-identity, and reproducibility thresholds, but NSE terms prohibit systematic or automated collection through the public website. No full historical acquisition may begin until an authorized or licensed delivery route is documented.

## Frozen baseline and deterministic sample

The pilot verifies the Family F Command 01 data-readiness hash `45ce21fdbf020cd990bdd9ca727e0d278de1eb9d5132d3cba18a70fb72ca0765` and the Family E closure hash `4899cdbfe54b0ea636faa8ff0b4504b6ef60242e7eabdf682b2b913cfb001c00`.

Before network inspection, the command selected eight point-in-time Nifty 500 securities for 2022–2024. Four full-window members were ranked by SHA-256 over command identity, stratum, symbol, and ISIN; one official index-notice event security per year and one supplementary event security were ranked the same way. No price or later outcome field participated. The frozen population is BHARATFORG, SUNPHARMA, SOBHA, FACT, UCOBANK, GILLETTE, SBFC, and ANANTRAJ. The 24-row request plan has hash `8522ea20315ca6632a75f06694c615b7dd1a0ff4526c5bddf4b78a585ca1a98d`.

## Official sources and historical access

The bounded plan attempted these Tier 1 official groups:

- NSE corporate announcements and filings.
- NSE structured/XBRL financial-result filings.
- Nifty Indices press releases and notice documents.
- NSE insider, bulk, block, and disclosure archives.
- BSE corporate announcements as a secondary exchange cross-check.
- SEBI orders and regulatory disclosures.
- ICRA and CRISIL rating disclosures.

Twenty-one NSE corporate-announcement records and six pre-existing official Nifty notice records were retained. The NSE announcement table exposed separately labeled exchange receipt and exchange dissemination times. One stable SUNPHARMA archive document lacked a labeled timestamp in the bounded response and remains `UNKNOWN`; digits in its filename were not treated as a timestamp. The NSE XBRL historical slice, NSE transaction archive, SEBI entity matches, and ICRA issuer matches were inconclusive in the bounded attempt. BSE and CRISIL automated retrieval did not return accessible content, so each is recorded as `AUTOMATION_ACCESS_RESTRICTED`; no controls were bypassed and counts were not chased.

## Timestamp semantics and market timing

For NSE announcements, `Exchange Dissemination Time` is retained as the public-availability timestamp and classified `EXACT_EXCHANGE_TIMESTAMP`. `Exchange Received Time` remains separate provenance. Timestamps are timezone-aware and normalized to `Asia/Kolkata`, then classified as `PRE_OPEN`, `DURING_MARKET`, `POST_CLOSE`, or `NON_TRADING_DAY`. Exact timestamps are same-day causal-research ready; `DATE_ONLY`, `INFERRED`, and `UNKNOWN` records are not.

Nifty notice publication dates are classified `DATE_ONLY`. The original announcement date and later effective inclusion/exclusion date are retained separately. These records are not safe for same-day causal research without a trustworthy time of publication.

Across all 27 records, 20 (74.07%) have exact exchange timestamps, six (22.22%) are date-only, and one (3.70%) is unknown. Twenty records (74.07%) are same-day causal-ready. Metrics are based only on actually inspected records.

## Linkage, document identity, revisions, and duplicates

NSE announcement rows use the official exchange symbol joined to the frozen date-valid membership mapping and are `EXACT_SYMBOL_DATE_VALID`; source rows are not promoted to `EXACT_ISIN` when the ISIN is absent from the source. Nifty notice rows with an explicit/mapped ISIN are `EXACT_ISIN`. All 27 retained records have canonical linkage, stable source document IDs, and reproducible official references.

The primary duplicate key is `(source, source_document_id)`. The fallback key is `(source, ISIN-or-symbol, published_at, event_category)`. Neither key collided in the retained sample, and no record was removed.

No corrected, withdrawn, or superseded filing with an explicit revision link was observed in the retained metadata. The result is not evidence that revisions do not occur: revision capability remains unproven. Future acquisition must retain originals and revisions independently and connect them only through explicit source lineage.

## Announcement categories and text

The feasibility mapping distinguishes order/contract, board decision, fundraising, M&A, buyback, dividend, split/bonus, regulatory, and other filing subjects. It is a transparent keyword audit, not a production classifier. Generic subjects such as “Press Release” and “Communication under Regulation 30” do not reliably establish a catalyst category, so `TEXT_CLASSIFICATION_REQUIRED = YES`. No positive, negative, bullish, or bearish labels are created.

## Reconciliation and cross-checks

For the 20 fully timestamped NSE records, receipt-to-dissemination differences were 2–14 seconds and are `SMALL_EXPLAINABLE_DIFFERENCE`: the fields describe different stages, and the later dissemination time is retained. The BSE cross-check remains `UNKNOWN_SEMANTICS` because the bounded access attempt was restricted. No BSE timestamp replaces an NSE timestamp, and source-specific lineage is preserved.

## Licensing and source-category results

NSE corporate announcements, XBRL, and transaction archives are `AUTOMATION_RESTRICTED` because current NSE Terms of Use prohibit systematic or automated website data collection. Nifty Indices, SEBI, and ICRA are `PUBLIC_ACCESS_TERMS_REVIEW_REQUIRED`; public visibility is not treated as permission for historical acquisition. BSE and CRISIL remain `UNKNOWN` on licensing because their bounded automated access attempts did not establish usable terms.

Results by source/category:

| Source | Records | Result | Reason |
| --- | ---: | --- | --- |
| NSE corporate announcements | 21 | `PILOT_CONDITIONAL` | 95.24% trusted timestamps and 100% linkage/document integrity; authorized access unresolved. |
| NSE XBRL financial results | 0 | `INCONCLUSIVE` | No structured historical result retained for the planned slice. |
| Nifty Indices notices | 6 | `PILOT_FAIL` | Publication is date-only, below the 95% timestamp threshold. |
| NSE insider/bulk/block archive | 0 | `INCONCLUSIVE` | No bounded matched record retained. |
| BSE corporate announcements | 0 | `ACCESS_RESTRICTED` | Bounded automated access did not return usable content. |
| SEBI orders/actions | 0 | `INCONCLUSIVE` | Official index visible; no matched pilot-security record retained. |
| ICRA rating rationales | 0 | `INCONCLUSIVE` | Official search visible; no matched issuer record retained. |
| CRISIL rating disclosures | 0 | `ACCESS_RESTRICTED` | Bounded automated access did not return usable content. |

The financial-results pilot therefore remains inconclusive and does not compute earnings surprise. The rating pilot is split between ICRA inconclusive and CRISIL access-restricted. These negative infrastructure findings are retained.

## Acquisition candidate and future plan

The sole ranked candidate is NSE corporate announcements. A future acquisition would cover 2022-01-01 through 2024-12-31 and require source document ID/reference, official symbol, date-valid ISIN mapping, subject, exchange receipt and dissemination timestamps, revision identifiers, raw metadata, retrieval timestamps, and immutable hashes. It would use authorized bounded pagination with checkpoint/resume, documented rate limits and backoff, immutable raw payload/document storage, and append-only normalized records that preserve source-specific lineage. Written permission or a licensed official delivery mechanism is a prerequisite. This command does not execute that acquisition.

## Safety boundary

The pilot used no historical analyst consensus and preserves `HISTORICAL_EARNINGS_SURPRISE_READINESS = NOT_AVAILABLE`. It performed no bulk crawl, subscription purchase, paywall or anti-bot bypass, validation access, broker call, order, remote migration, or Supabase persistence. It created no Strategy V2 or Family G work and must stop at Command 02.
