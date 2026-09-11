# Strategy Diagnostic Exit / Stop-Path V1

## Status and scope

`STRATEGY_DIAGNOSTIC_EXIT_STOP_PATH_V1` is Step 02.13 / Command 02 of `STRATEGY_DIAGNOSTIC_FRAMEWORK_V1` (`SWING_STRATEGY_DIAGNOSTICS_V1`). It is **HISTORICAL RESEARCH ONLY / GROSS BEFORE COSTS**. Every experiment is diagnostic-only, is ineligible for promotion, and cannot change the frozen Strategy V1 baseline.

This command tests one dimension: exit and stop-path semantics. It does not change opportunity eligibility, the baseline ranking, next-session-open entry, four-session horizon, one-percent trade risk, four-percent total open-risk admission cap, four-position limit, one-open-position-per-symbol policy, long cash-equity direction, or no-leverage rule. It does not model fees, taxes, spread, market impact, or slippage.

## Frozen baseline dependency

All seven definitions depend on `PORTFOLIO_BACKTEST_V1`, `SWING_PORTFOLIO_BACKTEST_V1`, config hash `6e98307afead0ffa`, and the frozen feature, candidate, setup, regime, entry, Risk V1, Risk V1.1, Score V1, Outcome V1, and portfolio-ledger hashes. The runner reads and checks those hashes before and after both canonical executions of every experiment.

`EXP-EXIT-001` is an exact reproduction gate. It must match 728 admitted trades, 2,568 skips, ₹86,107.226785713465 ending equity, −13.892773214286535% gross return, −3.182877736277989% CAGR, 25.76815326209741663605033331% maximum drawdown, and the frozen 27 target / 159 stop / 542 time exits. A mismatch stops the suite.

## Preregistered hypotheses and experiments

The finite allowlist was written to `data/research/diagnostics/strategy/v1/exit_command_02/registry/exit_experiment_registry_v1_preregistered.json` before simulation. Each record stores parameters, a parameter hash, a Command-02 pre-registration hash, evaluation fields, frozen dependencies, and `promotion_allowed = false`.

| ID | Name | Preregistered variation | Hypothesis |
|---|---|---|---|
| EXP-EXIT-001 | BASELINE_EXIT_REPRODUCTION | Frozen stop, frozen target, session-4 close | The baseline exit path reproduces exactly. |
| EXP-EXIT-002 | PROTECT_AFTER_0_5R | Protect at entry from the session after a completed prior session reaches +0.5R | Prior favorable movement may precede material giveback. |
| EXP-EXIT-003 | PROTECT_AFTER_1R | Protect at entry from the session after a completed prior session reaches +1R | Prior favorable movement may precede material giveback. |
| EXP-EXIT-004 | FIXED_1R_PROFIT_EXIT | Replace only the target with +1R | Target distance may affect exit mix and occupancy within four sessions. |
| EXP-EXIT-005 | FIXED_1_5R_PROFIT_EXIT | Replace only the target with +1.5R | Target distance may affect exit mix and occupancy within four sessions. |
| EXP-EXIT-006 | FIXED_2R_PROFIT_EXIT | Replace only the target with +2R | Target distance may affect exit mix and occupancy within four sessions. |
| EXP-EXIT-007 | EARLY_STOP_DIAGNOSTIC_ONLY | Descriptive path review; no portfolio change | Stop exits may divide into never-favorable and earlier-session-favorable paths. |

The numerical variants came from the command specification, not from a search. No grid, optimizer, adaptive threshold, automatic selector, or combined experiment exists.

## Exact protection semantics

For `EXP-EXIT-002` and `EXP-EXIT-003`, the frozen target remains unchanged. A threshold reached during a completed session records activation at that session’s close. The effective stop changes to the entry price only from the next session. There is no same-bar activation and no use of same-session favorable excursion to protect a trade that also reaches its original stop.

Once protection is active:

- a later session opening below entry exits at that opening price as `PROTECTED_STOP_GAP_EXIT`;
- a later session trading through entry exits at entry as `PROTECTED_STOP_EXIT`;
- a protected stop and target touched in one daily bar remains `AMBIGUOUS_SAME_BAR_EXIT` under conservative stop-first pricing;
- otherwise the frozen target and session-4 close remain operative.

The protected-gap rule is explicitly limited to these two experiments. The baseline retains its frozen exact-stop fill convention.

## Exact fixed-target semantics

