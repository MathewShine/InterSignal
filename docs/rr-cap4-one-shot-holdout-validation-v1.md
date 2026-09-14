# R:R CAP4 One-Shot Holdout Validation V1

## Immutable status

`RR_CAP4_HOLDOUT_VALIDATION_V1` is validation record `VAL-RRCAL-001` for frozen experiment `EXP-RRCAL-001`. The explicitly authorized one-shot evaluation completed with state `EVALUATED`, validation run count 1, and immutable validation result hash `828b81cf3cd0d73873878a1027b68f788198a26d5172c488caf9f49662c9f124`.

The formal decision is:

- `RR_CAP4_HOLDOUT_VALIDATION_RESULT = FAILED`
- `RR_CAP4_GENERALIZATION_RESULT = DOES_NOT_GENERALIZE`
- `RR_CAP4_SCORE_CHANGE_READINESS = REJECTED`
- `PROMOTED_TO_STRATEGY_V1 = false`

The failure is binding for this frozen hypothesis. No parameter was changed after validation, no retuning or alternate mapping was tested, and no second validation attempt is permitted.

## Explicit authorization and one-shot governance

The user explicitly authorized Step 02.16 / Command 02. The auditable authorization reference is `USER_AUTHORIZATION_STEP_02_16_COMMAND_02_ATTACHMENT_A2B7F0B0_2026_09_12`, with authorization token `81c1e146ebf9777632cd5abc9dad6797ea4acd30ce043fc2ecd32d361699b698`.

Before outcome access, 103 experiment-specific tests passed. The frozen hashes, treatment, threshold, portfolio mechanics, cost model, state, run count, and exact terminal date were verified. The authorization was persisted, the state transitioned `SEALED → AUTHORIZED_TO_EVALUATE`, and `validation_started_at = 2026-09-12T17:22:29.65288Z` was durably recorded with run count 1 before holdout performance fields were loaded. Evaluation completed at `2026-09-12T17:22:35.368045Z`, transitioning to `EVALUATED`. An attempted second `VALIDATION_RUN` was rejected by the guard.

The validation is now consumed. Any future reproduction may only be labeled `REPRODUCTION_RUN` and must use the exact development freeze hash, parameters, and immutable validation result hash. It cannot be used to retune `EXP-RRCAL-001`.

## Frozen experiment identity

The pre-access checks recomputed and matched:

- Development population hash: `6a6b12b608812318f81331e3e2ad66fe5fe1fffc091bf86d1018623396dca523`
- Parameter hash: `ce07c6defad1b5f43902057d2f9be9350ab44d3c8bb6b72b17cd222a0b04586c`
- Preregistration hash: `22d79a991043d5b83f616d15c1a8ac5b14472abb03d4c3ee7db92c2238ab3c7e`
- Development freeze hash: `d31d4dc891258535a7a16c4edc0a530191af64faa6ba4931eb84d9dadc57c4d2`

The control remained `RR_SCORE_MAPPING_V1`: `<1.5 → 0`, `1.5–<2 → 3`, `2–<2.5 → 4`, and `>=2.5 → 5`. The sole treatment remained `RR_SCORE_MAPPING_CAP4_V1`: `<1.5 → 0`, `1.5–<2 → 3`, and `>=2 → 4`. Raw score threshold remained 80. Score weights, ranking and tie breaks, 1% trade risk, 4% open-risk cap, maximum four positions, no leverage, same-symbol restriction, frozen stops and targets, four-session hold, and ambiguity handling were unchanged.

No development artifact was overwritten. A separate validation linkage record associates the immutable validation result with the historical development freeze.

## Formal-holdout caveat and population

The partition contains decision dates from 2025-01-01 through the frozen terminal date 2026-08-13 only. It excludes DEVELOPMENT rows and does not silently extend the terminal date. The validation dates are not claimed to be historically unseen because earlier aggregate diagnostics touched the period. They are nevertheless the formal one-shot holdout for `EXP-RRCAL-001` because its parameters and decision rules were frozen using DEVELOPMENT only.

The validation source population has 1,224 opportunities and immutable population hash `c22241cc9cc80336bada2ab6b4818c5f8c462490d83944b4876133be8399d90a`. All 1,224 were control eligible; 1,065 remained treatment eligible, and 159 became `CONTROL_ONLY`. There were zero source-level `TREATMENT_ONLY` and zero `INELIGIBLE_BOTH` rows.

