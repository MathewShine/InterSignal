# Corporate Actions And Adjusted Prices

Current phase: Step 02.3E / Command 01 - corporate-action event layer and adjusted research price series

## Sources Used

- NSE corporate actions page: https://www.nseindia.com/companies-listing/corporate-filings-actions
- NSE corporate actions API: https://www.nseindia.com/api/corporates-corporateActions
- Source manifest: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reference\nse\corporate_actions\corporate_action_source_manifest.csv
- Raw source artifacts are cached separately from normalized events.

## Coverage

- Start date: 2021-09-07
- End date: 2026-09-07
- Official events acquired: 12257
- Adjustment factors generated: 522

## Action Types Found

- STOCK_SPLIT: 267
- BONUS: 255
- DIVIDEND: 7498
- SPECIAL_DIVIDEND: 193
- RIGHTS: 207
- MERGER/DEMERGER/SPINOFF: 62
- SYMBOL/NAME changes: 0
- OTHER/UNKNOWN: 3772

## Adjustment Methodology

- Methodology version: PRICE_ADJUSTED_STRUCTURAL_V1
- Price target: PRICE_ADJUSTED
- Structural policy: Backward-adjust pre-ex-date OHLC for verified structural split, bonus, and face-value events only.
- Dividend policy: INFORMATIONAL_ONLY
- Special dividend policy: MANUAL_REVIEW_REQUIRED
- Rights policy: ADJUSTMENT_REQUIRES_REVIEW
- Merger/demerger policy: CONTINUITY_BREAK; no naive mechanical price factor is created.
- Symbol identity policy: Symbol/name changes are identity events, not price events; ISIN is preferred when present.
- Adjusted-volume policy: Adjusted volume is generated with the inverse structural price factor.

## Suspect Reconciliation

- Existing suspect rows reconciled: 808
- CONFIRMED_CORPORATE_ACTION: 418
- LIKELY_CORPORATE_ACTION: 9
- MARKET_MOVE: 78
- DATA_QUALITY_ISSUE: 0
- IDENTITY_CHANGE: 0
- UNRESOLVED: 303
- Reconciliation CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\corporate_action_suspect_reconciliation.csv

## Pilot Examples

- type=STOCK_SPLIT, symbol=FISCHER, date=2025-09-12, raw_gap=-89.9965, adjusted_gap=0.0353, status=PASS
- type=BONUS, symbol=ECLERX, date=2026-03-13, raw_gap=-49.9778, adjusted_gap=0.0444, status=PASS
- type=NO_ACTION, symbol=AARVEEDEN, date=2021-09-08, raw_gap=-0.2717, adjusted_gap=-0.2717, status=PASS
- type=DEMERGER, symbol=ARSHIYA, date=2022-03-03, raw_gap=-16.0156, adjusted_gap=-16.0156, status=CONTINUITY_BREAK
- type=SUSPECT_RECONCILIATION, symbol=GANGAFORGE, date=2021-09-13, raw_gap=-89.7445, adjusted_gap=, status=CONFIRMED_CORPORATE_ACTION

## Adjusted Dataset

- Full processing completed: True
- Output path: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\research\adjusted\daily\nse
- Output format: partitioned CSV
- Records generated: 3246754
- Records with adjusted factor applied: 235657
- ADJUSTED_READY: 2069715
- RAW_ONLY: 821584
- CONTINUITY_BREAK: 60517
- MANUAL_REVIEW_REQUIRED: 294938

## Auditability

- Every adjusted row carries raw OHLCV, adjusted OHLCV, cumulative factor, event count, methodology version, and source-event provenance.
- Official raw NSE files and normalized RAW candles are not overwritten by this step.
- Raw input integrity unchanged: True

## Known Limitations

- NSE corporate-action rows do not always include ISIN values, so symbol-level identity remains the default when ISIN is absent.
- Rights issues, special dividends, mergers, demergers, and spinoffs are stored and flagged, not mechanically adjusted.
- This is not a total-return series; ordinary dividends remain informational only.
- Suspect reconciliation is official-source based and conservative; unmatched discontinuities remain UNRESOLVED or MARKET_MOVE.

## Safety

- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.
- ZERO strategy calculations were executed.
