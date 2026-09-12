# Early-Path Recovery Diagnostic V1

## Status and purpose

`EARLY_PATH_RECOVERY_DIAGNOSTIC_V1` is a preregistered, offline, DEVELOPMENT-only diagnostic under profile `DEVELOPMENT_EARLY_PATH_RECOVERY_V1` and family `EARLY_PATH_QUALITY_DIAGNOSTIC`. It characterizes the first three canonical 5-minute bars and their association with the frozen opportunity path. It creates no entry rule, chooses no winner, changes no Strategy V1 component, runs no portfolio, authorizes no validation, and creates no Strategy V2.

This work is distinct from Command 02's failed controlled rule `first completed 10m close >= T+1 open`. Command 02 tested a treatment rule and found rejection separation without improved treatment outcomes. Command 03 does not retest that rule or assign a recovery-based entry. It asks whether the *shape* of weakness, recovery, persistence, higher lows, and range location carries descriptive information that could justify a separately preregistered controlled experiment.

## Temporal and population governance

- Development window: 2022-01-01 through 2024-12-31 only.
- Validation: `SEALED`; run count `0`; validation rows accessed `0`; no 2025+ or holdout performance.
- Source: real canonical Groww 5-minute DEVELOPMENT data. Synthetic data is used only by offline tests.
- Population: the same strict-covered, CA-safe frozen opportunity population used by Commands 01/02 where possible, with frozen stop and target and all three opening bars available.
- Exact source population: 1,101; frozen admitted subset: 253; exclusions: none.
- Selected scope: 100 symbols, exactly 53.2398% of the current 2,068-opportunity DEVELOPMENT denominator. Earlier planning language rounded this to about 53.7%; this is selected-scope research, not whole-universe proof.
- Population hash: `49c9243b76a6de6cee38d9f293cb5b510e45ec90f25fb6bfce76ede7fe09c1c8`.
- Preregistration hash: `912f42ca7a6c58d4b64cfc0f42fb9e886e3b7d13ebf400b42144bc28a50a5fa8`.

The immutable population manifest was written before outcome computation. It includes opportunity identity, frozen daily fields, T+1 open, frozen stop/target/R:R, the first three canonical bars, quality and CA-safety metadata, and the frozen admitted flag. Price data uses the same causal in-memory T+1-open alignment as Commands 01/02; raw provider data is not altered.

## Causal bar and path definitions

`open_0` is the T+1 session open. `c1/h1/l1`, `c2/h2/l2`, and `c3/h3/l3` come respectively from completed bars 09:15–09:20, 09:20–09:25, and 09:25–09:30. All classifications depend only on information available by 09:30.

First-five-minute state:

- `FIRST5_STRONG`: `c1 > open_0`.
- `FIRST5_WEAK`: `c1 < open_0`.
- `FIRST5_FLAT`: `c1 == open_0` at canonical Decimal precision, with no tolerance band.

Recovery state:

- For `FIRST5_WEAK`, `RECOVER_BY_10` means `c2 >= open_0`; `PARTIAL_RECOVERY_BY_10` means `c1 < c2 < open_0`; `PERSISTENT_WEAK_TO_10` means `c2 <= c1` and `c2 < open_0`.
- For paths still below open at 10 minutes, `RECOVER_BY_15` means `c3 >= open_0`; `PARTIAL_RECOVERY_BY_15` means `c2 < c3 < open_0`; `PERSISTENT_WEAK_TO_15` means `c3 <= c2` and `c3 < open_0`.

Open-reclaim state:

- `NEVER_BELOW_OPEN_FIRST15`: all three completed closes are at/above `open_0`.
- `DIP_AND_RECLAIM_BY_10`: `c1 < open_0` and `c2 >= open_0`.
- `DIP_AND_RECLAIM_BY_15`: `c1 < open_0`, `c2 < open_0`, and `c3 >= open_0`.
- `BELOW_OPEN_AT_15`: `c3 < open_0`.
- `MIXED_OPEN_RECLAIM`: the deterministic residual, such as an initially strong path that later dips and finishes back at/above open.