Seven hundred nineteen rows lost the fifth point. The changed-score counts were 196 for 85→84, 34 for 84→83, 136 for 83→82, 21 for 82→81, 173 for 81→80, and 159 for 80→79. Thus 12.9902% of control eligibility depended specifically on the fifth point at the raw-80 threshold. Continuous effective R:R and all non-R:R components remained unchanged.

## Holdout fifth-point discrimination

Both component cells are adequate for description:

| Metric | Control R:R4 | Control R:R5 |
| --- | ---: | ---: |
| Count | 466 | 719 |
| Median target distance | 10.4247% | 30.7474% |
| Median target R | 1.9575R | 5.5652R |
| Median MFE | 0.4400R | 0.4665R |
| Median MAE | 0.4448R | 0.5111R |
| Target-first rate | 3.4335% | 0.1391% |
| Stop-first rate | 21.8884% | 23.6439% |
| Median MFE / target-R | 0.2119 | 0.0767 |

R:R5 target distance was 2.9495 times the R:R4 median while median MFE improved only 0.0264R, below the frozen material threshold. R:R5 had worse median MAE, target-first rate lower by 3.2944 percentage points, and MFE/target ratio lower by 0.1353. The frozen base classifier was `MIXED` with zero materially positive, two negative, and two immaterial dimensions. Therefore `VALIDATION_FIFTH_RR_POINT_RESULT = CONFIRMS_NONPOSITIVE_VALUE`.

The removed 159-row cohort is `LIMITED`: median effective R:R 6.5840, median target distance 30.4572%, median MFE 0.6104R, median MAE 0.4938R, target-first 0%, stop-first 28.3019%, and neither 71.6981%. It contains 111 rows from 2025 and 48 from 2026.

The retained 1,065-row cohort is `ADEQUATE_FOR_DESCRIPTION`: median effective R:R 2.7266, median target distance 19.7761%, median MFE 0.4305R, median MAE 0.4689R, target-first 1.6901%, stop-first 21.7840%, and neither 76.4319%.

## Validation-year component evidence

| Period | Cell | Count | Median target distance | Median target R | Median MFE | Median MAE | Target first | Stop first | MFE/target |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2025 | R:R4 | 253 | 9.9240% | 1.9393R | 0.4525R | 0.4234R | 4.7431% | 19.7628% | 0.2250 |
| 2025 | R:R5 | 478 | 32.3191% | 5.7671R | 0.4451R | 0.4794R | 0.0000% | 21.3389% | 0.0744 |
| 2026 partial | R:R4 | 213 | 10.8500% | 2.0111R | 0.4032R | 0.5053R | 1.8779% | 24.4131% | 0.1949 |
| 2026 partial | R:R5 | 241 | 29.2614% | 5.2655R | 0.4920R | 0.5451R | 0.4149% | 28.2158% | 0.0852 |

All four direction dimensions supported CAP4 in 2025; three of four supported it in 2026 partial through 2026-08-13. `VALIDATION_TEMPORAL_CONSISTENCY = CONSISTENT`.

## Independent holdout portfolios

Both portfolios started independently at ₹100,000. Development ending equity was not carried forward.

| Metric | Control | CAP4 treatment |
| --- | ---: | ---: |
| Ending equity | ₹88,285.0823 | ₹86,123.0599 |
| Gross return | -11.7149% | -13.8769% |
| Maximum drawdown | 16.3433% | 16.2748% |
| Trades | 245 | 232 |
| Skips | 979 | 833 |
| Mean realized R | -0.0516R | -0.0743R |
| Median realized R | -0.0618R | -0.0684R |
| Positive rate | 44.8980% | 43.1034% |
| Target / stop / time exits | 5 / 52 / 188 | 5 / 50 / 177 |

Treatment ended ₹2,162.02 below control, breaching the preregistered ₹1,000 material-deterioration boundary even though its maximum drawdown was 0.0685 percentage points lower. This failure of gross criterion C is why the overall validation fails despite component evidence supporting the structural hypothesis. Ending equity is not used alone: the decision also incorporates the component, yearly, cost, and selection evidence.

## Trade-set changes

The portfolios share 181 trades. Control has 245 trades and treatment 232, with 64 control-only and 51 treatment-only replacement trades; Jaccard similarity is 0.6115. Twenty-nine control-only trades were direct source eligibility removals. Thirty-five additional control-only trades and all 51 replacements were endogenous chronological slot/ranking effects, yielding 86 portfolio replacement effects. No source-level treatment-only opportunity or unexplained trade-set state occurred, and every replacement was treatment eligible.

