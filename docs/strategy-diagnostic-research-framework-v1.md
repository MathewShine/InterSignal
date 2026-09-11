# Strategy Diagnostic Research Framework V1

STATUS: PROVISIONAL_DIAGNOSTIC_RESEARCH_FRAMEWORK

- Version: `STRATEGY_DIAGNOSTIC_FRAMEWORK_V1`
- Profile: `SWING_STRATEGY_DIAGNOSTICS_V1`
- Promotion allowed: **false**
- Performance scope: **HISTORICAL RESEARCH ONLY / GROSS BEFORE COSTS**

## Purpose and frozen boundary

This framework investigates why Strategy V1 produced weak historical gross results. It is not a strategy version, optimizer, or promotion mechanism. It consumes the frozen chain from `DAILY_FEATURES_V1` through `PORTFOLIO_BACKTEST_V1`; it never rewrites those datasets or feeds outcome evidence into candidate, setup, regime, entry, risk, or scoring logic.

Every run records the exact feature, candidate, setup, regime, entry, risk V1/V1.1, score V1, outcome V1, and portfolio-backtest V1 hashes before and after execution. A mismatch fails the experiment.

## Pre-registration and immutability

Every experiment is registered before results are computed. Its SHA-256 pre-registration hash covers framework identity, experiment identity and family, hypothesis, locked parameters, frozen baseline hashes, declared evaluation fields, and metric definitions. Timestamps and results are excluded. Any parameter change changes this hash and requires a new experiment ID; a completed experiment cannot be re-registered or edited.

The registry uses explicit lifecycle states: `REGISTERED`, `READY`, `RUNNING`, `COMPLETE`, `REJECTED`, `INVALID`, and `FAILED`. Failure never becomes partial completion.

## Experiment families

The registry supports ranking, entry-timing, exit, hold-horizon, target, stop, score-calibration, regime, portfolio-capacity, and cost-sensitivity diagnostics. Command 01 authorizes only four ranking, four hold-horizon, and four descriptive entry-gap experiments listed in the manifest.

Ranking adapters change only ordering. Hold adapters change only the time-exit horizon and rerun the portfolio chronologically, allowing longer occupancy to affect later admissions. Entry-gap experiments only segment existing frozen opportunities and admissions; they are not entry filters.

## Pre-registered research hypotheses

- H1 — The four-position limit plus crowded days may make selection order a major determinant of portfolio performance.
- H2 — Next-open entry may lose edge after strong EOD momentum and positive gaps.
- H3 — Many positions time-exit after useful favorable movement; frozen targets may be too distant for a four-session window.
- H4 — Four sessions may be too short for some momentum setups.
- H5 — Stop losses dominate negative P&L; some stop-outs may have had earlier favorable excursion.
- H6 — Raw scores 80–85 may not be monotonic with portfolio returns.
- H7 — Neutral-regime behavior may be weaker than Bullish-regime behavior.
- H8 — Max-position pressure may materially distort which mechanically valid opportunities enter.
- H9 — Weak gross edge may be materially reduced by realistic transaction costs.

These are questions, not conclusions. Command 01 runs only the explicitly authorized H1, H2, and H4 diagnostics; later families require separate authorization.

## Metrics

Portfolio experiments report sample availability, trades, admission rate, ending equity, gross return, CAGR, maximum drawdown, realized-R distribution, positive-P&L rate, exit rates, turnover, holding period, yearly results, and positive/negative/best/worst-year summaries. Comparisons report deltas, admitted-trade Jaccard, source overlap, and skip-profile changes.

Gap cohorts report source/admitted counts, admission rate, effective R:R, four-session MFE/MAE, gross P&L, realized R, and exit distribution. Unavailable and right-censored extended-horizon observations are explicit.

## Research controls

There is no automatic winner selection, optimization, grid/random/Bayesian/genetic search, or result-dependent parameter mutation. No score threshold, score weight, max-position limit, risk percentage, stop, target, regime rule, cost model, or live behavior is changed. All Command 01 experiments have `eligible_for_promotion = false`.

Diagnostics can expose sensitivity, not causality or deployable edge. Comparing a small finite suite still creates multiple-comparison and overfitting risk. Results must remain provisional historical research and cannot replace the active mechanical baseline without a separately authorized, separately versioned process.