Reclaim-time buckets are `NONE`, `5M`, `10M`, and `15M`. `10M` and `15M` are literal first completed-close reclaims after one or two prior closes below open. `5M` means the first completed bar was already at/above open; there is no prior completed 5-minute close in the observed window. `NONE` means all three completed closes remained below open. Reclaim states are descriptive labels, never trading rules.

Higher-low structure uses strict comparisons with no ATR or tick buffer: `HIGHER_LOW_10 = l2 > l1`, `HIGHER_LOW_15 = l3 > l2`, `TWO_STEP_HIGHER_LOW` means both, `ONE_STEP_HIGHER_LOW` means exactly one, and `NO_HIGHER_LOW` means neither. The diagnostic also records `h2 > h1` and `h3 > h2` descriptively; higher highs do not define a rule.

The 15-minute close location is `(c3 - min(l1,l2,l3)) / (max(h1,h2,h3) - min(l1,l2,l3))`. The frozen buckets are `LOW_QUARTER` `[0,0.25)`, `LOW_MID` `[0.25,0.50)`, `HIGH_MID` `[0.50,0.75)`, and `HIGH_QUARTER` `[0.75,1.00]`; zero range is explicitly `ZERO_RANGE`. BAR1 close location uses the same buckets and is descriptive only.

The non-overlapping primary hierarchy is:

1. `PERSISTENT_STRENGTH_15`: `c1`, `c2`, and `c3` all at/above open.
2. `RECOVERY_STRENGTH_15`: at least one of `c1`/`c2` below open and `c3` at/above open.
3. `PERSISTENT_WEAKNESS_15`: all three closes below open.
4. `MIXED_EARLY_PATH`: all other close sequences.

First-15-minute stop and target touches are reported but do not remove a record from its state. Full-path controls retain the frozen open reference, stop, target, MFE, MAE, and first-touch result. Post-15 metrics begin at the first eligible 5-minute bar with bar start at or after 09:30 and use `INTRADAY_FIRST_TOUCH_ENGINE_V1`. Same-bar ambiguity is preserved and never resolved favorably. Post-15 MFE/MAE retain the frozen T+1-open risk denominator; no delayed entry price is assigned.

The preregistered favorable path is `TARGET_FIRST` or control MFE at least 1.5R. Failure is control `STOP_FIRST`. State separation is descriptive enrichment against the source-population failure rate 23.1608% and favorable rate 11.4441%; no optimization score is used.

## Registered experiments

Exactly ten IDs are isolated in the Command 03 registry:

1. `EXP-EARLYPATH-001` — `BASELINE_EARLY_PATH_PROFILE`
2. `EXP-EARLYPATH-002` — `FIRST_5M_STATE`
3. `EXP-EARLYPATH-003` — `FIVE_TO_TEN_MIN_RECOVERY`
4. `EXP-EARLYPATH-004` — `TEN_TO_FIFTEEN_MIN_RECOVERY`
5. `EXP-EARLYPATH-005` — `OPEN_RECLAIM_STATE`
6. `EXP-EARLYPATH-006` — `HIGHER_LOW_STRUCTURE`
7. `EXP-EARLYPATH-007` — `EARLY_CLOSE_LOCATION`
8. `EXP-EARLYPATH-008` — `PERSISTENT_STRENGTH_VS_RECOVERY`
9. `EXP-EARLYPATH-009` — `PERSISTENT_WEAKNESS`
10. `EXP-EARLYPATH-010` — `EARLY_PATH_CONTEXT_INTERACTIONS`

Every preregistration freezes its metrics, baseline dependencies, exact state definitions and buckets, parameter hash, promotion prohibition, and validation prohibition. Command 01 and Command 02 records and hashes are guarded and were not modified.

## DEVELOPMENT findings

First-five-minute counts were 473 strong, 620 weak, and 8 flat. Strong versus weak showed lower control stop-first (19.45% versus 25.97%) and higher favorable-path rate (16.70% versus 7.58%). The flat cell is `VERY_SMALL`.

Within first-five weakness, counts for recovered, partial, and persistent-to-10 were 98, 200, and 322. Their failure rates were 21.43%, 25.50%, and 27.64%; favorable rates were 14.29%, 8.00%, and 5.28%. Thus persistent-to-10 minus recovered failure was +6.21 percentage points, while recovered minus persistent favorable was +9.01 points. This is descriptive separation, not evidence that the old `c2 >= open` rule improves an entry.

