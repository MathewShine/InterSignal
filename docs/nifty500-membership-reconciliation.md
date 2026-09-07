# Nifty 500 Membership Reconciliation

Current phase: Step 02.3D-Fix / Command 02 - count drift reconciliation

## Unresolved PDF Review

- `ind_prs23082021.pdf`: Visually reviewed pages 1, 3 and 4. The PDF contains 23 Nifty 500 exclusions and 23 inclusions effective September 30, 2021, but the later official September 15, 2021 release states the August 23 REIT/InvIT inclusions were revoked and the earlier replacement list stands replaced. Events from this superseded document are not applied.
- OCR was not used; visual inspection of rendered pages was sufficient.

## Official Current Count

- Current snapshot source date: 2026-09-07
- Current snapshot row count: 501
- Explanation: The official current constituent CSV dated 2026-09-07 contains 501 unique symbols and 501 unique ISINs. The extra constituent is DUMMYHEG, a dummy symbol for the HEG Ltd. demerger, supported by the official September 03, 2026 corporate-action press release effective September 07, 2026.

## Root Causes

- Current 501 count is explained by the official DUMMYHEG demerger adjustment effective 2026-09-07.
- Several historical rows use earlier symbols/names that map to current official constituent identities; these are captured in `membership_identity_aliases.csv`.
- Remaining count drift is tied to official lifecycle inconsistencies that need manual source reconciliation, especially repeated or missing add/remove events.

## Identity Aliases

- AKZOINDIA -> JSWDULUX: Official Nifty 500 lifecycle uses AKZOINDIA before the current constituent snapshot lists JSW Dulux Ltd. with the same exchange instrument identity.
- GET&D -> GVT&D: Official Nifty 500 lifecycle uses GET&D before the current constituent snapshot lists GE Vernova T&D India Ltd. as GVT&D.
- GMRINFRA -> GMRAIRPORT: Official Nifty 500 lifecycle uses GMRINFRA before the current constituent snapshot lists GMR Airports Ltd. as GMRAIRPORT.
- HBLPOWER -> HBLENGINE: Official Nifty 500 lifecycle uses HBLPOWER before the current constituent snapshot lists HBL Engineering Ltd. as HBLENGINE.
- MFL -> EPIGRAL: Official Nifty 500 lifecycle adds Meghmani Finechem Ltd. as MFL and later removes Epigral Ltd.; treated as one canonical identity for lifecycle counting.
- SWANENERGY -> SWANCORP: Official Nifty 500 lifecycle uses SWANENERGY before the current constituent snapshot lists Swan Corp Ltd. as SWANCORP.
- ZOMATO -> ETERNAL: Official Nifty 500 lifecycle uses ZOMATO before the current constituent snapshot lists Eternal Ltd. as ETERNAL.

## Event Extraction

- Official documents inventoried: 135
- Documents containing Nifty 500 changes: 35
- Historical ADD events: 305
- Historical REMOVE events: 304
- Current snapshot events: 501
- Effective event range: 2021-06-30 to 2026-09-30

## Reconciliation Summary

- Reconstructed coverage: 2021-09-30 to 2026-09-07
- Rows with count differences: 1
- First count difference: 2024-09-30
- Lifecycle anomalies remaining: 3

## Per-Effective-Date Reconciliation

| effective_date | count_before | additions | removals | expected_after | actual_after | difference | notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 2021-09-30 |  | 22 | 22 |  | 499 |  | Count before this date is outside the reconstructed coverage range. |
| 2021-10-29 | 499 | 1 | 1 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2022-03-31 | 499 | 32 | 32 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2022-04-07 | 499 | 1 | 1 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2022-04-12 | 499 | 1 | 1 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2022-05-04 | 499 | 1 | 1 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2022-05-31 | 499 | 1 | 1 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2022-08-08 | 499 | 3 | 3 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2022-09-30 | 499 | 19 | 19 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2022-12-30 | 499 | 4 | 4 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2023-02-17 | 499 | 1 | 1 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2023-03-31 | 499 | 20 | 20 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2023-04-28 | 499 | 2 | 2 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2023-07-13 | 499 | 1 | 1 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2023-09-29 | 499 | 18 | 18 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2023-10-26 | 499 | 1 | 1 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2024-03-28 | 499 | 34 | 34 | 499 | 499 | 0 | Count reconciles against applied event totals for this effective date. |
| 2024-09-30 | 499 | 27 | 27 | 499 | 500 | 1 | Count difference remains; see lifecycle anomalies and identity alias notes. |
| 2024-10-10 | 500 | 1 | 1 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2024-10-16 | 500 | 1 | 1 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2025-03-21 | 500 | 1 | 1 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2025-03-28 | 500 | 30 | 30 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2025-04-11 | 500 | 1 | 1 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2025-09-23 | 500 | 1 | 1 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2025-09-30 | 500 | 18 | 18 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2025-12-31 | 500 | 1 | 1 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2026-03-30 | 500 | 31 | 31 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2026-05-12 | 500 | 1 | 1 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2026-07-17 | 500 | 1 | 1 | 500 | 500 | 0 | Count reconciles against applied event totals for this effective date. |
| 2026-09-07 | 500 | 1 | 0 | 501 | 501 | 0 | Count reconciles against applied event totals for this effective date. |

## Lifecycle Anomalies

- 2024-09-30 REMOVED IDEA (IDEA): remove_already_active_after_effective_date from ind_prs23082024.pdf
- 2024-03-28 ADDED IREDA (IREDA): add_not_active_after_effective_date from ind_prs28022024.pdf
- 2024-03-28 REMOVED VGUARD (VGUARD): remove_already_active_after_effective_date from ind_prs28022024.pdf

## Query Counts

| date | before_command_02 | after_command_02 | status |
| --- | ---: | ---: | --- |
| 2026-09-07 | 501 | 501 | PARTIAL_HISTORY |
| 2025-06-15 | 502 | 500 | PARTIAL_HISTORY |
| 2024-06-15 | 502 | 499 | PARTIAL_HISTORY |
| 2023-06-15 | 503 | 499 | PARTIAL_HISTORY |
| 2022-06-15 | 505 | 499 | PARTIAL_HISTORY |

## Final Status

- Survivorship-bias status: PARTIAL_HISTORY

## Remaining Limitations

- Historical membership is reconstructed from parsed official documents but has not been manually reconciled end to end.
- Lifecycle anomalies remain unresolved: 3 event applications need review.
- Count reconciliation differences remain on 1 effective dates.

## Safety

- ZERO order endpoints were called.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.
- ZERO strategy, indicator, backtest, or signal calculations were executed.
