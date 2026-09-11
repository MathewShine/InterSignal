# Strategy Diagnostic Score Calibration V1

## Scope and hypothesis

`STRATEGY_DIAGNOSTIC_SCORE_CALIBRATION_V1` is Step 02.13 / Command 04 under `STRATEGY_DIAGNOSTIC_FRAMEWORK_V1` (`SWING_STRATEGY_DIAGNOSTICS_V1`). It asks whether the frozen `STRATEGY_SCORE_V1` total and its available components discriminate historical opportunity quality. It is descriptive, **HISTORICAL RESEARCH ONLY**, gross before costs, and ineligible for promotion.

The command consumes the frozen feature, candidate, setup, regime, entry, Risk V1/V1.1, score, outcome, and portfolio ledgers. It never rewrites a score, changes a mapping or weight, searches an entry threshold, reranks an opportunity, changes an admission, or generates an alternate portfolio.

## Frozen score and component mappings

The frozen score is `STRATEGY_SCORE_V1` / `SWING_DAILY_EOD_V1`, config hash `e257c76b90e25cb7`. Its weights remain setup 20, momentum 20, RVOL 15, relative strength 15, regime 10, sector 10, catalyst 5, and reward:risk 5. Sector and catalyst were unavailable historically, so the typical available weight is 85. The entry-eligible threshold remains raw score 80 and the high-conviction threshold remains 90; neither is changed or searched.

The exact preregistered score levels are:

- Setup: 16 (`VALID`) and 20 (`STRONG`).
- Momentum: every frozen level 15, 16, 17, 18, 19, and 20.
- RVOL: 0/6/10/13/15 mapped to `WEAK`/`NORMAL`/`GOOD`/`STRONG`/`EXCEPTIONAL`; absent levels remain zero-count rows.
- RS: 0/6/11/15 mapped to `WEAK`/`NEUTRAL`/`POSITIVE`/`STRONG`; absent levels remain zero-count rows.
- Regime: 0/5/10 mapped to exceptional Bearish/Neutral/Bullish; the normal eligible cohort contains Bullish and Neutral only.
- R:R: 0/3/4/5; the eligible source cohort contains 3/4/5.

No alternate component is invented. Component vectors use only setup, momentum, RVOL, RS, regime, and R:R; unavailable sector and catalyst are excluded rather than imputed.

## Preregistered experiments

Exactly ten `SCORE_CALIBRATION_DIAGNOSTIC` experiments are permitted: `EXP-SCORECAL-001` through `EXP-SCORECAL-010`. They cover total-score profiles, the six component families, exact component vectors, score 80–85 decomposition, and yearly component stability. Definitions, metrics, levels, classification rules, score identity, baseline hashes, parameter hashes, and preregistration hashes are written before diagnostic metrics are derived. Completed experiments are immutable.

## Populations and outcome metrics

Every table labels its population. The frozen populations are 3,296 mechanically valid primary/entry-eligible opportunities, 728 admitted portfolio trades, 2,568 skipped opportunities, and the max-position-skipped subset. Source opportunity metrics are four-session MFE_R, MAE_R, close return, and target-first/stop-first/neither. Admitted-trade metrics add realized R, gross P&L, positive-gross-P&L rate, and target/stop/time exits.

Source and admitted results are deliberately compared because portfolio ranking and capacity select a non-random subset. Mathematical necessity to retain raw score 80 is distinct from historical outcome discrimination.

## Component profiles, vectors, and decomposition

The component outcome matrix reports component, frozen value, population, sample size, MFE, MAE, realized R, positive rate, target/stop/time rates, gross P&L, and admission information. Exact six-component vectors are reported for every source vector, with the top 20 marked and sample-size warnings attached.

Score 80–85 decomposition reports mean and median component points plus each component's percentage contribution to the raw score. Score 84 versus 85 and score 80 versus 85 comparisons additionally retain candidate category, setup quality, regime, actual R:R, extension, gap, target distance, outcomes, admissions, and year distributions. These are descriptive comparisons, not score rankings.

Leave-one-component calculations subtract one frozen component without renormalization and count rows that would fall below 80. They do not reapply eligibility, rerun ranking, or simulate a portfolio.

## Correlation, redundancy, and temporal stability

Pearson and Spearman correlations are descriptive only. Component-pair correlations are produced separately for source and admitted populations; component/outcome correlations cover MFE, MAE, four-session close return, and admitted realized R. No significance testing, feature-importance model, regression coefficient, probability calibration, logistic model, tree, random forest, boosting model, neural network, isotonic model, or optimized weight is produced.

Yearly diagnostics cover 2022–2025 and partial 2026. Each component's levels, mean points, outcomes, and admitted realized-R association are reported per year. Direction is classified only where sample and variation support it, and a warning is raised when apparent positive discrimination occurs in only one year.

## Sample safety and interpretation

The locked sample flags are `<30 VERY_SMALL`, `30–99 SMALL`, `100–299 LIMITED`, and `>=300 ADEQUATE_FOR_DESCRIPTION`. Component vectors below 30 are reported but never treated as meaningful evidence. Neutral regime and sparse component endpoint cohorts carry the same warning discipline.

All classifications use locked directional and materiality rules. They do not establish causality and cannot promote a component, change a score, or name a best score. Any repeatable weakness may only set `SCORE_CALIBRATION_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING`; a future change requires a separate preregistered and explicitly authorized command.

## Reproducibility, storage, and restrictions

Each experiment runs twice with frozen hash guards and matching canonical outputs. Command 04 artifacts live under `data/research/diagnostics/strategy/v1/score_calibration_command_04/`, separate from Commands 01–03. Ten records are appended only after verifying the previous 29 experiment hashes, producing a combined registry count of 39.

No score, weight, threshold, candidate rule, setup rule, regime rule, entry rule, risk rule, exit rule, hold horizon, maximum position rule, or portfolio mechanic is changed. No live signal, order, migration, Supabase write, optimization, winner selection, or experiment promotion is allowed.

## Limitations and future testing

Historical association is not causal component value. Portfolio admission introduces selection distortion. Sector and catalyst cannot be evaluated because they were unavailable. Some levels or vectors are absent or small, and some year/component pairs have insufficient variation for correlation. Results remain gross before costs and slippage. Any future test must be independently preregistered; Command 04 stops at review.
