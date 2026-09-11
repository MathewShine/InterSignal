# Strategy Diagnostic Synthesis V1

## Scope

`STRATEGY_DIAGNOSTIC_SYNTHESIS_V1` / `SWING_STRATEGY_RESEARCH_SYNTHESIS_V1` is the Step 02.13 Command 06 research-decision support layer. It consumes the completed Command 01–05 registry and reports. It does not run a strategy variant, add an experiment, modify Strategy V1, create Strategy V2, select a historical winner, optimize, or promote anything.

The frozen baseline remains 728 admitted trades, ending equity 86,107.2268, gross return −13.8928%, CAGR −3.1829%, and maximum drawdown 25.7682%. These values provide context only and are prohibited from entering the hypothesis-priority score.

## Input integrity and diagnostic coverage

The required registry contains exactly 49 unique, complete, unpromoted records: ranking 4, holding 4, entry timing/gap 4, exit/stop path 7, entry quality 10, score calibration 10, and regime context 10. Its fixed ID/hash fingerprint is validated before synthesis. The five source summaries must be ready, failure-free, and unchanged.

Coverage is `BROAD`, while overall multiple-comparison risk is `HIGH`. Ranking, horizon, gap, exits, extension, score, regime, and portfolio selection have been inspected. Cost realism, intraday timing, point-in-time news/catalyst, and stock-specific sector context remain important gaps. Forty-nine diagnostics make stricter preregistration and an untouched temporal holdout mandatory for later work.

## Evidence and risk methodology

Evidence is `HIGH` when multiple diagnostics or direct mechanical evidence have adequate samples and preserved chronology; `MEDIUM` when one strong or several aligned descriptive findings retain a material limitation; `LOW` when evidence is weak, unstable, interaction-dependent, or purely descriptive; and `VERY_LOW` for tiny/incomplete samples or speculation.

Overfitting risk is based on the number of related variants already inspected, outcome-motivated rule risk, sample adequacy, temporal stability, and parameter freedom. It is `LOW`, `MODERATE`, `HIGH`, or `VERY_HIGH`. Engineering/research complexity is separately `LOW`, `MEDIUM`, or `HIGH`, and impact is local, component-level, entry-policy, exit-policy, portfolio-policy, or system-wide.

The preregistered non-performance priority weights are evidence strength 25%, research importance 20%, sample adequacy 15%, temporal stability 15%, low overfitting risk 15%, and low dimensionality/simplicity 10%. Ending equity, return, CAGR, drawdown, gross P&L, and realized R are excluded. A `PRIORITY_A` candidate must not be contradicted; must have at least medium evidence or critical importance; must have adequate/limited samples; must change no more than one dimension; must avoid post-hoc threshold mining; must have low/moderate overfitting risk; and must have explicit falsification criteria.

## Main synthesis

- Ranking and four-slot selection are material interpretation problems. Simple SCORE_ONLY, RR_FIRST, and SETUP_FIRST rankings did not solve the strategy, so another open-ended ranking search would be high-risk.
- The holding horizon matters mechanically, but fixed 6/8/10-session extensions did not consistently solve results.
- Gap behavior is mixed and context-dependent; a universal positive-gap exclusion is unsupported.
- Material giveback exists. Simple +0.5R/+1R protection worsened results, and fixed 1R/1.5R/2R targets did not deliver a robust solution.
- Systematic entry exhaustion is not supported. Higher score was not simply more extended.
- Total score is only partially discriminative. Low component redundancy does not identify correct weights. The R:R component remains a defensible isolated calibration question.
- Bullish was stronger than Neutral at a high level, but Neutral is small. Fine-grained regime strength is not monotonic, breadth is only weakly positive and unstable, and new-Bullish persistence lacks replication.
- Calendar behavior is unstable. Strategy V1 is negative gross before costs, and no completed diagnostic supports live progression.

The resulting classifications are `DIAGNOSTIC_COVERAGE_RESULT=BROAD`, `OVERFITTING_RISK_RESULT=HIGH`, `STRATEGY_V1_RESEARCH_RESULT=WEAK_AND_REQUIRES_RESEARCH`, `DATA_READINESS_RESULT=LIMITED_BUT_USABLE`, and `NEXT_PHASE_READINESS=INFRASTRUCTURE_REQUIRED_FIRST`.

## Ruled-out simple forms and unresolved work

The machine report lists each ruled-out form with originating command and experiment. It includes the three simple rankings, each 6/8/10-day blanket horizon, both simple protection thresholds, each 1R/1.5R/2R fixed target, a simple high-extension penalty, monotonic stronger-Bullish logic, and a universal positive-gap exclusion.

Unresolved questions include stop-loss contribution, partial score calibration, the 2023 difference, ranking/slot interaction, R:R mapping, breadth replication, Bullish persistence, missing sector/catalyst history, and daily-bar execution ambiguity.

## Data readiness

The score is `LIMITED_BY_MISSING_COMPONENTS`: stock-sector scoring (10 points) and catalyst/news scoring (5 points) are historically unavailable. Global/GIFT, India VIX, and intraday regime confirmation are also unavailable. Daily OHLC cannot fully order intraday events. Costs, slippage, taxes, and real fills are absent. Membership history, corporate-action exclusions, small Confirmed-only and Neutral cohorts, and partial 2026 limit interpretation.

Intraday data priority is `CRITICAL`. It is required to validate 5–15 minute confirmation, retests, VWAP behavior, precise entry timing, and stop/target ordering. A realistic cost/slippage/tax model is `HIGH_PRIORITY_INFRASTRUCTURE` before any promotion-level conclusion.

Missing-data research value is ranked: intraday bars, point-in-time stock-sector mapping, India VIX, point-in-time catalyst/news, then a defensible Global/GIFT proxy. This is a research-value ranking, not a claim that any source is available.

## Temporal protocol and sample guidance

The proposed calendar protocol is development on 2022–2024 (2,068 source opportunities, 478 admissions) and untouched validation on 2025–latest frozen partial 2026 (1,224 source, 246 admissions). The split is calendar-defined rather than performance-selected. The validation terminal date must be frozen before future work, and validation must never tune parameters.

After a first untouched holdout, an expanding-window walk-forward replication may be preferable for later robustness testing. It is not implemented here.

Samples below 30 are not inferential; 30–99 are small; 100–299 limited; and 300 or more adequate for description. Promotion-level decisions require adequate source paths and trade counts across multiple periods, explicit nonzero costs, and untouched validation.

## Proposed work, not executed

At most three later research proposals are recorded: a one-dimension slot-capacity test with ranking and signals frozen; one architecture-led monotone R:R mapping; and an untouched temporal replication with Strategy V1 parameters unchanged. Each has predeclared samples and falsification criteria.

The three leading infrastructure items are a realistic cost/slippage/tax model, a fixed temporal holdout/walk-forward harness, and a point-in-time intraday execution layer. Historical sector and catalyst data remain important after those immediate controls.

The mandatory policy is `ONE_RESEARCH_DIMENSION_AT_A_TIME`. Ranking must be frozen before signal changes. Every later experiment must state one changed dimension, frozen comparison, parameters, primary/secondary metrics, samples, temporal robustness, falsification, promotion prohibition, and follow-up decision rule before results.

## Readiness

`LIVE_TRADING_READY=false` and `SMALL_CAPITAL_LIVE_READY=false`. The project is `READY_FOR_FURTHER_RESEARCH` and `READY_FOR_PAPER_RESEARCH_ONLY`; that is not permission to deploy capital. No Strategy V2 artifact exists at the end of Command 06.