For paths below open at 10 minutes, counts for recovered, partial, and persistent-to-15 were 54, 211, and 348. Failure/favorable rates were respectively 29.63%/14.81%, 25.12%/5.69%, and 26.44%/6.32%. The small recovered-by-15 cell did not show lower failure.

Open-reclaim counts and control failure/favorable rates were:

| State | Count | Failure | Favorable |
| --- | ---: | ---: | ---: |
| Never below | 337 | 17.80% | 19.58% |
| Dip/reclaim by 10 | 98 | 21.43% | 14.29% |
| Dip/reclaim by 15 | 28 | 28.57% | 10.71% |
| Below at 15 | 612 | 25.82% | 6.21% |
| Mixed residual | 26 | 30.77% | 19.23% |

The `DIP_AND_RECLAIM_BY_15` and residual cells are `VERY_SMALL`. Never-below strength had the cleanest aggregate profile; slower reclaim did not monotonically improve failure.

Higher-low counts were 418 two-step, 505 one-step, and 178 no-higher-low. Two-step versus no-higher-low improved failure by 5.75 points (20.10% versus 25.84%) and favorable rate by 7.21 points (15.07% versus 7.87%), yielding `PROMISING_FOR_CONTROLLED_TEST` diagnostically. This does not select a higher-low rule.

Close-location counts and control failure/favorable rates were:

| Bucket | Count | Failure | Favorable |
| --- | ---: | ---: | ---: |
| Low quarter | 329 | 26.14% | 6.08% |
| Low mid | 261 | 26.05% | 10.73% |
| High mid | 281 | 21.00% | 12.46% |
| High quarter | 230 | 18.26% | 18.70% |
| Zero range | 0 | — | — |

High-quarter versus low-quarter improved failure by 7.88 points and favorable rate by 12.62 points, so close location is also `PROMISING_FOR_CONTROLLED_TEST` diagnostically. No quartile cutoff is promoted.

Primary-state path metrics were:

| State | Count | Control failure | Favorable | Median post15 MFE | Median post15 MAE | Post15 stop | Post15 target | Median extension | Median hypothetical R:R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Persistent strength | 337 | 17.80% | 19.58% | 0.616R | 0.345R | 17.51% | 7.12% | +0.698% | 1.773 |
| Recovery strength | 124 | 26.61% | 16.13% | 0.620R | 0.478R | 26.61% | 8.87% | +0.266% | 1.938 |
| Persistent weakness | 494 | 26.72% | 6.07% | 0.256R | 0.594R | 26.52% | 1.82% | -0.818% | 2.564 |
| Mixed path | 146 | 20.55% | 6.85% | 0.381R | 0.500R | 20.55% | 3.42% | -0.278% | 2.189 |

Recovery strength versus persistent weakness improved failure by only 0.11 points but improved favorable rate by 10.06 points. Persistent strength had much lower failure than recovery with a higher favorable rate; recovery therefore did not behave like uninterrupted strength. Hypothetical 15-minute R:R is descriptive only and is not an entry treatment.

## Temporal, context, and subset findings

The primary-state distributions for persistent strength / recovery / persistent weakness / mixed were 111/34/164/55 in 2022, 134/56/180/48 in 2023, and 92/34/150/43 in 2024. Recovery versus persistent-weakness failure was not stable: 29.41% versus 33.54% in 2022, 28.57% versus 26.11% in 2023, and 20.59% versus 20.00% in 2024. Recovery favorable rates were 5.88%, 19.64%, and 20.59%, versus weakness at 6.10%, 5.56%, and 6.67%. The mechanical classification is `UNSTABLE`.

Score offered no partition because all frozen records were in the preregistered 80–85 bucket. Setup, candidate stage, regime, frozen R:R, and gap interactions were descriptive only. Many recovery cells were small; candidate `CONFIRMED_ONLY`, neutral-regime, material-gap-up, and several gap-by-state cells were very small. Persistent strength generally retained higher favorable rates and persistent weakness generally retained lower favorable rates, but the context tables do not authorize subgroup selection. VWAP is reported as metadata only; opening range does not define any state.

