# Temporal Development/Validation Protocol V1

## Status and scope

`TEMPORAL_RESEARCH_HARNESS_V1` implements `TEMPORAL_VALIDATION_PROTOCOL_V1` for the `SWING_TEMPORAL_VALIDATION_V1` research profile. It is governance infrastructure around the frozen Strategy V1 chain. It does not create Strategy V2, change a strategy rule, run an optimization, or authorize real validation evaluation.

The split was declared on a calendar basis before future Strategy V2 experiments. It was not selected because one window performed better than another.

## Frozen windows

| Window | Inclusive start | Inclusive end | Purpose |
|---|---:|---:|---|
| `DEVELOPMENT_WINDOW_V1` | 2022-01-01 | 2024-12-31 | Hypothesis formation, parameter definition, and development-only evaluation |
| `VALIDATION_WINDOW_V1` | 2025-01-01 | 2026-08-13 | Formal one-shot holdout after explicit authorization |

The validation terminal date is the maximum `decision_date` in the frozen, forward-safe `PORTFOLIO_BACKTEST_V1` source-opportunity pool. It is a source-controlled constant. Appending later market data does not extend V1; an extension requires `VALIDATION_WINDOW_V2`.

## Partition and boundary semantics

`decision_date` determines cohort membership because it is the date on which the strategy information exists. Entry date and exit date never reassign an observation.

A development decision whose entry or four-session observation crosses 2025 remains DEVELOPMENT and is flagged `CROSSES_VALIDATION_BOUNDARY`. Such observations disclose that later prices are present and must not be silently used for parameter selection. The frozen eligible baseline source pool contains no such row, but nine broader outcome rows cross the boundary; all nine belong to the exceptional-review research cohort, not the eligible baseline pool.

## Validation status and contamination caveat

The initial state is `SEALED`. While sealed, validation outcome/performance access raises `ValidationAccessError`. Structural row counts, dates, identities, source-input distributions, missingness, and row fingerprints may be inspected; validation return, CAGR, drawdown, P&L, realized R, MFE/MAE, and exit attribution may not be emitted.

`validation_pristine_status` is `FORMAL_HOLDOUT_AFTER_DIAGNOSTIC_PHASE`. It is not `PRISTINE_UNSEEN_DATA`. Earlier baseline, outcome, ranking, holding, gap, exit, entry-quality, score, regime, cost, and synthesis work touched 2025–2026 information. The contamination register preserves that fact. No prior diagnostic changed frozen Strategy V1 parameters, but human knowledge of aggregate and cohort results exists.

## Development freeze and authorization

Before validation, one future experiment version must freeze, using DEVELOPMENT only:

- its hypothesis and single changed dimension;
- parameters and all rule definitions;
- ranking, score, reward:risk, entry, and exit changes if applicable;
- primary and secondary metric definitions;
- falsification, promotion, and minimum-sample criteria;
- baseline dependencies, development result, and required cost model.

Canonical sorted JSON produces a `parameter_hash`; the complete freeze payload produces `development_freeze_hash`. The freeze cannot self-authorize validation.

`authorize_validation(experiment_id, development_freeze_hash, explicit_user_authorization)` conceptually verifies the frozen artifact, parameter hash, completed development result, unused validation state, and an auditable explicit authorization. This command tested that contract only with a synthetic fixture. It did not authorize a real experiment.

One frozen experiment version may run validation once. A successful result changes the state to `EVALUATED` and fixes an immutable result hash. A reproducibility rerun is marked `REPRODUCTION_RUN` and must use the identical development freeze and immutable result hash. A parameter revision requires a new experiment ID/version; the old validation result remains recorded.

## Evaluation modes

`CONTINUOUS_CONTEXT_ANALYSIS` is a descriptive slice of the frozen full-history run. Portfolio equity is path-dependent, so this is not an independent validation backtest.

`INDEPENDENT_WINDOW_BACKTEST` starts each window with ₹100,000 and processes only opportunities assigned by decision date. It reuses the frozen `PORTFOLIO_BACKTEST_V1` mechanics: score/ranking order, four-position cap, 1% per-trade risk, 4% portfolio risk cap, one open position per symbol, frozen stop/target/time exits, conservative ambiguity policy, and no leverage. Future validation should use this mode.

The development baseline run in Command 02 is `BASELINE_REFERENCE_ONLY`; it establishes harness mechanics and is not tuning. Holdout performance was not run.

## Cost-aware validation and promotion governance

Any future validation must report both gross and cost-adjusted results using the frozen `INDIA_EQUITY_COST_MODEL_V1` / `NSE_CASH_DELIVERY_RESEARCH_V1` assumptions. A nonzero cost/slippage scenario is mandatory; a zero-cost result alone is insufficient.

Promotion requires a development freeze, explicit one-shot validation authorization, cost-aware evaluation, adequate sample review, no severe temporal failure, no baseline mutation, and explicit human review. Development performance alone cannot promote a candidate.

## Input distribution shift

The consistency report compares opportunity counts, frozen score, candidate category, setup quality, regime state, effective reward:risk, decision-date price, and 20-day median traded value. Price and liquidity come from causal candidate inputs keyed by decision date, symbol, and ISIN. Standardized differences and category percentage-point differences are descriptive; no outcome values, machine learning, fitted bins, or PSI are used.

## Walk-forward design only

Possible later expanding-window checks are: develop through 2022/validate 2023, develop through 2023/validate 2024, and develop through 2024/validate 2025. These are retrospective robustness folds because earlier diagnostics already exposed their periods. No walk-forward results were generated in Command 02.

## Safety

`LIVE_TRADING_READY` and `SMALL_CAPITAL_LIVE_READY` remain false. The harness performs no live signaling, order placement, remote migration, or Supabase persistence. `READY_FOR_FURTHER_RESEARCH` and `READY_FOR_PAPER_RESEARCH_ONLY` remain true.

