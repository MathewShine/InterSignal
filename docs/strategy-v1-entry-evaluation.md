# Strategy V1 Entry Evaluation

Current phase: Step 02.8 / Command 01 - Strategy V1 entry-evaluation foundation

## Boundary

- ENTRY_EVALUATION_V1 combines same-day Momentum Candidate, Daily Setup Evaluation, and Market Regime rows.
- The output is NEXT_SESSION_ENTRY_RESEARCH and remains DAILY_EOD only.
- READY_FOR_RISK_EVALUATION does not mean trade.
- EXCEPTIONAL_LONG_REVIEW does not mean high conviction or trade approval.
- No final 0-100 entry score, stop, target, risk/reward, position sizing, BUY/SELL signal, backtest, paper trade, order, migration, or Supabase write is implemented.

## Version

- Entry methodology/config hash: ENTRY_EVALUATION_V1 / 5a8c1c82e9b36be5
- Candidate: MOMENTUM_CANDIDATES_V1 / d111957c7a24da96
- Setup: DAILY_SETUP_EVALUATION_V1 / 1dcc8d7790116e56
- Regime: MARKET_REGIME_V1 / 47ed769ec4115481

## Architecture

- Candidate Engine: which stocks deserve attention.
- Setup Engine: whether the technical structure is credible.
- Market Regime Engine: broad market environment.
- Entry Evaluation Engine: whether current context may proceed to later risk evaluation.
- Later Risk and Signal Engines are explicitly not implemented here.

## Gates

- Data/research safety preserves row availability, corporate-action/research blocking, and membership uncertainty metadata.
- Candidate eligibility allows only EMERGING or CONFIRMED rows.
- Setup eligibility requires setup_eligible plus VALID or STRONG for normal readiness; WATCH stays watch-only and POOR blocks.
- Bullish regime permits normal long evaluation.
- Neutral regime applies stricter confirmation.
- Bearish regime blocks normal swing longs except rare exceptional-long review rows.
- Regime unavailable is conservative and never treated as Neutral.

## Results

- Full generation completed: True
- Total evaluated rows: 142202
- Readiness counts: {'NOT_READY': {'count': 72159, 'pct': '50.7440'}, 'WATCH': {'count': 43913, 'pct': '30.8807'}, 'CONDITIONALLY_READY': {'count': 3136, 'pct': '2.2053'}, 'READY_FOR_RISK_EVALUATION': {'count': 22670, 'pct': '15.9421'}, 'EXCEPTIONAL_LONG_REVIEW': {'count': 324, 'pct': '0.2278'}}
- Candidate to setup conversion: 20.9195%
- Setup to ready/conditional conversion: 87.8378%
- Candidate to ready/conditional conversion: 18.3753%
- Daily ready-for-risk distribution: {'min': 0, 'p10': 0, 'p25': 1, 'median': 11.0, 'mean': 19.098, 'p75': 34, 'p90': 47, 'p95': 57, 'p99': 80, 'max': 108}

## Exceptional Longs

- Bearish candidate rows: 22500
- Bearish setup-eligible rows: 3771
- Exceptional-long candidates: 324
- Exceptional-long review-ready rows: 324 (8.5919% of bearish setup rows)

## Integrity

- DAILY_FEATURES_V1 unchanged: True
- MOMENTUM_CANDIDATES_V1 unchanged: True
- DAILY_SETUP_EVALUATION_V1 unchanged: True
- MARKET_REGIME_V1 unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO records were persisted to Supabase.

## Known Limitations

- Stock-specific historical sector RS is unavailable and not used.
- Catalyst/news is unavailable and not fabricated.
- Risk/reward is not evaluated, so no trade can be approved from this layer.
- The rank is a same-day structural context ordering, not the final Strategy V1 0-100 score.
