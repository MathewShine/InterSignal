# Daily Feature Engine

Current phase: Step 02.4 / Command 02 - benchmark and sector relative-strength context

## Status

- Feature methodology: DAILY_FEATURES_V1
- Benchmark context version: BENCHMARK_CONTEXT_V1
- Sector context version: SECTOR_CONTEXT_V1
- Full generation completed: True
- Ready for review: True
- Feature dataset: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\research\features\daily\v1\daily_features_v1.csv.gz

## Architecture

- Inputs: adjusted NSE research daily prices, point-in-time Nifty 500 membership, corporate-action research eligibility, and official NSE trading sessions.
- Output: DAILY_EOD feature snapshots that are available only after the close of the feature date and usable as NEXT_SESSION_DECISION_INPUT.
- No strategy scoring, trade signals, outcome labels, order logic, remote migrations, or Supabase feature writes are performed.

## Methodology

- Adjustment methodology: PRICE_ADJUSTED_STRUCTURAL_V1
- Exclusion policy: CORPORATE_ACTION_EXCLUSIONS_V1
- Traded value: ADJUSTED_CLOSE_X_ADJUSTED_VOLUME_PROXY
- ATR: SIMPLE_ROLLING_MEAN
- Return volatility: SAMPLE_STDEV_NON_ANNUALIZED
- Rolling windows use trading sessions, not calendar days.
- Relative volume denominators use prior sessions only and exclude the current date.
- Prior highs/lows exclude the current date; inclusive rolling highs/lows are stored separately.
- Benchmark and sector index closes are official DAILY_EOD context and are not treated as intraday inputs.
- DAILY_FEATURES_V1 is retained; benchmark_context_version and sector_context_version record this Command 02 enhancement.

## Feature Groups

- returns: return_1d, return_2d, return_3d, return_5d, return_10d, return_20d
- momentum: momentum_3d, momentum_5d, momentum_10d, momentum_20d, positive_days_5, positive_days_10, positive_days_20, up_days_ratio_5, up_days_ratio_10, up_days_ratio_20
- liquidity: daily_traded_value, median_traded_value_5d, median_traded_value_20d, avg_volume_5d, avg_volume_20d
- relative_volume: relative_volume_5d, relative_volume_20d
- volatility: true_range, atr_5, atr_14, atr_20, atr_percent_14, return_volatility_5d, return_volatility_20d
- levels: high_5d, high_10d, high_20d, high_52w, low_5d, low_10d, low_20d, low_52w, prior_high_5d, prior_high_20d, prior_high_52w, prior_low_5d, prior_low_20d, distance_to_prior_5d_high_pct, distance_to_prior_20d_high_pct, distance_to_prior_52w_high_pct
- trend: sma_5, sma_10, sma_20, sma_50, sma_200, distance_from_sma_20_pct, distance_from_sma_50_pct, distance_from_sma_200_pct
- candle: daily_range_pct, body_pct, upper_wick_pct, lower_wick_pct, close_location_value, gap_open_pct
- consolidation: above_prior_5d_high, above_prior_20d_high, above_prior_52w_high, intraday_high_above_prior_20d_high, range_width_5d_pct, range_width_10d_pct, range_width_20d_pct, atr_contraction_ratio
- benchmark: benchmark_symbol, primary_benchmark_id, secondary_benchmark_id, benchmark_return_1d, benchmark_return_2d, benchmark_return_3d, benchmark_return_5d, benchmark_return_10d, benchmark_return_20d, relative_return_1d_vs_nifty500, relative_return_3d_vs_nifty500, relative_return_5d_vs_nifty500, relative_return_10d_vs_nifty500, relative_return_20d_vs_nifty500, nifty50_return_5d, nifty50_return_20d, relative_return_5d_vs_nifty50, relative_return_20d_vs_nifty50, relative_return_5d_vs_benchmark, relative_return_20d_vs_benchmark
- sector: sector_index_id, sector_index_name, sector_mapping_status, sector_mapping_confidence, sector_mapping_source, sector_return_1d, sector_return_3d, sector_return_5d, sector_return_10d, sector_return_20d, sector_index_return_1d, sector_index_return_5d, sector_index_return_20d, relative_return_1d_vs_sector, relative_return_3d_vs_sector, relative_return_5d_vs_sector, relative_return_10d_vs_sector, relative_return_20d_vs_sector, sector_above_sma20, sector_momentum_available

## Membership And Eligibility

- Membership status: PARTIAL_HISTORY
- Membership metadata is retained on every feature row.
- Corporate-action eligibility: LOOKBACK_AWARE_ELIGIBILITY_APPLIED
- Features crossing an exclusion or continuity-break interval are null with explicit reason codes.

## Benchmark And Sector

- Benchmark status: AVAILABLE
- Primary benchmark: NIFTY_500
- Secondary benchmark: NIFTY_50
- Benchmark reason: 
- Sector status: LIMITED
- Sector reason: Current-only sector metadata is retained but not projected backward.
- Sector mapping policy: Only POINT_IN_TIME_VERIFIED and INFERRED_WITH_EVIDENCE mappings are eligible for sector-relative features.

## Pilot

- Symbols requested: RELIANCE, TCS, HDFCBANK, INFY, SUNPHARMA, 360ONE, 3MINDIA, INFIBEAM, AADHARHFC
- Symbols generated: 360ONE, 3MINDIA, AADHARHFC, HDFCBANK, INFIBEAM, INFY, RELIANCE, SUNPHARMA, TCS
- Pilot rows: 9341
- Manual validation rows: 12
- Manual validation passed: True

## Full Generation

- Total potential Nifty 500 symbol-date observations: 597924
- Generated feature rows: 597924
- READY rows: 395617
- Rows with partial/null features: 597924
- Corporate-action-blocked rows: 25070
- Insufficient-history rows: 167457
- Membership-uncertain rows: 597924
- Benchmark-relative rows: 569087 (95.1771%)
- Sector-relative rows: 0 (0.0000%)
- 5-session relative strength usable: 98.6227%
- 20-session relative strength usable: 95.1771%
- 5-session usable: 99.1082%
- 20-session usable: 96.8444%
- 60-session usable: 92.4183%
- 200-session usable: 72.3435%
- Storage bytes: 237415127
- Processing seconds: 759.227

## Integrity And Safety

- Raw NSE unchanged: True
- Adjusted dataset unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.

## Known Limitations

- Sector index history is available where official NSE publishes it, but point-in-time stock-sector mapping remains limited.
- CURRENT_ONLY sector mappings are retained for diagnostics and deliberately produce null sector-relative fields.
- Historical Nifty 500 membership remains PARTIAL_HISTORY and must be considered by future backtests.
- EMA features are deferred; SMA descriptors are implemented for Command 01.
