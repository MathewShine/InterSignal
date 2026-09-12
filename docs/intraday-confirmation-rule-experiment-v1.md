# Intraday Confirmation Rule Experiment V1

## Research identity and scope

`INTRADAY_CONFIRMATION_RULE_EXPERIMENT_V1` is the first true controlled intraday rule experiment in InterSignal. Its sole record is `EXP-INTRARULE-001`, its profile is `TEN_MINUTE_OPEN_CONFIRMATION_V1`, and its type is `DEVELOPMENT_ONLY_CONTROLLED_RULE_EXPERIMENT`.

The experiment is confined to decisions from 2022-01-01 through 2024-12-31. Validation remains `SEALED`, the validation run count remains zero, and no holdout result was accessed. The experiment is research only: it does not promote a rule, modify Strategy V1, create Strategy V2, rerun the portfolio, generate live signals, or place orders.

## Why the rule uses 10 minutes

Ten minutes was chosen before outcome evaluation as the architecture-led midpoint of the original intended 5-to-15-minute confirmation window. It was not selected as a historical winner. This command did not run separate 5-minute or 15-minute treatment experiments and makes no claim that 10 minutes is best.

## Preregistered rule and one changed dimension

For each frozen long opportunity, the treatment waits for the first completed 10-minute bar on T+1:

```text
CONFIRMED if first_10m_close >= T+1_session_open
REJECTED  if first_10m_close <  T+1_session_open
```

The comparison uses canonical `Decimal` price precision with no tolerance or percentage buffer. Equality is confirmed. A confirmed treatment uses the first completed 10-minute close as its hypothetical entry reference.

The one changed dimension is entry confirmation timing and the associated sign filter. The control is `FROZEN_NEXT_OPEN_BASELINE`; the treatment is `TEN_MINUTE_OPEN_CONFIRMATION_V1`. Frozen stop, target, holding horizon, risk structure, ranking, admission status, and Strategy V1 position policy are unchanged. Treatment R:R is reported descriptively and is not filtered again at 1.5R.

No VWAP, opening-range, gap, score, regime, ranking, stop, target, holding-horizon, R:R-threshold, capital, capacity, or slot-replacement rule is part of the treatment. The descriptive context report is limited to dimensions already present in Command 01 and cannot select subgroup rules.

## Frozen population and dependencies

The primary population contains all 1,101 strict-covered DEVELOPMENT opportunities from Command 01. It is restricted to the selected 100-symbol scope, `USABLE_STRICT` intraday coverage, corporate-action-safe rows, an available first 10-minute bar, and available frozen stop, target, and risk structure. The secondary population is the unchanged set of 253 frozen Strategy V1 admissions. Admissions were not rerun, and the two populations are reported separately.

The immutable population manifest records opportunity ID, symbol, decision and entry dates, score, setup quality, candidate stage, regime state, T+1 open, first 10-minute close, stop, target, frozen R:R, intraday quality, corporate-action safety, and frozen admission flag. It also records the causal timestamp and adjusted-price-basis alignment audit fields.

The run guards the frozen feature, candidate, setup, regime, entry, Risk V1, Risk V1.1, Score V1, Outcome V1, Backtest V1, 49-record diagnostic registry, cost-model, temporal-harness, intraday-architecture, provider-pilot, Command 05/05A/05B, and Command 01 dependencies. Command 01 remains at 1,101 covered source opportunities, 253 admitted opportunities, 10 diagnostic experiment IDs, population hash `2308db408804b4b85addf34260e2072194c52c64fb878f79b0921054e074965c`, and preregistration hash `7aea55e3e3628031ba1a05980bbef2bb86052a1264642e5e70405041e64ba89e`.

## Price and path semantics

The experiment uses real normalized Groww 5-minute bars and the frozen Command 05B derived 10-minute bars. Raw prices remain unchanged at rest. Each opportunity is causally rebased in memory using the ratio between the frozen adjusted T+1 open and the raw first 5-minute open, preserving the Command 01 daily/intraday price-basis alignment.

Before treatment entry, the causal source bars ending at or before the 10-minute completion timestamp are checked against the frozen stop and target:

- A stop touch is `PRE_CONFIRMATION_STOP_INVALIDATED`.
- A target touch is `PRE_CONFIRMATION_TARGET_REACHED`.
- An unknowable stop/target ordering is `PRE_CONFIRMATION_AMBIGUOUS`.
- A confirmation close outside the frozen stop/target structure is `TREATMENT_STRUCTURE_INVALID`.

