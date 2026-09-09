# Momentum Candidate Engine

Current phase: Step 02.5 / Command 01 - Emerging and Confirmed Momentum research candidates

## Boundary

- Candidate Engine is not an Entry Engine.
- Output means worth further Strategy V1 evaluation, not buy/sell advice.
- No final 0-100 entry score, risk/reward, stops, position sizing, backtesting, future labels, live feeds, or orders are implemented.

## Version

- Candidate methodology: MOMENTUM_CANDIDATES_V1
- Config hash: d111957c7a24da96
- Input features: DAILY_FEATURES_V1 with BENCHMARK_CONTEXT_V1 and SECTOR_CONTEXT_V1.

## Mandatory Gates

- Point-in-time NIFTY_500 universe row from the feature dataset.
- Cash-equity/EQ source policy, with non-standard series rejected if present.
- Corporate-action-safe required feature windows.
- Price between INR 100 and INR 7,000.
- 20-day median traded value at least INR 100,000,000.
- Required momentum, liquidity, volatility, and breakout-context features must be present.

## Emerging Momentum

- Earlier-stage acceleration using positive 3d/5d momentum, improving 10d structure, healthy up-day ratio, emerging relative volume, 20d-high proximity, current-day confirmation, and benchmark-relative support where available.
- Default relative-volume reference: 1.20x.
- Requires mandatory gates plus at least 4 emerging evidence flags.

## Confirmed Momentum

- Stronger established momentum using 5d/10d/20d return depth, 1.50x relative volume, repeated positive sessions, 20d-high test/clearance, current-day strength, and 20d benchmark-relative support.
- Requires mandatory gates plus at least 5 confirmed evidence flags.
- If both Emerging and Confirmed pass, primary state is CONFIRMED while both booleans are preserved.

## Ranking

- Same-date cross-sectional percentiles are built from momentum, relative volume, benchmark-relative strength, and breakout-context components.
- Emerging and Confirmed ranks are assigned separately on each trading date.
- Later dates and future outcomes are not used.

## Context Handling

- NIFTY 500 benchmark relative strength supports candidacy but missing isolated benchmark context is not a mandatory rejection by itself.
- Historical sector-relative strength is not fabricated from current-only mapping. Sector context is metadata in this command.
- Extension and volatility are descriptive diagnostics, not final entry penalties.

## Pilot

- Pilot rows: 13
- Pilot validation rows: 43
- Pilot validation passed: True
- Pilot symbols: 3MINDIA, AARTIDRUGS, AAVAS, ABFRL, ADVENZYMES, BHARTIARTL, HDFCBANK, INFIBEAM, INFY, RELIANCE, SUNPHARMA, TCS
- Pilot dates: 2021-09-30, 2021-10-29, 2024-03-27, 2026-09-07

## Full Historical Generation

- Full generation completed: True
- Total evaluated rows: 597924
- Emerging rows: 109201
- Confirmed rows: 33001
- Rejected rows: 415100
- Unavailable rows: 40622
- Both-eligible rows: 30957
- Candidate count distribution: min=0, median=111.0, mean=116.1781, p90=202, p95=228, max=327
- Candidate dataset: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\research\candidates\daily\v1\momentum_candidates_v1.csv.gz
- Processing seconds: 162.387
- Storage bytes: 91000462

## Major Rejection Reasons

- FAR_FROM_RELEVANT_HIGH: 226258
- LOW_RELATIVE_VOLUME: 185608
- WEAK_BENCHMARK_RELATIVE_STRENGTH: 127650
- LOW_MULTI_DAY_MOMENTUM: 120205
- LOW_LIQUIDITY: 92510
- PRICE_BELOW_MINIMUM: 52455
- CORPORATE_ACTION_BLOCKED: 25070
- PRICE_ABOVE_HARD_LIMIT: 23427
- MISSING_LIQUIDITY_HISTORY: 18868
- INSUFFICIENT_HISTORY: 15431
- MISSING_REQUIRED_FEATURE: 3437

## Integrity And Safety

- DAILY_FEATURES_V1 unchanged: True
- Raw NSE unchanged: True
- Adjusted dataset unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.

## Known Limitations

- Membership remains PARTIAL_HISTORY and is carried as metadata/warning.
- Sector context remains unavailable for historical relative strength because upstream mapping is current-only or unavailable.
- Thresholds are baseline research defaults, not optimized parameters.
