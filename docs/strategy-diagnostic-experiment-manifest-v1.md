# Strategy Diagnostic Experiment Manifest V1

All experiments depend on the frozen `PORTFOLIO_BACKTEST_V1` chain, remain **HISTORICAL RESEARCH ONLY / GROSS BEFORE COSTS**, and have promotion status **NOT_ELIGIBLE**.

| ID | Family | Hypothesis | Parameter variation | What remains fixed | Evaluation metrics | Promotion |
|---|---|---|---|---|---|---|
| EXP-RANK-001 | RANKING_DIAGNOSTIC | H1 ranking reproduction | BASELINE_RANK | All frozen portfolio mechanics | Portfolio metrics, yearly results, overlap | NOT_ELIGIBLE |
| EXP-RANK-002 | RANKING_DIAGNOSTIC | H1 ranking sensitivity | SCORE_ONLY: score → symbol | Entry, four slots, sizing, risk, exits, costs | Portfolio metrics, yearly results, overlap | NOT_ELIGIBLE |
| EXP-RANK-003 | RANKING_DIAGNOSTIC | H1 ranking sensitivity | RR_FIRST: R:R → score → symbol | Entry, four slots, sizing, risk, exits, costs | Portfolio metrics, yearly results, overlap | NOT_ELIGIBLE |
| EXP-RANK-004 | RANKING_DIAGNOSTIC | H1 ranking sensitivity | SETUP_FIRST: setup → score → R:R → symbol | Entry, four slots, sizing, risk, exits, costs | Portfolio metrics, yearly results, overlap | NOT_ELIGIBLE |
| EXP-HOLD-001 | HOLD_HORIZON_DIAGNOSTIC | H4 horizon anchor | Four sessions | Ranking, entry, slots, sizing, risk, stop, target | Portfolio metrics, holding and exit distribution | NOT_ELIGIBLE |
| EXP-HOLD-002 | HOLD_HORIZON_DIAGNOSTIC | H4 horizon sensitivity | Six sessions | Ranking, entry, slots, sizing, risk, stop, target | Portfolio metrics, holding, censoring, overlap | NOT_ELIGIBLE |
| EXP-HOLD-003 | HOLD_HORIZON_DIAGNOSTIC | H4 horizon sensitivity | Eight sessions | Ranking, entry, slots, sizing, risk, stop, target | Portfolio metrics, holding, censoring, overlap | NOT_ELIGIBLE |
| EXP-HOLD-004 | HOLD_HORIZON_DIAGNOSTIC | H4 horizon sensitivity | Ten sessions | Ranking, entry, slots, sizing, risk, stop, target | Portfolio metrics, holding, censoring, overlap | NOT_ELIGIBLE |
| EXP-ENTRY-001 | ENTRY_TIMING_DIAGNOSTIC | H2 next-open anchor | All next-open gaps | Frozen opportunities and admissions | Cohort counts, R:R, MFE/MAE, P&L, realized R, exits | NOT_ELIGIBLE |
| EXP-ENTRY-002 | ENTRY_TIMING_DIAGNOSTIC | H2 gap relationship | Gap ≤ 0% cohort | Frozen opportunities and admissions | Cohort counts, R:R, MFE/MAE, P&L, realized R, exits | NOT_ELIGIBLE |
| EXP-ENTRY-003 | ENTRY_TIMING_DIAGNOSTIC | H2 gap relationship | 0% < gap ≤ 0.5% cohort | Frozen opportunities and admissions | Cohort counts, R:R, MFE/MAE, P&L, realized R, exits | NOT_ELIGIBLE |
| EXP-ENTRY-004 | ENTRY_TIMING_DIAGNOSTIC | H2 gap relationship | Gap > 0.5% cohort | Frozen opportunities and admissions | Cohort counts, R:R, MFE/MAE, P&L, realized R, exits | NOT_ELIGIBLE |

No experiment is named or interpreted as better, improved, optimal, or a winner. The registered hypotheses remain unconfirmed until the diagnostic outputs are reviewed.

## Command 02 — Exit / Stop-Path Diagnostic Family

The following seven definitions are appended without changing any completed Command 01 definition or hash. Their detailed, pre-registered semantics are documented in `strategy-diagnostic-exit-stop-path-v1.md`.