The 64 control-only trades contributed -₹1,919.44 gross, with mean/median realized R of -0.0381R/-0.0618R. Their exits were 1 target, 14 stop, and 49 time exits; median effective R:R was 5.6132 and median target distance was 29.4361%.

The 51 treatment replacements contributed -₹3,865.56 gross, with mean/median realized R of -0.1377R/-0.0833R. Their exits were 1 target, 12 stop, and 38 time exits, with 39 in 2025 and 12 in 2026. These are endogenous substitutions, not direct evidence about the score component.

## Frozen cost overlay

The unchanged `INDIA_EQUITY_COST_MODEL_V1`, `NSE_CASH_DELIVERY_RESEARCH_V1`, baseline nonzero-slippage scenario was applied as an `APPROXIMATE_RESEARCH_ESTIMATE`. It is not an executable cost-aware admission portfolio.

| Metric | Control | CAP4 treatment |
| --- | ---: | ---: |
| Modeled transaction costs | ₹18,598.54 | ₹16,960.27 |
| Approximate net ending equity | ₹69,686.5423 | ₹69,162.7899 |
| Approximate net return | -30.3135% | -30.8372% |
| Gross-positive to net-negative flips | 12 | 11 |
| Cash-feasibility violations | 33 | 29 |

`VALIDATION_COST_CONCLUSION = BOTH_WEAK`. Both approximate net results are poor. Treatment remains ₹523.75 below control after costs, which is within the frozen ₹1,000 material cost threshold; costs narrow rather than reverse the gross disadvantage. Cost criterion D therefore passes, but does not rescue the failed gross criterion.

## Development versus validation

Component evidence aligns strongly in direction: R:R5 again has much larger targets, lower target-first probability, higher stop-first probability, and lower MFE/target ratio. Both periods have consistent yearly component evidence. Trade-set similarity remains above the frozen 0.50 interpretability floor.

Portfolio direction does not align. CAP4 ended ₹2,936.81 above control in DEVELOPMENT but ₹2,162.02 below control in validation. Five of six frozen alignment checks pass; the gross portfolio direction check fails. `DEVELOPMENT_VALIDATION_ALIGNMENT = PARTIAL_ALIGNMENT`.

The pre-existing temporal harness classification is `TEMPORAL_DATA_SHIFT_RESULT = HIGH`. The failed portfolio generalization is reported in that context, but the shift does not excuse or override failure.

## Frozen success criteria and final decision

Criteria A, B, D, E, F, and G pass: R:R5 is not positively discriminative; its targets remain substantially larger without target-achievement improvement; the net disadvantage is below the material cost boundary with no reversal; both validation years support CAP4; selection remains interpretable; and all implementation/integrity checks pass.

Criterion C fails because CAP4 gross ending equity is ₹2,162.02 lower than control, beyond the frozen ₹1,000 threshold. The validation contract requires all major conditions. Consequently, the binding result is `FAILED`, `DOES_NOT_GENERALIZE`, and `REJECTED` for score-change readiness.

No 4.5-point treatment, new R:R boundary, threshold change, weight change, alternate mapping, or subgroup exception was evaluated. CAP4 was not promoted into Strategy V1. No Score V2 or Strategy V2 was created.

## Pilot, storage, and operational safeguards

All 14 requested real holdout pilot categories were available and passed: IPCALAB 2025-01-02, APTUS 2025-02-01, BALRAMCHIN 2025-03-18, LAURUSLABS 2025-02-05, APLAPOLLO 2026-01-01, PAYTM 2026-07-07, and AIAENG 2025-02-05 cover the mapping, transition, retained/removed, portfolio, replacement, yearly, target/stop, and cost cases.

Immutable validation artifacts are under `data/research/validation/experiments/rr_cap4_val_001/`. Fourteen reports under `data/reports/` use the `rr_cap4_validation_v1_` prefix. Generated outputs and `backend/.env` are ignored by Git. No broker secrets or provider headers were logged; no order endpoint, live signal, live order, broker call, remote migration, or Supabase persistence occurred.

The only recommended next action is human review of the failed immutable validation result. Do not rerun, retune, promote CAP4, create Score/Strategy V2, or begin another command automatically.
