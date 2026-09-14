# R:R Score Cap-4 Controlled Experiment V1

## Status and scope

`RR_SCORE_MAPPING_CONTROLLED_EXPERIMENT_V1` is the preregistered, DEVELOPMENT-only controlled score-component experiment `EXP-RRCAL-001` under profile `RR_CAP4_DEVELOPMENT_V1`. It changes exactly one dimension: an effective R:R of at least 2.5 receives 4 treatment points instead of 5 control points. It does not create Score V2 or Strategy V2, change Strategy V1, promote a production rule, or authorize validation.

The development window is 2022-01-01 through 2024-12-31, partitioned by `decision_date`. Validation remains `SEALED`, validation run count remains 0, and no validation or holdout result was accessed. The frozen checkpoint is `c6315abdd92db3b978ae28c5f5b08013ead4bbb3`.

## Architecture-led rationale and frozen treatment

R:R of at least 2 already satisfies the architecture's preferred reward/risk quality. This experiment asks whether increasing the score again merely because the structural target is more distant adds useful evidence about future opportunity quality. CAP4 was not chosen because it performed best in a retrospective search. No mapping search, threshold search, optimizer, machine learning, or alternative treatment was run.

The exact mappings are:

| Effective R:R | Control `RR_SCORE_MAPPING_V1` | Treatment `RR_SCORE_MAPPING_CAP4_V1` |
| --- | ---: | ---: |
| `<1.5` | 0 | 0 |
| `>=1.5` and `<2.0` | 3 | 3 |
| `>=2.0` and `<2.5` | 4 | 4 |
| `>=2.5` | 5 | 4 |

Treatment score is calculated only as `frozen control raw score - control R:R points + treatment R:R points`. Setup, momentum, RVOL, relative-strength, regime, sector, and catalyst values are not recomputed. Continuous effective R:R, the frozen stop, structural target, target distance, and effective R:R calculation are unchanged. The raw entry threshold remains 80 with no normalization. High-R:R opportunities are not rejected directly; they lose only the fifth score point.

All portfolio mechanics are also frozen: independent ₹100,000 starting capital, at most four concurrent long cash-equity positions, 1% trade risk, 4% aggregate admission risk, no leverage, one open position per symbol, the existing score-consuming ranking order, frozen stop and target, four-session hold, and conservative ambiguity handling. No intraday confirmation or early-path rule is combined with the experiment.

## Preregistration, population, and immutable hashes

The source is the frozen DEVELOPMENT score/risk/outcome population: every DEVELOPMENT row that reached frozen score evaluation with a valid risk structure and sufficient score coverage. Its immutable manifest includes identity, all component points, frozen control score/status/eligibility, continuous R:R and target-distance fields, frozen outcome linkage, and frozen portfolio-admission flag.

- Source rows: 2,068
- Population hash: `6a6b12b608812318f81331e3e2ad66fe5fe1fffc091bf86d1018623396dca523`
- Parameter hash: `ce07c6defad1b5f43902057d2f9be9350ab44d3c8bb6b72b17cd222a0b04586c`
- Preregistration hash: `22d79a991043d5b83f616d15c1a8ac5b14472abb03d4c3ee7db92c2238ab3c7e`
- Development freeze hash: `d31d4dc891258535a7a16c4edc0a530191af64faa6ba4931eb84d9dadc57c4d2`

The population manifest, one-record preregistration, mappings, decision rules, support/falsification rules, and development freeze were written before treatment outcome computation. Baseline dependencies through Step 02.15 / Command 03 were hashed before and after the run and remained unchanged.

## Mechanical source-level effect

All 2,068 source rows are control eligible. CAP4 leaves 1,986 treatment eligible and removes 82 `CONTROL_ONLY` rows. Source-level `TREATMENT_ONLY` and `INELIGIBLE_BOTH` counts are both zero. A total of 484 rows lose one point; 82 control score-80 rows become treatment score 79 and lose eligibility. The fifth point therefore supports 3.9652% of control-eligible rows specifically at the threshold.

The changed-score counts are 141 for 85→84, 18 for 84→83, 89 for 83→82, 10 for 82→81, 144 for 81→80, and 82 for 80→79. The full control/treatment raw-score distributions are:

| Score | Control | Treatment |
| ---: | ---: | ---: |
| 79 | 0 | 82 |
| 80 | 623 | 685 |
| 81 | 205 | 71 |
| 82 | 304 | 383 |
| 83 | 208 | 137 |
| 84 | 587 | 710 |
| 85 | 141 | 0 |