These states are separate from a normal rejection caused by a close below the open. Treatment eligibility requires usable data, no prior stop or target touch, no ambiguity, and a confirmation price strictly between the frozen stop and target.

For confirmed rows, treatment risk is confirmation price minus frozen stop; reward is frozen target minus confirmation price. Post-entry path evaluation begins with the next eligible 5-minute bar strictly after the completed 10-minute interval. No high or low from the confirmation interval can trigger a post-entry result. `INTRADAY_FIRST_TOUCH_ENGINE_V1` reports `STOP_FIRST`, `TARGET_FIRST`, `AMBIGUOUS`, or `NEITHER`. A neither result retains the frozen final holding-session close reference; there is no new exit rule or exit optimization.

## Preregistered metrics and falsification

The primary metrics were frozen before matched-path outcomes were computed: treatment stop-first and target-first rates, treatment MFE_R and MAE_R, confirmed retention, control-failure rejection, good-opportunity rejection, and treatment R:R delta versus control.

A favorable control opportunity was defined before evaluation as `TARGET_FIRST` or control MFE of at least 1.5R. The central filtering measures are:

```text
CONTROL_FAILURE_REJECTION_RATE = rejected control STOP_FIRST / all control STOP_FIRST
GOOD_OPPORTUNITY_REJECTION_RATE = rejected favorable control / all favorable control
FILTER_SEPARATION = CONTROL_FAILURE_REJECTION_RATE - GOOD_OPPORTUNITY_REJECTION_RATE
```

The five preregistered falsification criteria fail when:

1. Good-opportunity rejection is at least failure rejection.
2. Matched treatment stop-first is not lower than matched control stop-first.
3. Treatment MAE does not improve while treatment MFE deteriorates by at least 0.10R.
4. At least two of three DEVELOPMENT years do not show both positive filter separation and a lower treatment stop-first rate.
5. Median delay exceeds 1%, median R:R delta is below -0.50, or pre-confirmation/structure invalidation exceeds 10%.

No metric, criterion, window, or threshold was changed after result computation. A revised rule would require `EXP-INTRARULE-002` or later.

## DEVELOPMENT results

The source population is the primary conclusion because portfolio ranking and slot effects can distort the admitted subset.

| Measure | Source opportunities | Frozen admitted subset |
|---|---:|---:|
| Population | 1,101 | 253 |
| Confirmed | 487 | 108 |
| Rejected | 608 | 143 |
| Stop-invalidated before confirmation | 6 | 2 |
| Confirmed retention | 44.2325% | 42.6877% |
| Normal rejection | 55.2225% | 56.5217% |
| Failure rejection | 61.1765% | 64.8148% |
| Good-opportunity rejection | 31.7460% | 37.9310% |
| Filter separation | +29.4304 pp | +26.8838 pp |
| Median control MFE_R | 0.5795 | 0.5940 |
| Median treatment MFE_R | 0.3876 | 0.3756 |
| Median MFE delta | -0.1919R | -0.2183R |
| Median control MAE_R | 0.3972 | 0.3610 |
| Median treatment MAE_R | 0.4611 | 0.3646 |
| Median MAE delta | +0.0639R | +0.0036R |
| Median control R:R | 2.0499 | 2.1030 |
| Median treatment R:R | 1.7998 | 1.9067 |
| Median R:R delta | -0.2956 | -0.2864 |

Among 487 confirmed source rows, the control and treatment both contain 93 stop-first paths (19.0965%). Control contains 33 target-first paths (6.7762%) and treatment contains 34 (6.9815%). Control/treatment ambiguous counts are both zero; neither counts are 361 and 360 respectively. The matched stop-first direction therefore does not improve.

The source rejection cohort contains 156 control stop-first, 15 control target-first, and 437 control neither paths; 40 rejected rows meet the preregistered favorable-control definition. This shows meaningful false-start filtering, but also nontrivial good-opportunity sacrifice.

Confirmed source entries have mean drift 0.7664%, median drift 0.5295%, p25 0.2330%, p75 1.0208%, and p90 1.7196%. The rates above 1% and 2% are 25.6674% and 6.5708%. The cheaper-than-open rate is 0%, as expected from the exact long confirmation rule.

Treatment R:R is below 1.5 for 24.6407% of confirmed source rows, at least 2 for 35.1129%, and at least 2.5 for 23.2033%. These are observations, not an additional admission threshold.

## DEVELOPMENT-year stability