| ID | Family | Hypothesis | Parameter variation | What remains fixed | Evaluation metrics | Promotion |
|---|---|---|---|---|---|---|
| EXP-EXIT-001 | EXIT_DIAGNOSTIC | H3/H5 baseline exit anchor | Frozen exit reproduction | Full Strategy V1 baseline | Portfolio, exit, occupancy, yearly, giveback | NOT_ELIGIBLE |
| EXP-EXIT-002 | EXIT_DIAGNOSTIC | H5 prior favorable excursion | Protect at entry next session after completed prior +0.5R | Frozen target and all non-exit mechanics | Portfolio, activation paths, transformed stops, occupancy | NOT_ELIGIBLE |
| EXP-EXIT-003 | EXIT_DIAGNOSTIC | H5 prior favorable excursion | Protect at entry next session after completed prior +1R | Frozen target and all non-exit mechanics | Portfolio, activation paths, transformed stops, occupancy | NOT_ELIGIBLE |
| EXP-EXIT-004 | EXIT_DIAGNOSTIC | H3 target-distance diagnostic | Fixed +1R target; no protection | Stop, hold, ranking, entry, capacity, risk | Portfolio, target hits, occupancy, profit-cap tradeoff | NOT_ELIGIBLE |
| EXP-EXIT-005 | EXIT_DIAGNOSTIC | H3 target-distance diagnostic | Fixed +1.5R target; no protection | Stop, hold, ranking, entry, capacity, risk | Portfolio, target hits, occupancy, profit-cap tradeoff | NOT_ELIGIBLE |
| EXP-EXIT-006 | EXIT_DIAGNOSTIC | H3 target-distance diagnostic | Fixed +2R target; no protection | Stop, hold, ranking, entry, capacity, risk | Portfolio, target hits, occupancy, profit-cap tradeoff | NOT_ELIGIBLE |
| EXP-EXIT-007 | EXIT_DIAGNOSTIC | H5 stop-path diagnostic | Descriptive earlier-session MFE only | Baseline trades and all mechanics | Stop/time path thresholds and final realized R | NOT_ELIGIBLE |

Command 02 performs no combinatorial tests, parameter search, automatic selection, or promotion. All performance remains historical, gross before costs, and subject to daily-bar ordering limits.

## Command 03 — Entry Quality & Momentum Exhaustion Diagnostic Family

These ten definitions are appended without altering any completed Command 01 or 02 definition or hash. Exact buckets, reference hierarchy, maturity mapping, and classification rules are documented in `strategy-diagnostic-entry-quality-v1.md`.

| ID | Family | Fixed diagnostic | Frozen population | Promotion |
|---|---|---|---|---|
| EXP-ENTRYQ-001 | ENTRY_QUALITY_DIAGNOSTIC | Baseline entry-quality profile | 3,296 source / 728 admitted / 2,568 skipped | NOT_ELIGIBLE |
| EXP-ENTRYQ-002 | ENTRY_QUALITY_DIAGNOSTIC | ATR extension buckets | Unchanged | NOT_ELIGIBLE |
| EXP-ENTRYQ-003 | ENTRY_QUALITY_DIAGNOSTIC | Breakout/reference-distance buckets | Unchanged | NOT_ELIGIBLE |
| EXP-ENTRYQ-004 | ENTRY_QUALITY_DIAGNOSTIC | Prior-day move buckets | Unchanged | NOT_ELIGIBLE |
| EXP-ENTRYQ-005 | ENTRY_QUALITY_DIAGNOSTIC | 5d/10d/20d momentum and maturity class | Unchanged | NOT_ELIGIBLE |
| EXP-ENTRYQ-006 | ENTRY_QUALITY_DIAGNOSTIC | Gap × prior move and maturity × gap | Unchanged | NOT_ELIGIBLE |
| EXP-ENTRYQ-007 | ENTRY_QUALITY_DIAGNOSTIC | Upstream RVOL state × ATR extension | Unchanged | NOT_ELIGIBLE |
| EXP-ENTRYQ-008 | ENTRY_QUALITY_DIAGNOSTIC | Upstream RS state × ATR extension | Unchanged | NOT_ELIGIBLE |
| EXP-ENTRYQ-009 | ENTRY_QUALITY_DIAGNOSTIC | Frozen score 80–85 × ATR extension | Unchanged | NOT_ELIGIBLE |
| EXP-ENTRYQ-010 | ENTRY_QUALITY_DIAGNOSTIC | Candidate stage × extension | Unchanged | NOT_ELIGIBLE |

Command 03 is descriptive only. It applies no entry filter, reranking, alternate admission, predictive model, parameter optimization, automatic selection, or promotion.

## Command 04 — Score Calibration & Component Discrimination Diagnostic Family

These ten definitions are appended without altering any completed Command 01–03 definition or hash. Exact component mappings, populations, metrics, classification rules, and limitations are documented in `strategy-diagnostic-score-calibration-v1.md`.

