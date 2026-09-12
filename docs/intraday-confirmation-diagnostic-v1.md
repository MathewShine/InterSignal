# Intraday Confirmation Diagnostic V1

Status: DEVELOPMENT diagnostic complete; historical research only.

## Purpose and governance

`INTRADAY_CONFIRMATION_DIAGNOSTIC_V1` / `DEVELOPMENT_INTRADAY_CONFIRMATION_V1` asks whether waiting for the first completed 5-minute, derived 10-minute, or derived 15-minute bar after the T+1 open is associated with better subsequent path quality, or mainly changes price and frozen stop/target headroom. The confirmation close is a hypothetical reference, not an executed trade.

The analysis is restricted to 2022-01-01 through 2024-12-31. Validation is `SEALED`, its run count remains zero, and no validation rows or holdout performance are consumed. The command does not modify Strategy V1, create Strategy V2, rerun portfolio admissions or equity, model a costed portfolio, optimize a wait window or context threshold, choose a winner, or promote a rule.

All empirical rows come from the real Groww DEVELOPMENT dataset sealed by Command 05B. The primary population includes only corporate-action-safe opportunities with `USABLE_STRICT` data across the frozen four-session path and a valid frozen next-open/stop/target structure. The frozen 100-symbol dataset covers about 54% of all DEVELOPMENT opportunities, so findings are not whole-universe claims.

The sealed Groww bars remain raw and are never overwritten. Because frozen Strategy V1 open/stop/target values use the adjusted daily price basis, the diagnostic rebases each opportunity's intraday OHLC and VWAP in memory by `frozen T+1 open / raw Groww T+1 open`. That causal ratio is known at the session open, preserves every observed intraday return and path relationship, and prevents later corporate-action factors from becoming artificial price drift or false stop/target touches. The method is locked in the preregistration; it changes neither the source data nor the frozen risk structure.

## Frozen population and experiments

- Strict covered source opportunities: 1,101 of 2,068 DEVELOPMENT opportunities.
- Strict covered admitted trades: 253 of 478 DEVELOPMENT admissions.
- Population manifest hash: `2308db408804b4b85addf34260e2072194c52c64fb878f79b0921054e074965c`.
- Preregistration hash: `7aea55e3e3628031ba1a05980bbef2bb86052a1264642e5e70405041e64ba89e`.
- Registry: exactly `EXP-INTRACONF-001` through `EXP-INTRACONF-010`; every record has `promotion_allowed=false` and `eligible_for_promotion=false`.

The population was frozen before result computation. Price-drift, R:R, VWAP, opening-range, early-path, sample-safety, classification, and temporal-consistency definitions were then written to the preregistration artifact before the empirical diagnostic ran.

## Causal references and path semantics

The 5-minute reference is the close of the first completed canonical 5-minute bar. The 10-minute and 15-minute references are the closes of the first completed derived 10-minute and 15-minute bars. Each derived close and timestamp are checked against its first two or three canonical 5-minute source bars. At time X, only source bars whose `bar_end <= X` are consumed; partial derived bars fail.

Pre-confirmation stop and target touches include the completed confirmation bar because those highs/lows occurred before its close became observable. If stop and target touch in the same 5-minute bar, the row remains `INTRABAR_AMBIGUOUS`. A stop-first row is `STOP_INVALIDATED_BEFORE_CONFIRMATION`; a target-first row is `TARGET_REACHED_BEFORE_CONFIRMATION`. A close outside the frozen stop/target structure is `STRUCTURE_INVALID_AT_CONFIRMATION`.

For feasible rows, the post-confirmation path starts at the next eligible 5-minute bar. Highs and lows from earlier in the confirmation bar cannot become post-entry events. Path ordering uses `INTRADAY_FIRST_TOUCH_ENGINE_V1`, preserves same-bar ambiguity, and retains gap-through-stop and gap-through-target states. MFE and MAE in confirmation R units use `confirmation_price - frozen_stop`; they are not directly substituted for frozen portfolio R.

## Price drift and frozen R:R

| Window | Available | Feasible | Stop before | Target before | Median drift | >1% chase | Cheaper than open | Median confirmation R:R | Median R:R delta | Below 1.5 R:R | Median MFE R | Median MAE R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 5m | 1,101 | 1,096 | 5 | 0 | -0.1417% | 9.36% | 56.31% | 2.135 | +0.073 | 9.27% | 0.422 | 0.474 |
| 10m | 1,101 | 1,095 | 6 | 0 | -0.1400% | 11.35% | 55.68% | 2.196 | +0.087 | 10.92% | 0.434 | 0.482 |
| 15m | 1,101 | 1,094 | 6 | 1 | -0.1846% | 11.72% | 58.13% | 2.219 | +0.102 | 11.04% | 0.446 | 0.468 |

Median drift and median R:R do not show broad deterioration. Only one source opportunity touched the target before the 15m close, none did so before 5m or 10m, and 9–12% had moved more than 1% above the open. Opportunity cost is therefore `LOW` under the preregistered structural rule; this classification does not use historical return or portfolio P&L.

