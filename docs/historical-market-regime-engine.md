# Historical Market Regime Engine

Current phase: Step 02.7 / Command 01 - historical Market Regime Engine foundation

## Boundary

- This is MARKET_REGIME_V1, a DAILY_EOD_REGIME used as NEXT_SESSION_CONTEXT.
- It reports broad market context only; it does not decide stock entries.
- No future returns, MFE, MAE, winners/losers, backtesting, entry scoring, risk/reward, stops, targets, position sizing, orders, migrations, or Supabase writes are used.
- Missing Global/GIFT, India VIX, and intraday evidence is marked unavailable, not neutral.

## Version

- Regime version/config hash: MARKET_REGIME_V1 / 47ed769ec4115481
- Classification threshold: bullish >= 30, bearish <= -30
- Minimum available weight: 60%

## Component Availability

- NIFTY_TREND: USABLE, coverage 99.5915%, source=data/reference/nse/indices/normalized/benchmark_daily.csv, limitation=
- NIFTY500_BREADTH: USABLE, coverage 99.9183%, source=data/research/features/daily/v1/daily_features_v1.csv.gz, limitation=Membership reconstruction is PARTIAL_HISTORY; current constituents are not projected backward.
- SECTOR_INDEX_PARTICIPATION: USABLE, coverage 99.9183%, source=data/reference/nse/indices/normalized/sector_index_daily.csv, limitation=Uses official sector index performance only; not stock-level sector breadth.
- INDIA_VIX: UNAVAILABLE, coverage 0.0000%, source=data/reference/nse/indices/normalized/india_vix_daily.csv, limitation=Official local India VIX history is not present; no substitute was fabricated.
- GLOBAL_GIFT: UNAVAILABLE, coverage 0.0000%, source=future GlobalMarketContextProvider, limitation=No reliable local historical Global/GIFT dataset exists yet.
- INTRADAY_CONFIRMATION: UNAVAILABLE, coverage 0.0000%, source=future intraday regime provider, limitation=This command is DAILY_EOD; intraday confirmation is reserved for a future live engine.

## Generation

- Historical coverage: 2021-09-30 to 2026-09-07
- Total regime rows: 1224
- Full generation completed: True
- Regime counts: {'UNAVAILABLE': {'count': 33, 'pct': '2.6961'}, 'BEARISH': {'count': 379, 'pct': '30.9641'}, 'NEUTRAL': {'count': 234, 'pct': '19.1176'}, 'BULLISH': {'count': 578, 'pct': '47.2222'}}
- Confidence counts: {'LOW': {'count': 13, 'pct': '1.0621'}, 'MEDIUM': {'count': 1211, 'pct': '98.9379'}}
- Score distribution: {'usable_rows': 1224, 'min': '-100.0000', 'p10': '-81.5385', 'p25': '-46.1538', 'median': '27.6923', 'mean': '13.0132', 'p75': '72.3077', 'p90': '90.7692', 'p95': '100.0000', 'max': '100.0000'}
- Available-weight distribution: {'usable_rows': 1224, 'min': '15.0000', 'p10': '60.0000', 'p25': '65.0000', 'median': '65.0000', 'mean': '63.9706', 'p75': '65.0000', 'p90': '65.0000', 'p95': '65.0000', 'max': '65.0000'}

## Persistence

- Streak summary: {'BULLISH': {'streak_count': 98, 'one_session': 35, 'two_sessions': 18, 'three_to_five': 14, 'six_to_ten': 16, 'over_ten': 15, 'median': 2.0, 'mean': 5.898, 'p90': 13, 'p95': 17, 'max': 54}, 'NEUTRAL': {'streak_count': 144, 'one_session': 96, 'two_sessions': 29, 'three_to_five': 17, 'six_to_ten': 1, 'over_ten': 1, 'median': 1.0, 'mean': 1.625, 'p90': 3, 'p95': 4, 'max': 14}, 'BEARISH': {'streak_count': 82, 'one_session': 37, 'two_sessions': 11, 'three_to_five': 8, 'six_to_ten': 18, 'over_ten': 8, 'median': 2.0, 'mean': 4.622, 'p90': 10, 'p95': 14, 'max': 24}}
- Top transitions: [{'from_state': 'BULLISH', 'to_state': 'BULLISH', 'count': 480}, {'from_state': 'BEARISH', 'to_state': 'BEARISH', 'count': 297}, {'from_state': 'NEUTRAL', 'to_state': 'NEUTRAL', 'count': 90}, {'from_state': 'NEUTRAL', 'to_state': 'BULLISH', 'count': 81}, {'from_state': 'BULLISH', 'to_state': 'NEUTRAL', 'count': 79}, {'from_state': 'BEARISH', 'to_state': 'NEUTRAL', 'count': 65}, {'from_state': 'NEUTRAL', 'to_state': 'BEARISH', 'count': 63}, {'from_state': 'BULLISH', 'to_state': 'BEARISH', 'count': 18}, {'from_state': 'BEARISH', 'to_state': 'BULLISH', 'count': 16}]
- Score continuity: {'usable_rows': 1223, 'min': '0.0000', 'p10': '0.0000', 'p25': '9.2308', 'median': '21.5385', 'mean': '26.7554', 'p75': '40.0000', 'p90': '60.0000', 'p95': '75.0000', 'max': '153.8462', 'direct_bullish_bearish_flips': 34, 'pathological_regime_flipping_detected': True}

## Integrity And Safety

- DAILY_FEATURES_V1 unchanged: True
- MOMENTUM_CANDIDATES_V1 unchanged: True
- DAILY_SETUP_EVALUATION_V1 unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.

## Known Limitations

- Historical Nifty 500 membership remains PARTIAL_HISTORY.
- Sector participation is official sector-index participation, not point-in-time stock-sector breadth.
- India VIX, Global/GIFT, and intraday confirmation are unavailable in this command and reduce confidence/coverage.
- No outcome or profitability interpretation is made from regime states.