For `EXP-EXIT-004` through `EXP-EXIT-006`, the target is `entry + fixed_R × initial_risk_per_share`. The original stop remains unchanged, protection is disabled, and the session-4 close remains the time exit. If the fixed target and original stop are both touched in a daily bar, the conservative stop-first price applies and the state is `AMBIGUOUS_SAME_BAR_EXIT`.

No experiment combines protection with a fixed target. There are no partial exits, trailing stops, dynamic targets, alternate rankings, alternate entry gaps, longer holds, score changes, regime changes, risk changes, or position-count changes.

## Chronological portfolio effects

All portfolio experiments rerun the complete 3,296-opportunity frozen cohort in chronological order. Admissions occur at the session open before that session’s exits, so exit proceeds are not reused on the same day. Earlier or later exits can change later slot availability, same-symbol conflicts, cash, opening equity, sizing, and the admitted source-key set. The reports therefore separate exit outcomes from occupancy effects using days at maximum capacity, occupancy-days, each skip category, new/lost admissions, and Jaccard overlap.

## Descriptive path and giveback conventions

For baseline `STOP_EXIT` trades, `EXP-EXIT-007` counts favorable thresholds only from fully completed sessions strictly before the stop date. The stop bar’s high is excluded because daily OHLC cannot prove that favorable excursion happened before the stop.

For `TIME_EXIT` trades, the exit occurs at the fourth-session close, so that session’s high is included as occurring before the close. This convention reproduces the prior descriptive findings that 256 time exits reached at least +0.5R and 123 reached at least +1R.

`giveback_r = peak_mfe_r_before_exit − realized_r`. With daily data, the stored peak includes the exit-bar high and is therefore a descriptive upper bound when an intraday stop/target event occurs. Overall and exit-type mean, median, p75, and p90 values must not be read as intraday-ordered evidence.

## Evaluation and structural classifications

Portfolio reports include opportunity and admission counts, equity, return, CAGR, maximum drawdown, realized-R distribution, positive-P&L rate, exit counts/rates, holds, turnover, overlap, occupancy, skip profiles, yearly 2022–2026 results, and one-year P&L concentration. Protection reports add activation and post-activation paths plus transformations of overlapping baseline stops. Fixed-target reports add target-exit R, changed admissions, target-distance context, and profit-cap tradeoffs.

Classification thresholds were locked into every definition through a hash before results:

- `EXIT_PATH_RESULT`: high at median giveback ≥0.75R or mean ≥1R; material at median ≥0.25R or mean ≥0.5R; otherwise low; fewer than 20 observations is inconclusive.
- `PROTECTION_DIAGNOSTIC_RESULT` and `FIXED_TARGET_DIAGNOSTIC_RESULT`: material if any family run has baseline Jaccard below 0.80 or an absolute return/drawdown change of at least five percentage points; mixed if the corresponding thresholds are 0.95 or one point; otherwise no clear effect; fewer than 20 trades is inconclusive.
- `EXIT_OCCUPANCY_RESULT`: high if minimum baseline Jaccard is below 0.50 or the maximum-position skip change is at least 20% of baseline; moderate at 0.80 or 5%; otherwise low; fewer than 20 trades is inconclusive.
- `FRAMEWORK_RESULT` is `CLEAN` only when baseline reproduction, pilot validation, repeated canonical outputs, statuses, and all frozen-hash guards pass.

These classifications describe structural differences; they do not select a preferred exit or authorize implementation in Strategy V1.

## Pilot and reproducibility

The pilot covers cases A–N: baseline target, stop without prior +0.5R, stops after prior +0.5R and +1R, time exits after +0.5R and +1R, protection-to-stop and protection-to-target, all three fixed targets, same-bar fixed-target ambiguity, a freed slot, and an occupancy-changed admission. Real frozen examples are used whenever present; synthetic fixtures are permitted only when no real match exists. Stored fields include symbol, dates, entry, risk, activation, next-session stop, target, exit, realized R, slot release, and admission evidence.

Every experiment executes twice from the same preregistered definition. Timestamps and run IDs are excluded from canonical comparison. A differing fingerprint or before/after baseline hash stops completion.

## Storage and non-promotion

Command 02 run artifacts live below `data/research/diagnostics/strategy/v1/exit_command_02/`, separate from Command 01’s `runs/` subtree. The seven final records are appended to the shared framework registry while the prior 12 completed records and their parameter/pre-registration hashes are preserved verbatim. Machine-readable reports use the `data/reports/strategy_diagnostic_v1_exit_*` names required by the command.

No signal is generated, no order is placed, no broker or remote service is called, no database migration runs, and nothing is written to Supabase. Diagnostic artifacts are ignored by Git. This command stops at review readiness and does not begin Command 03.
