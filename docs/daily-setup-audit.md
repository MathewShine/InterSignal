# Daily Setup Audit

Current phase: Step 02.6 / Command 02 - setup funnel, candle semantics, persistence, and threshold sensitivity

## Boundary

- This is a structural audit of DAILY_SETUP_EVALUATION_V1 only.
- No future returns, MFE, MAE, winner/loser labels, profitability, target-hit, stop-hit, backtesting, entry scoring, market-regime scoring, risk/reward, orders, migrations, or Supabase writes are used.
- The baseline setup, candidate, and feature datasets remain unchanged.

## Version

- Audit version: DAILY_SETUP_AUDIT_V1
- Setup version/config hash: DAILY_SETUP_EVALUATION_V1 / 1dcc8d7790116e56
- Candidate version/config hash: MOMENTUM_CANDIDATES_V1 / d111957c7a24da96
- Feature version: DAILY_FEATURES_V1

## Funnel

- Candidate rows: 142202
- Setup eligible: 29748 (20.9195%)
- Setup rejected: 112454
- Quality counts: {'POOR': 67165, 'VALID': 19744, 'WATCH': 45289, 'STRONG': 10004}
- Emerging pass rate: 20.4146%
- Confirmed pass rate: 22.5902%
- Per-day setup eligible: min=0, p10=4, p25=11, median=22.0, mean=24.7076, p75=36, p90=48, p95=57, p99=80, max=108

## Candle Quality

- POOR candle rows: 93646 (65.8542%)
- Top weaknesses: {'WEAK_CLOSE_LOCATION': {'count': 93431, 'pct': '99.7704'}, 'MULTIPLE_CANDLE_WEAKNESSES': {'count': 33054, 'pct': '35.2968'}, 'SMALL_BODY': {'count': 24367, 'pct': '26.0203'}, 'LARGE_UPPER_WICK': {'count': 8497, 'pct': '9.0735'}, 'GAP_FADE': {'count': 3102, 'pct': '3.3125'}}
- Top combinations: [{'combination': 'WEAK_CLOSE_LOCATION', 'count': 60377, 'pct': '64.4737'}, {'combination': 'MULTIPLE_CANDLE_WEAKNESSES;SMALL_BODY;WEAK_CLOSE_LOCATION', 'count': 22438, 'pct': '23.9604'}, {'combination': 'LARGE_UPPER_WICK;MULTIPLE_CANDLE_WEAKNESSES;WEAK_CLOSE_LOCATION', 'count': 6004, 'pct': '6.4114'}, {'combination': 'GAP_FADE;MULTIPLE_CANDLE_WEAKNESSES;WEAK_CLOSE_LOCATION', 'count': 2031, 'pct': '2.1688'}, {'combination': 'LARGE_UPPER_WICK;MULTIPLE_CANDLE_WEAKNESSES;SMALL_BODY;WEAK_CLOSE_LOCATION', 'count': 1510, 'pct': '1.6125'}]

## Persistence And Sensitivity

- Structural stability: STABLE (STABLE <=10% max setup-count shift and Jaccard >=0.85; MODERATELY_SENSITIVE <=30% and Jaccard >=0.65; otherwise HIGHLY_SENSITIVE.)
- Funnel sanity: HEALTHY_BUT_CANDLE_STRICT. The pass rate is structurally selective and candle quality is strict, but loosening candle thresholds does not radically reshape the setup population.
- Highest-density dates are in C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\research\audits\daily_setups\v1\daily_setup_density.csv.gz
- Sensitivity scenarios are in C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\daily_setup_sensitivity.csv

## Integrity And Safety

- DAILY_SETUP_EVALUATION_V1 unchanged: True
- MOMENTUM_CANDIDATES_V1 unchanged: True
- DAILY_FEATURES_V1 unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.

## Known Limitations

- Persistence and transitions describe setup-state evolution only, not price outcomes.
- Sensitivity scenarios are small structural perturbations, not optimized parameters.
- Daily reclaim and false-breakout warnings remain daily-EOD diagnostics, not intraday proof.