## Early path and false starts

At 5m, 473 rows showed early strength, 620 early weakness, and 8 were flat. At 10m the counts were 475, 613, and 13; at 15m they were 449, 640, and 12. False starts, defined as early weakness followed by post-confirmation stop-first, numbered 157, 156, and 157 respectively.

Early weakness occurred in 63.14%, 63.14%, and 63.53% of frozen stop-first paths at 5m, 10m, and 15m. It also occurred in 43.10%, 39.22%, and 37.07% of preregistered good paths. Thus early weakness has a consistent failure association but would also discard a material share of good paths. The descriptive false-start classification is `PROMISING_FOR_CONTROLLED_TEST`; it is not an entry filter.

Failure-minus-good early-weakness separation was supportive in all nine window/year cells: +16.31 to +23.42 percentage points at 5m, +17.83 to +27.64 at 10m, and +23.06 to +28.56 at 15m. Temporal consistency is `CONSISTENT` under the preregistered descriptive rule. The full evidence gate, not any single cohort, authorizes only a later controlled experiment.

## VWAP and opening range

Above-VWAP sample counts were 546, 525, and 490 at 5m, 10m, and 15m. Below-VWAP counts were 549, 573, and 606. Median post-confirmation MFE R was lower above VWAP than below VWAP in every window (approximately 0.393 versus 0.472 at 5m, 0.389 versus 0.467 at 10m, and 0.372 versus 0.510 at 15m). The preregistered result is `NO_CLEAR_ASSOCIATION`, not a VWAP rule.

The confirmation close belongs to the same bars that define its matching opening range. It therefore cannot be above that range high or below that range low: those empirical pilot categories are mechanically `NOT_AVAILABLE`. Exact high/low boundary states are retained separately from `INSIDE_OR`. Most rows were inside their opening range: 1,018 at 5m, 1,048 at 10m, and 1,059 at 15m. Exact-boundary samples were small or very small, so `OPENING_RANGE_CONTEXT_RESULT=INCONCLUSIVE`.

Opening-range width is reported in absolute price, percent, and decision-time ATR14 units. ATR is frozen daily context and is not recomputed from intraday outcomes.

## Contexts, source/admitted comparison, and sensitivity

The diagnostic reports score 80–85, setup `VALID`/`STRONG`, frozen candidate stage, Bullish/Neutral regime, frozen R:R band, and upstream opening-gap band. Cells under 30 remain visible and are explicitly non-interpretable. In particular, Neutral regime and confirmed-only-stage samples are very small. Descriptive differences across adequately sized score, setup, stage, R:R, and gap cohorts are mixed and do not define a new filter.

Admitted covered trades had slightly lower feasible rates than the source population (99.21% versus 99.36–99.55%), slightly less-negative median drift, higher median MFE R, and lower median MAE R. These differences demonstrate portfolio-selection distortion; admissions were not rerun.

The known unexplained SCHAEFFLER daily mismatch on 2023-09-01 does not enter the 1,101-row primary population. The with/without sensitivity is consequently identical, and the result was not tuned around it.

## Results and interpretation

- `CONFIRMATION_5M_RESULT=PROMISING_FOR_CONTROLLED_TEST`
- `CONFIRMATION_10M_RESULT=PROMISING_FOR_CONTROLLED_TEST`
- `CONFIRMATION_15M_RESULT=PROMISING_FOR_CONTROLLED_TEST`
- `VWAP_CONTEXT_RESULT=NO_CLEAR_ASSOCIATION`
- `OPENING_RANGE_CONTEXT_RESULT=INCONCLUSIVE`
- `FALSE_START_FILTERING_RESULT=PROMISING_FOR_CONTROLLED_TEST`
- `CONFIRMATION_DELAY_COST_RESULT=LOW`
- `INTRADAY_CONFIRMATION_DIAGNOSTIC_RESULT=SUPPORTED_FOR_CONTROLLED_TEST`
- `INTRADAY_CONFIRMATION_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING=YES`

The main tension is stable: early weakness is more common among frozen failures, but it is also common among good paths. Feasibility, delay cost, R:R preservation, multi-year consistency, and sample adequacy satisfy the preregistered gate for a later isolated controlled experiment. This is not a strategy rule or promotion, and no 5m/10m/15m reference is described as best, optimal, or a winner.

## Artifacts and limitations

Machine reports are under `data/reports/intraday_confirmation_v1_*`. The population, pre-registration registry, final registry, per-experiment results, and run manifest are under `data/research/diagnostics/intraday/v1/confirmation_command_01/`. Both locations are ignored by Git.

The real data is restricted to the frozen selected-symbol scope. Warning sessions are excluded from the primary analysis rather than imputed. Confirmation references are hypothetical and do not include execution costs. Same-bar sequence ambiguity remains unresolved. No live signal, live order, broker-order method, remote migration, or Supabase write occurs.