The `CONTROL_ONLY` cohort has 82 rows (`SMALL`): median effective R:R 4.9785, median target distance 23.8657%, median MFE 0.4511R, median MAE 0.6077R, target-first 1/82 (1.2195%), stop-first 29/82 (35.3659%), and neither 52/82. The retained `ELIGIBLE_BOTH` cohort has 1,986 rows. Relative to the full control-eligible source set, retained rows improve three of four preregistered path dimensions: median MAE, target-first rate, and stop-first rate; median MFE is slightly lower rather than improved.

## Fifth-point discrimination and target achievability

The control R:R-point-4 comparison cell has 1,541 rows and the R:R-point-5 cell has 484, so both are `ADEQUATE_FOR_DESCRIPTION`.

| Metric | R:R points 4 | R:R points 5 |
| --- | ---: | ---: |
| Median effective R:R | 2.0000 | 5.0049 |
| Median target distance | 10.5987% | 25.1049% |
| Median target distance R | 1.8934R | 4.7320R |
| Median MFE | 0.4129R | 0.4543R |
| Median MAE | 0.4868R | 0.5438R |
| Target first | 5.9053% | 0.8264% |
| Stop first | 20.8306% | 24.5868% |
| Median MFE / target-R | 0.2147 | 0.0830 |

R:R-point-5 rows have targets roughly 2.37 times farther away by the median percentage and 2.50 times farther in target-R terms. Their median MFE advantage is only +0.0414R, below the frozen +0.10R material threshold; median MAE is +0.0570R worse but below the frozen 0.10R threshold. Target-first rate is 5.0788 percentage points lower, and the median MFE/target ratio is 0.1317 lower. The point-5 cohort therefore differs principally through target distance without higher target achievement.

The preregistered mechanical classification is `FIFTH_RR_POINT_DISCRIMINATION_RESULT = MIXED`: zero dimensions materially favor the fifth point, two materially oppose it, and two are immaterial. `MIXED` here leans nonpositive under the frozen support rule; it is not a claim that every outcome metric is worse.

## Yearly component behavior

Each year compares the same frozen R:R-point-4 and point-5 cohorts:

| Year | Cell | Count | Median MFE | Median MAE | Target first | Stop first | Median MFE/target |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2022 | R:R4 | 490 | 0.4370R | 0.5583R | 6.1224% | 24.4898% | 0.2237 |
| 2022 | R:R5 | 83 | 0.3579R | 0.6109R | 0.0000% | 31.3253% | 0.0603 |
| 2023 | R:R4 | 518 | 0.4006R | 0.4473R | 6.5637% | 19.1120% | 0.2011 |
| 2023 | R:R5 | 237 | 0.5458R | 0.4794R | 0.4219% | 21.9409% | 0.0945 |
| 2024 | R:R4 | 533 | 0.4087R | 0.4568R | 5.0657% | 19.1370% | 0.2150 |
| 2024 | R:R5 | 164 | 0.4065R | 0.5899R | 1.8293% | 25.0000% | 0.0833 |

All three years are nonpositive for the fifth point in at least three of the four preregistered direction dimensions. The result is `RR_FIFTH_POINT_TEMPORAL_CONSISTENCY = CONSISTENT`. This is descriptive DEVELOPMENT evidence, not validation evidence.

## Independent gross portfolio comparison

The control reproduced the exact frozen independent DEVELOPMENT baseline ending equity of ₹98,326.608925713674 before the treatment portfolio was run.

| Metric | Control | CAP4 treatment |
| --- | ---: | ---: |
| Starting equity | ₹100,000 | ₹100,000 |
| Ending equity | ₹98,326.6089 | ₹101,263.4226 |
| Gross return | -1.6734% | +1.2634% |
| Maximum drawdown | 23.1408% | 24.6345% |
| Completed trades | 481 | 470 |
| Skips | 1,587 | 1,516 |
| Mean realized R | -0.0018R | +0.0105R |
| Median realized R | -0.0458R | -0.0337R |
| Positive rate | 47.4012% | 48.2979% |
| Target / stop / time exits | 23 / 106 / 352 | 22 / 99 / 349 |

Independent yearly ending equity for control/treatment was ₹83,891.02/₹84,020.58 in 2022, ₹122,865.61/₹118,463.83 in 2023, and ₹95,817.86/₹103,874.68 in 2024. Under the frozen material-deterioration rule, treatment was materially worse in 2023 only, not in at least two of three years. A higher aggregate treatment ending equity is supporting context, not a standalone winner test.

## Trade-set stability and substitutions

The trade sets contain 481 control trades and 470 treatment trades, with 442 in their intersection. There are 39 control-only trades and 28 treatment-only replacement trades; Jaccard similarity is 0.8684. Eighteen control-only trades are direct fifth-point eligibility removals. The other 21 control-only trades and all 28 replacements are chronological slot/ranking cascades, for 49 selection changes beyond direct removals. Every treatment-only portfolio trade remains source-level treatment eligible, and there are no unexplained trade-set states.