Source versus admitted counts for persistent strength, recovery, persistent weakness, and mixed were 337/80, 124/33, 494/113, and 146/27. Source versus admitted failure rates were 17.80%/13.75%, 26.61%/27.27%, 26.72%/24.78%, and 20.55%/22.22%; favorable rates were 19.58%/18.75%, 16.13%/15.15%, 6.07%/6.19%, and 6.85%/7.41%. These are modest subset differences, not a reranking.

The known unexplained daily mismatch `SCHAEFFLER|2023-09-01` did not enter this population. The deterministic omit-one sensitivity therefore produced no affected IDs and identical recovery-value metrics with and without the observation. No definition or classification was tuned around it.

## Classification and sample limits

Sample warnings are `<30 VERY_SMALL`, `30–99 SMALL`, `100–299 LIMITED`, and `>=300 ADEQUATE_FOR_DESCRIPTION`. These labels do not imply inferential significance.

- `PERSISTENT_WEAKNESS_RESULT = NO_CLEAR_ASSOCIATION`: failure enrichment was only +3.56 points, below the preregistered promising threshold, despite a -5.37-point favorable enrichment.
- `RECOVERY_STATE_RESULT = NO_CLEAR_ASSOCIATION`: the +10.06-point favorable improvement over persistent weakness was paired with only a 0.11-point failure improvement and unstable year behavior.
- `HIGHER_LOW_RESULT = PROMISING_FOR_CONTROLLED_TEST`: aggregate count and dual-direction separation passed its descriptive classification.
- `EARLY_CLOSE_LOCATION_RESULT = PROMISING_FOR_CONTROLLED_TEST`: aggregate dual-direction separation passed its descriptive classification.
- `EARLY_PATH_TEMPORAL_CONSISTENCY = UNSTABLE` for the central recovery-versus-persistent-weakness comparison.
- `EARLY_PATH_RECOVERY_DIAGNOSTIC_RESULT = WEAKLY_SUPPORTED`.
- `EARLY_PATH_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING = NO`.

The later-testing gate requires one promising concept with an adequate candidate-state count, supportive direction in more than one year, subgroup breadth, no VWAP/opening-range dependency, no threshold optimization, and no equivalence to the failed 10-minute rule. Two-step higher-low had count 418 and two supportive years but failed subgroup breadth in the available context. High-quarter close location had three supportive years and subgroup breadth but count 230, below `ADEQUATE_FOR_DESCRIPTION`. Consequently, no concept passes the full gate, and there is no authorized next rule.

## Pilot and operational safeguards

Fourteen requested empirical pilot categories were available and passed deterministic checks for open, OHLC bars, state assignment, reclaim timing, higher-low state, close location, control/post-15 path, MFE/MAE, year, and sample bucket. The pilot uses real cases including BALRAMCHIN 2022-01-03, ABCAPITAL 2022-01-03, NTPC 2022-01-04, ICICIGI 2022-07-07, EICHERMOT 2022-01-03, CHOLAFIN 2022-01-12, COALINDIA 2022-07-26, ONGC 2022-01-12, BSOFT 2022-01-03, and INDIACEM 2022-01-03.

Outputs are ignored by Git. `backend/.env` remains ignored; no secrets or provider headers are logged. The diagnostic contains no order API, emits zero live signals and zero live orders, makes zero broker order calls, performs zero remote migrations, and writes nothing to Supabase.

## Artifacts and review boundary

The immutable artifacts and isolated registry are under `data/research/diagnostics/intraday/v1/early_path_command_03/`. The twelve machine reports are `data/reports/early_path_recovery_v1_summary.json` plus the population, first5, recovery10, recovery15, reclaim, higher-low, close-location, states, contexts, yearly, and pilot CSVs with the same `early_path_recovery_v1_` prefix.

The only appropriate next action is review. A later controlled test would require a new command and new preregistration after an explicit human decision; this diagnostic itself authorizes none. Validation remains sealed, and work stops at Step 02.15 / Command 03.
