# Daily Breakout Setup Evaluation

Current phase: Step 02.6 / Command 01 - breakout-quality and daily entry-setup evaluation foundation

## Boundary

- Setup Evaluation is not the final Entry Engine.
- It creates setup state, quality descriptors, evidence, and warnings only.
- No final 0-100 entry score, Entry Eligible band, High Conviction band, stop loss, target, risk/reward, position sizing, future outcome labels, backtesting, paper trading, live feeds, orders, migrations, or Supabase persistence are implemented.

## Version

- Setup methodology: DAILY_SETUP_EVALUATION_V1
- Setup config hash: 1dcc8d7790116e56
- Candidate input: MOMENTUM_CANDIDATES_V1 / d111957c7a24da96
- Feature input: DAILY_FEATURES_V1

## Architecture

- Momentum Candidate Snapshot + DAILY_FEATURES_V1 + adjusted daily OHLC feed deterministic setup components.
- Output availability is EOD and intended for NEXT_SESSION_DECISION_INPUT.
- Candidate, setup, and future entry layers remain separate.

## Methodology

- Breakout states: APPROACHING, TESTING, INTRADAY_BREAK_ONLY, CLOSE_ABOVE, CLOSE_ACCEPTED, FAILED_BREAK, NOT_NEAR_LEVEL.
- Level quality uses prior 20-session touch count, days since prior high, proximity to level, and range compression.
- Consolidation uses 5d/10d/20d range width, ATR contraction, and price proximity to highs.
- Acceptance uses close above prior high, close distance, close location, body, upper wick, volume support, and benchmark RS support.
- Candle quality uses close location value, body size, and upper-wick size.
- Volume confirmation is descriptive: WEAK, NORMAL, GOOD, STRONG, EXCEPTIONAL.
- Benchmark RS is WEAK, NEUTRAL, POSITIVE, STRONG, or UNKNOWN if unavailable.
- Sector context is preserved as metadata and not used as mandatory evidence.
- Extension risk uses ATR multiples, SMA20 distance, and candidate-layer extension diagnostics.
- False-breakout warnings are same-day technical flags only.
- Daily reclaim is coarse daily context only: low_T below prior high and close_T above prior high.
- Overhead resistance and 52w context use prior/current daily levels only.
- Momentum continuation is allowed where structure, momentum, candle, RS, and extension still support continuation.
- Setup quality is a descriptor only: POOR, WATCH, VALID, STRONG.

## Full Generation

- Full generation completed: True
- Candidate rows evaluated: 142202
- Setup eligible: 29748
- Setup rejected: 112454
- STRONG: 10004
- VALID: 19744
- WATCH: 45289
- POOR: 67165
- Emerging pass rate: 20.4146%
- Confirmed pass rate: 22.5902%
- Per-day setup eligible: min=0, median=22.0, mean=24.7076, p90=48, p95=57, max=108
- Setup dataset: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\research\setups\daily\v1\daily_setup_evaluations_v1.csv.gz

## Pilot Examples

- clean_20d_breakout: found; ABB 2021-10-29 VALID CLOSE_ACCEPTED
- approaching_breakout: found; ACC 2021-10-29 VALID APPROACHING
- strong_continuation: found; RAMCOCEM 2021-10-29 STRONG CLOSE_ACCEPTED
- failed_intraday_breakout: found; BAJAJHLDNG 2021-10-29 POOR FAILED_BREAK
- large_upper_wick: found; BAJAJHLDNG 2021-10-29 POOR FAILED_BREAK
- tight_consolidation_breakout: found; ACC 2021-11-01 WATCH CLOSE_ABOVE
- loose_or_noisy_consolidation: found; BIRLACORPN 2021-10-29 POOR CLOSE_ABOVE
- emerging_low_rvol_candidate: found; ABFRL 2021-10-29 POOR NOT_NEAR_LEVEL
- confirmed_strong_rvol_candidate: found; AAVAS 2021-10-29 POOR NOT_NEAR_LEVEL
- corporate_action_blocked_candidate: found; BHARTIARTL 2021-09-30 POOR UNAVAILABLE
- infibeam_or_excluded_case: found; INFIBEAM 2021-09-30 POOR UNAVAILABLE

## Major Rejection Reasons

- POOR_CANDLE_QUALITY: 93646
- INSUFFICIENT_SETUP_CONFIRMATION: 72957
- NO_CLEAR_BREAKOUT_OR_CONTINUATION: 41294
- POSSIBLE_FALSE_BREAKOUT: 25871
- CONFIRMED_REQUIRES_CLOSE_OR_CONTINUATION: 19548
- EXTREME_EXTENSION: 3038

## Integrity And Safety

- DAILY_FEATURES_V1 unchanged: True
- MOMENTUM_CANDIDATES_V1 unchanged: True
- Candidate config hash unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.

## Known Limitations

- No intraday opening-range breakout or precise intraday retest/reclaim detection is attempted.
- No future price outcome, target, stop, MFE, MAE, or winner/loser labels are generated.
- Historical sector-relative strength remains metadata-only when sector mapping is current-only.
- Thresholds are baseline research defaults, not optimized parameters.