The 39 control trades absent from treatment contributed -₹6,631.21 gross with mean/median realized R of -0.2089R/-0.2560R. Their exits were 1 target, 11 stop, and 27 time exits; their yearly counts were 4/12/23 in 2022/2023/2024. Median effective R:R was 3.9266 and median target distance was 23.1482%. This group includes direct removals and indirect selection cascades and is descriptive only.

The 28 treatment-only trades are explicitly labeled endogenous deterministic substitutions created when changed eligibility and score ranking alter chronological portfolio slots. Their score, continuous R:R, frozen outcome, year, and source eligibility are reported individually; they are not direct component evidence.

## Frozen cost overlay

Both generated trade sets were overlaid with the unchanged `INDIA_EQUITY_COST_MODEL_V1`, `NSE_CASH_DELIVERY_RESEARCH_V1`, baseline-slippage scenario `COST-SCENARIO-002`. Control modeled transaction costs are ₹37,254.00 and approximate overlay ending equity is ₹61,072.6089 (-38.9274%). Treatment modeled costs are ₹35,515.52 and approximate overlay ending equity is ₹65,747.9026 (-34.2521%). The treatment's relative structural advantage is not reversed by the overlay.

These are frozen generated-trade-set overlays, not executable cost-aware portfolios. Admissions were not rerun with costs. The overlay reports 126 control and 120 treatment cash-feasibility violations, so its net equity figures must not be presented as realizable cost-aware portfolio results. Trade-cost and daily cash reconciliation checks themselves have zero violations.

## Frozen decision and falsification result

Before observing treatment results, the experiment froze five falsification criteria:

- A: fifth-point discrimination is clearly positive and at least two years oppose CAP4.
- B: rows are removed but the retained source population improves fewer than two path-quality dimensions.
- C: treatment deteriorates materially in at least two of three independent years.
- D: treatment creates source-level treatment-only rows, unexplained trade changes, or Jaccard similarity below 0.50.
- E: treatment is better gross but loses that relative advantage after the frozen cost overlay.

All five criteria pass without triggering. The fifth point is not clearly positively discriminative; target distance is substantially larger without better target achievement; retained rows improve three path dimensions; yearly evidence is consistent; only one independent year is materially worse; selection changes remain interpretable; and the cost overlay does not reverse the relative result.

The frozen decision outputs are:

- `RR_CAP4_EXPERIMENT_RESULT = SUPPORTED_FOR_NEXT_STAGE`
- `RR_FIFTH_POINT_HYPOTHESIS = SURVIVES_DEVELOPMENT_TEST`
- `ELIGIBLE_FOR_VALIDATION_CONSIDERATION = YES`

`YES` means only that the DEVELOPMENT evidence is eligible for human consideration. It does not authorize validation, unseal the holdout, promote CAP4, or create a new strategy or score version.

## Pilot, reports, and operational safeguards

All 14 requested pilot categories were available and passed. Real examples include ABCAPITAL 2022-10-27 for the unchanged 3-point bucket; ABCAPITAL 2022-01-03 for the unchanged 4-point bucket; HDFCAMC 2022-10-20 for 5→4; SPARC 2022-10-28 for 85→84; MCX 2022-10-27 for 80→79 and the removed source cohort; HINDPETRO 2022-12-12 for 84→83; TANLA 2023-04-17 for a large target; NAUKRI 2022-11-14 for high R:R with low MFE; BALRAMCHIN 2022-01-03 and DALBHARAT 2023-09-01 for R:R4/R:R5 target-first cases; JINDALSTEL 2022-10-27 for a control-only portfolio trade; and IEX 2022-11-25 for a treatment replacement.

Immutable artifacts and the isolated one-record registry are under `data/research/experiments/strategy/v1/rr_cap4_command_01/`. The 13 machine reports are under `data/reports/` with the `rr_cap4_v1_` prefix: summary, population, score transitions, R:R4-vs-R:R5, removed cohort, retained cohort, yearly component, control portfolio, treatment portfolio, trade-set comparison, replacement trades, costs, and pilot.

All generated outputs are ignored by Git. `backend/.env` remains ignored. The experiment performs no remote writes or migrations, uses no Supabase persistence, logs no broker secret or provider header, exposes no order endpoint, emits zero live signals, places zero live orders, and makes zero broker order calls.

The only recommended next action is human review of this DEVELOPMENT result. Do not access validation, promote CAP4, alter Strategy V1, or begin another command automatically.
