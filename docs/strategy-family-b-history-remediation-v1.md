# Family B development history remediation V1

## Scope and reason

`FAMILY_B_DEVELOPMENT_HISTORY_REMEDIATION_V1` implements the
`SMA200_PREHISTORY_READINESS_V1` profile. The frozen daily research history
previously began on 2021-09-07, leaving only 140 valid sessions at the first
2022 Family B formation and confounding the B002 trend-filter evidence with
dataset availability. This command changes data coverage only. It does not
change B001 or B002, create B003, create Strategy V2, or evaluate performance.

The immutable input gate verified attribution-audit hash
`cdcef2b88766f501f6b7d21a2c1dd1cc93f79287f79c09d02dfef7f84142a0f1`
and all frozen Family B configuration, success-criteria, control, MOM-B-001,
MOM-B-002, and development-registry hashes.

## Source, dates, and lineage

The extension uses the project's existing official NSE daily bhavcopy source
architecture and official NSE corporate-action endpoint. No new provider was
introduced. The source-native raw archives are full-market files; normalized
and adjusted remediation output is restricted to the 607 causal Family B
formation symbols plus nine required raw aliases (616 raw identifiers).

The requested prehistory starts on 2020-01-01 and ends on 2021-09-06, directly
before the immutable V1 daily start. Acquisition produced 418 official trading
sessions, 832,924 normalized full-market records, and zero failed sessions.
The required-symbol structural layer contains 203,205 normalized and adjusted
rows across 524 symbols. The versioned lineage remains:

`SOURCE / RAW -> NORMALIZED -> CORPORATE ACTION STRUCTURAL LAYER -> ADJUSTED DAILY -> SMA READINESS`

The performance development period remains exactly 2022-01-01 through
2024-12-31. Rows from 2020 and 2021 are signal-formation prehistory only for
the existing 6M, SMA200, liquidity, and corporate-action dependencies; they are
not performance observations.

## Identity continuity and point-in-time membership

Formation-date membership and the frozen 302-row B002 candidate population are
unchanged. Historical prices are not required to be observations from dates on
which the security was a Nifty 500 member. The remediation adds only documented
identity continuity for `MAGMA -> POONAWALLA`, `ORIENTREF -> RHIM`, and
`AMARAJABAT -> ARE&M`, supported by dated NSE daily records and frozen
membership/ISIN evidence. It does not substitute a future survivor into the
formation population.

## Corporate actions and overlap reconciliation

The added prehistory includes 3,376 official corporate-action events and 56
price-adjustment factors under `PRICE_ADJUSTED_STRUCTURAL_V1`. Corporate-action
inputs are bounded by the unchanged 2024-12-31 development end. There are
35,192 required-symbol rows with a non-unit adjustment factor. Complex or
manual-review cases remain unavailable; no factor or price history is invented.

The V2 extension does not duplicate or overwrite the frozen V1 overlap. It
references V1 for 2021-09-07 through 2024-12-31 and applies versioned logical
identity metadata. Of 503,221 compared rows, 502,692 are exact and 529 have
explained identity-only differences. Numeric fields and eligibility flags are
identical, with zero unexplained differences. Therefore
`DAILY_HISTORY_REMEDIATION_RECONCILIATION = EXPLAINED_VERSIONED_DIFFERENCES`.

## SMA200 availability before and after

The audit reproduces the frozen 302 B002 top-decile candidates and 30 original
SMA-unavailable rows. After remediation, 20 dataset-truncation cases and three
identity-continuity cases are resolved. Seven rows remain unavailable:

- five genuine recent listings: DEVYANI, AWL, RAINBOW, SIGNATURE, and DOMS;
- two corporate-action/data-quality exclusions: BORORENEW and TATAELXSI;
- zero official-source gaps, unresolved identities, other unexplained cases, or
  unexplained cases.

At the 2022-03-31 formation, 20 of the original 23 candidates now have an exact
200-session SMA and three remain unavailable. Every available SMA uses exactly
200 valid observations ending no later than formation; no SMA150, SMA100,
expanding mean, partial window, calendar-day approximation, imputation, or
future observation is used.

`SMA200_STRUCTURAL_COVERAGE_RATE = 97.68211920529801324503311258%` (295/302),
classified `STRONG`. Excluding the five genuine recent listings,
`SMA200_REMEDIABLE_COVERAGE_RATE = 99.32659932659932659932659933%` (295/297).

## Readiness and limitations

`FAMILY_B_HISTORY_REMEDIATION_RESULT = READY_FOR_CLEAN_DEVELOPMENT_REEVALUATION`
and `FAMILY_B_B002_REEVALUATION_READINESS = YES`. This authorizes only a later,
separately requested controlled reevaluation using the unchanged frozen B002
rules. It does not execute that reevaluation.

`B001_STATUS_AFTER_ATTRIBUTION = NO_DISTINCT_FILTER_EVIDENCE` and
`B002_STATUS_BEFORE_REEVALUATION = CONFOUNDED_BY_HISTORY_AVAILABILITY` remain
unchanged. The known limitations are the five genuine recent listings, two
explicit corporate-action exclusions, source-native full-market raw archives,
the immutable V1 overlap-reference design, and the frozen partial confidence of
the point-in-time membership reconstruction.

No B002 return, ending equity, CAGR, drawdown, Sharpe, yearly return, or outcome
was computed or inspected. No 2025+ price row or validation result was loaded.
No live signal, live order, broker call, remote migration, database write, or
Supabase persistence occurred.

## Frozen hashes

- `history_remediation_config_hash`: `f7c60aaafc2661b163fb8c59c3b0ac5a68801b686e17a76ddd72938852a0657c`
- `raw_extension_hash`: `e28b00f7bbff8ae85da54cfc0bbc6cbd06192a085f7663645c7e0392d61bc017`
- `adjusted_extension_hash`: `3293f8e27ea17c0ef72946c538cab4463b4c08adf59c348fed9f3ea6bee9ad3d`
- `family_b_sma_readiness_hash`: `7757839611d462b86cc09f3559e1664020a024795995744f50d6d5023ff46c5a`
