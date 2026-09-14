# Strategy Family C Research Closure V1

## Decision

`FAMILY_C_RESEARCH_CLOSURE_V1` freezes Strategy Family C under the `BREAKOUT_CONTINUATION_CLOSURE_V1` profile. Family C is `PAUSED_NO_VALIDATION_CANDIDATE`; its evidence status is `POSITIVE_COMPRESSION_SIGNAL_NOT_PORTFOLIO_READY`. This command reads immutable DEVELOPMENT evidence only. It does not rerun performance, alter a strategy parameter, access validation, or create Strategy V2.

## Frozen research chain

`CONTROL-C-000` (`PURE_20D_CLOSE_BREAKOUT_V1`) was nonviable. Its executable portfolio had -0.92641584% net CAGR, 0.9848628175 net profit factor, 36.29593748% maximum drawdown, and 46.39249639% position win rate. Its final status is `CLOSED_NONVIABLE_CONTROL`.

`BRK-C-001` (`20D_BREAKOUT_WITH_10D_COMPRESSION_V1`) was `PARTIALLY_SUPPORTED`. It produced +9.82445552% net return, +3.17306986% net CAGR, 22.08443282% maximum drawdown, 49.74358974% position win rate, +0.209322798% net expectancy, and 1.073020458 net profit factor. Its final status is `PAUSED_POSITIVE_SIGNAL_INSUFFICIENT_IMPLEMENTATION`.

The C001 attribution audit found `CLEAR_POSITIVE` event-level compression evidence with `MOSTLY_CONSISTENT` temporal support. The 4,247 compression-pass events had 51.4245% win rate, +0.4394% normalized net expectancy, and 1.2108367955 net profit factor. The 7,961 compression-fail events had 48.0342% win rate, +0.1458% normalized net expectancy, and 1.0502432731 net profit factor. The development advantage was `PRIMARILY_COMPRESSION_SIGNAL`.

Portfolio realization remained inadequate. C001 rejected 61.7848% of entry-ready signals for capacity, the frozen breakout-strength ranking was `NO_DISCRIMINATION`, and admitted events were `SELECTED_WORSE` than capacity-rejected events. Capacity impact was `MATERIAL`.

`C1-IMP-001` changed only capacity ordering to tightest compression first. It failed: +0.6154649% net return, +0.2047355143% net CAGR, 19.14689006% maximum drawdown, 49.27163668% position win rate, +0.0484116391% net expectancy, and 1.0049998766 net profit factor. It passed zero of three admitted-quality dimensions and five of eight standard criteria; replacement quality was `WORSE`. Its final status is `CLOSED_FAILED_IMPLEMENTATION_HYPOTHESIS`.

`BRK-C-002` tested 1.5x breakout-day volume expansion and failed with -14.37381646% net return, -5.04113192% net CAGR, negative expectancy, and 0.9172192606 net profit factor. Its final status is `CLOSED_FAILED_DEVELOPMENT`.

## Preserved evidence and lesson

`EDGE-EVIDENCE-C-COMPRESSION-001` preserves the finding that 10-session compression no greater than 8% before a strict 20-session close breakout demonstrated positive event-level discrimination in DEVELOPMENT. Its status is `RESEARCH_EVIDENCE_NOT_VALIDATED`. The registry stores event counts, win-rate, expectancy and profit-factor differences, temporal consistency, median MFE/MAE differences, and limitations. This is not an executable-strategy or out-of-sample claim.

`EDGE-NEGATIVE-C-VOLUME-001` records that the tested 1.5x volume-expansion definition did not improve the architecture. `IMPLEMENTATION-NEGATIVE-C-COMPRESSION-RANK-001` records that tightest-compression-first capacity ranking failed.

The frozen research lesson is:

> A compact pre-breakout range improved 10-session breakout event quality in DEVELOPMENT, but frequent overlapping signals and portfolio-capacity/admission mechanics prevented the current implementation from converting that signal edge into a sufficiently robust executable strategy.

Volume expansion at the tested 1.5x definition did not improve the strategy. Do not generalize beyond tested definitions.

Family C did not achieve the aspirational 60% position win rate: the control was 46.39%, C001 portfolio 49.74%, the C001 event cohort 51.42%, and C1-IMP-001 49.27%. Research conclusions must not be altered solely to target 60%.

## Governance and future use

The C001 signal status is `PRESERVE_AS_POSITIVE_RESEARCH_EVIDENCE`. Its future policy is `REQUIRES_GENUINELY_NEW_ARCHITECTURE_OR_MULTI_STRATEGY_USE`. Any return requires a new conceptual hypothesis, a new experiment ID, preregistration, and justification beyond another threshold or ranking tweak.

Incremental Family C V1 tuning is deprioritized: compression thresholds of 6%, 7%, 9%, or 10%; capacities of 10, 15, 25, 30, or 40; alternate same-day rankings; different fixed sizing or holding; simple stop/target additions; gap filters; and volume-plus-compression combinations. A genuinely new research architecture would require separate justification.

`DAILY_HISTORY_PREHISTORY_V2`, structural signal datasets, attribution datasets, and capacity diagnostics remain preserved research infrastructure. `RESEARCH_EXPERIMENT_GOVERNANCE_V2` remains active. There were zero live signals, live orders, broker calls, remote migrations, Supabase writes, database writes, and network calls.

## Handoff

Family D is `NEXT_PLANNED` only: `FAMILY_D_OPENING_RANGE_STOCKS_IN_PLAY`. Its high-level concept combines unusual early-session activity, opening-range structure, and intraday breakout or continuation, potentially using the existing real 5-minute dataset. This differs materially from medium-term momentum, absolute-momentum filters, and daily breakout continuation. No parameters or implementation exist, and no performance claim is made.

Before any Family D performance work, governance requires preregistration of the exact opening range, activity definition, entry/exit rules, capital/capacity, and success criteria.