| ID | Family | Fixed diagnostic | Frozen population | Promotion |
|---|---|---|---|---|
| EXP-SCORECAL-001 | SCORE_CALIBRATION_DIAGNOSTIC | Total-score 80–85 calibration profile | 3,296 source / 728 admitted / 2,568 skipped | NOT_ELIGIBLE |
| EXP-SCORECAL-002 | SCORE_CALIBRATION_DIAGNOSTIC | Setup component discrimination | Unchanged | NOT_ELIGIBLE |
| EXP-SCORECAL-003 | SCORE_CALIBRATION_DIAGNOSTIC | Momentum component discrimination | Unchanged | NOT_ELIGIBLE |
| EXP-SCORECAL-004 | SCORE_CALIBRATION_DIAGNOSTIC | RVOL component discrimination | Unchanged | NOT_ELIGIBLE |
| EXP-SCORECAL-005 | SCORE_CALIBRATION_DIAGNOSTIC | RS component discrimination | Unchanged | NOT_ELIGIBLE |
| EXP-SCORECAL-006 | SCORE_CALIBRATION_DIAGNOSTIC | Regime component discrimination | Unchanged | NOT_ELIGIBLE |
| EXP-SCORECAL-007 | SCORE_CALIBRATION_DIAGNOSTIC | R:R component and target-distance discrimination | Unchanged | NOT_ELIGIBLE |
| EXP-SCORECAL-008 | SCORE_CALIBRATION_DIAGNOSTIC | Exact six-component vector profiles | Unchanged | NOT_ELIGIBLE |
| EXP-SCORECAL-009 | SCORE_CALIBRATION_DIAGNOSTIC | Score 80–85 decomposition and fixed pair comparisons | Unchanged | NOT_ELIGIBLE |
| EXP-SCORECAL-010 | SCORE_CALIBRATION_DIAGNOSTIC | Yearly component stability | Unchanged | NOT_ELIGIBLE |

Command 04 is descriptive only. It performs no score rewrite, reweighting, threshold search, ranking or portfolio rerun, optimizer, predictive model, automatic selection, winner declaration, or promotion.

## Command 05 — Regime & Market-Context Discrimination Diagnostic Family

These ten definitions are appended without altering any completed Command 01–04 definition or hash. Exact frozen score scales, fixed buckets, population separation, metrics, classification rules, and limitations are documented in `strategy-diagnostic-regime-context-v1.md`.

| ID | Family | Fixed diagnostic | Frozen population | Promotion |
|---|---|---|---|---|
| EXP-REGIME-001 | REGIME_CONTEXT_DIAGNOSTIC | Baseline Bullish/Neutral and separate research-cohort profile | 3,296 normal source / 728 admitted; separate Bearish exceptional and unavailable | NOT_ELIGIBLE |
| EXP-REGIME-002 | REGIME_CONTEXT_DIAGNOSTIC | Fixed normalized regime-score buckets | Unchanged | NOT_ELIGIBLE |
| EXP-REGIME-003 | REGIME_CONTEXT_DIAGNOSTIC | Fixed Bullish-strength buckets | Unchanged | NOT_ELIGIBLE |
| EXP-REGIME-004 | REGIME_CONTEXT_DIAGNOSTIC | Fixed Neutral-position buckets | Unchanged | NOT_ELIGIBLE |
| EXP-REGIME-005 | REGIME_CONTEXT_DIAGNOSTIC | Frozen Nifty-trend contribution discrimination | Unchanged | NOT_ELIGIBLE |
| EXP-REGIME-006 | REGIME_CONTEXT_DIAGNOSTIC | Frozen Nifty 500 breadth contribution discrimination | Unchanged | NOT_ELIGIBLE |
| EXP-REGIME-007 | REGIME_CONTEXT_DIAGNOSTIC | Frozen market-wide sector-index participation discrimination | Unchanged | NOT_ELIGIBLE |
| EXP-REGIME-008 | REGIME_CONTEXT_DIAGNOSTIC | Regime context × frozen Strategy Score 80–85 | Unchanged | NOT_ELIGIBLE |
| EXP-REGIME-009 | REGIME_CONTEXT_DIAGNOSTIC | Regime context × setup/R:R/candidate/gap | Unchanged | NOT_ELIGIBLE |
| EXP-REGIME-010 | REGIME_CONTEXT_DIAGNOSTIC | Yearly regime/component stability | Unchanged | NOT_ELIGIBLE |

Command 05 is descriptive only. It performs no regime or score threshold change, reweighting, Neutral exclusion, hysteresis, smoothing, persistence gate, ranking or portfolio rerun, optimizer, predictive model, automatic selection, or promotion. Future regime states are post-admission diagnostic labels only.