| Year | Confirmed / source | Failure rejection | Good rejection | Separation | Control stop-first | Treatment stop-first | Median R:R delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 164 / 364 | 64.2857% | 36.3636% | +27.9221 pp | 20.1220% | 20.1220% | -0.2911 |
| 2023 | 188 / 418 | 64.8352% | 30.0000% | +34.8352 pp | 16.4894% | 16.4894% | -0.3247 |
| 2024 | 135 / 319 | 51.5152% | 30.2326% | +21.2826 pp | 21.4815% | 21.4815% | -0.2620 |

Filter separation is positive in all three DEVELOPMENT years, but treatment stop-first is equal to control rather than lower in all three. Under the preregistered joint direction test, `TEMPORAL_RULE_CONSISTENCY` is therefore `UNSTABLE`.

## Cost metadata

The experiment calculates trade-level reference costs only for hypothetical confirmed entries using `INDIA_EQUITY_COST_MODEL_V1`, `COST-SCENARIO-002`, and the frozen baseline assumption of 5 bps slippage per side. Quantity is the frozen Strategy V1 hypothetical quantity. Each row reports estimated round-trip cost, cost_R, gross R, and gross-to-cost headroom for control and treatment.

Median source control cost_R is 0.0810 and median treatment cost_R is 0.0711; the median treatment-minus-control cost_R delta is -0.0070R. Mean cost_R values are 0.0901 and 0.0776. These figures are metadata only. No cash, capacity, slot-replacement, alternative-admission, or equity-curve model was run.

## Pilot validation

The pilot contains 14 predeclared real-case categories. Thirteen categories were available and passed all causal field checks. They cover close above open, close below open, exact equality, stop before confirmation, improved/degraded descriptive R:R, rejected control stop-first, rejected favorable control, confirmed control stop-first, confirmed control target-first, and examples from 2022, 2023, and 2024. No real target-before-confirmation example exists in this frozen population, so that category is explicitly `NOT_AVAILABLE`; no empirical case was fabricated.

Each available pilot row verifies T+1 open, first 10-minute close, status, pre-confirmation touch state, entry reference, frozen stop and target, treatment R:R, post-confirmation first touch, control and treatment outcomes, MFE/MAE, cost metadata when confirmed, and year assignment.

## Result and governance decision

Criteria A and E pass. Criteria B, C, and D fail. The mechanical DEVELOPMENT result is:

```text
TEN_MINUTE_CONFIRMATION_RULE_RESULT = MIXED
TEN_MINUTE_CONFIRMATION_HYPOTHESIS = WEAKENS
ELIGIBLE_FOR_VALIDATION_CONSIDERATION = NO
```

The rule rejects control failures more often than favorable controls and delay/R:R harm remains within the preregistered limits. However, treatment stop-first does not improve, median MFE deteriorates materially while median MAE worsens, and the joint yearly path criterion is unstable. The evidence therefore does not pass the next-stage gate. It is not promoted, no winner is selected, and validation remains unauthorized and sealed.

## Artifacts, reports, and reproducibility

The immutable experiment directory is `data/research/experiments/intraday/v1/ten_min_confirmation_rule/`. It contains the population manifest, preregistered one-record registry, completed one-record registry, experiment-freeze artifact, result, and run manifest. The separate registry leaves the prior 49 strategy diagnostics and 10 Command 01 intraday diagnostics unchanged.

Eleven machine reports are written under `data/reports/`: summary, population, matched, confirmed, rejected, outcomes, yearly, R:R, costs, contexts, and pilot. These paths and the experiment directory are git-ignored. The command performs no network request, database migration, Supabase persistence, or broker operation.

Run the experiment from the repository root with:

```powershell
& .\backend\.venv\Scripts\python.exe backend\scripts\run_intraday_confirmation_rule_experiment.py --tests-passed --frontend-build-passed
```

## Known limitations

- The evidence is limited to the frozen 100-symbol DEVELOPMENT scope and cannot establish holdout performance.
- Control MFE/MAE use frozen open risk while treatment MFE/MAE use confirmation-price risk, so their R denominators differ.
- Groww data is causally adjusted in memory to match the frozen daily price basis; raw data remains unchanged.
- Same-bar ordering uncertainty is preserved, and confirmation references are hypothetical rather than executable fills.
- Cost estimates reuse frozen quantity and a research slippage assumption; they are not a treatment equity curve.

The recommended next action is review only. Do not authorize validation or begin another command from this result.
