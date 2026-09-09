# Market Regime Stability Audit

Current phase: Step 02.7 / Command 02 - audit historical regime stability

## Boundary

- This is MARKET_REGIME_AUDIT_V1, a structural audit of MARKET_REGIME_V1.
- MARKET_REGIME_V1 is not changed by this audit.
- No future outcomes, future returns, candidate/setup outcomes, MFE, MAE, winners/losers, stops, targets, backtesting, entry scoring, trading execution, migrations, or Supabase writes are used.

## Version

- Audit version: MARKET_REGIME_AUDIT_V1
- Regime version/config hash: MARKET_REGIME_V1 / 47ed769ec4115481
- Baseline hash unchanged: True

## Direct Flips

- Direct Bullish/Bearish flips: 34
- Dominant drivers: {'MULTI_COMPONENT': {'count': 33, 'pct': '97.0588'}, 'TREND_DOMINANT': {'count': 1, 'pct': '2.9412'}}
- Structural classes: {'MODERATE_MULTI_COMPONENT_REVERSAL': {'count': 11, 'pct': '32.3529'}, 'BORDERLINE_THRESHOLD_FLIP': {'count': 11, 'pct': '32.3529'}, 'INCONCLUSIVE': {'count': 6, 'pct': '17.6471'}, 'STRONG_MULTI_COMPONENT_REVERSAL': {'count': 5, 'pct': '14.7059'}, 'SINGLE_COMPONENT_BUCKET_JUMP': {'count': 1, 'pct': '2.9412'}}
- Flip quality result: MOSTLY_REASONABLE_WITH_SOME_BORDERLINE_FLIPS

## Stability

- Score-change distribution: {'usable_rows': 1223, 'min': '0.0000', 'p10': '0.0000', 'p25': '9.2308', 'median': '21.5385', 'mean': '26.7554', 'p75': '40.0000', 'p90': '60.0000', 'p95': '75.0000', 'p99': '104.6154', 'max': '153.8462'}
- Boundary analysis: [{'band': 'PLUS_25_TO_35', 'range': '25.0000 to 35.0000', 'row_count': 60, 'state_distribution': {'BULLISH': {'count': 31, 'pct': '51.6667'}, 'NEUTRAL': {'count': 28, 'pct': '46.6667'}, 'UNAVAILABLE': {'count': 1, 'pct': '1.6667'}}, 'next_transition_distribution': {'BULLISH->BULLISH': {'count': 18, 'pct': '30.0000'}, 'NEUTRAL->BULLISH': {'count': 17, 'pct': '28.3333'}, 'BULLISH->NEUTRAL': {'count': 12, 'pct': '20.0000'}, 'NEUTRAL->NEUTRAL': {'count': 6, 'pct': '10.0000'}, 'NEUTRAL->BEARISH': {'count': 5, 'pct': '8.3333'}, 'UNAVAILABLE->UNAVAILABLE': {'count': 1, 'pct': '1.6667'}, 'BULLISH->BEARISH': {'count': 1, 'pct': '1.6667'}}, 'median_abs_next_score_change': '32.3077', 'direct_flip_count': 1, 'direct_flip_frequency_pct': '1.6667'}, {'band': 'PLUS_20_TO_40', 'range': '20.0000 to 40.0000', 'row_count': 82, 'state_distribution': {'NEUTRAL': {'count': 44, 'pct': '53.6585'}, 'BULLISH': {'count': 34, 'pct': '41.4634'}, 'UNAVAILABLE': {'count': 4, 'pct': '4.8780'}}, 'next_transition_distribution': {'NEUTRAL->BULLISH': {'count': 25, 'pct': '30.4878'}, 'BULLISH->BULLISH': {'count': 21, 'pct': '25.6098'}, 'NEUTRAL->NEUTRAL': {'count': 12, 'pct': '14.6341'}, 'BULLISH->NEUTRAL': {'count': 12, 'pct': '14.6341'}, 'NEUTRAL->BEARISH': {'count': 7, 'pct': '8.5366'}, 'UNAVAILABLE->UNAVAILABLE': {'count': 4, 'pct': '4.8780'}, 'BULLISH->BEARISH': {'count': 1, 'pct': '1.2195'}}, 'median_abs_next_score_change': '28.8462', 'direct_flip_count': 1, 'direct_flip_frequency_pct': '1.2195'}, {'band': 'MINUS_35_TO_25', 'range': '-35.0000 to -25.0000', 'row_count': 62, 'state_distribution': {'BEARISH': {'count': 33, 'pct': '53.2258'}, 'NEUTRAL': {'count': 26, 'pct': '41.9355'}, 'UNAVAILABLE': {'count': 3, 'pct': '4.8387'}}, 'next_transition_distribution': {'BEARISH->NEUTRAL': {'count': 15, 'pct': '24.1935'}, 'NEUTRAL->NEUTRAL': {'count': 13, 'pct': '20.9677'}, 'BEARISH->BEARISH': {'count': 13, 'pct': '20.9677'}, 'NEUTRAL->BEARISH': {'count': 10, 'pct': '16.1290'}, 'BEARISH->BULLISH': {'count': 5, 'pct': '8.0645'}, 'UNAVAILABLE->UNAVAILABLE': {'count': 3, 'pct': '4.8387'}, 'NEUTRAL->BULLISH': {'count': 3, 'pct': '4.8387'}}, 'median_abs_next_score_change': '30.7692', 'direct_flip_count': 5, 'direct_flip_frequency_pct': '8.0645'}, {'band': 'MINUS_40_TO_20', 'range': '-40.0000 to -20.0000', 'row_count': 75, 'state_distribution': {'NEUTRAL': {'count': 34, 'pct': '45.3333'}, 'BEARISH': {'count': 34, 'pct': '45.3333'}, 'UNAVAILABLE': {'count': 7, 'pct': '9.3333'}}, 'next_transition_distribution': {'NEUTRAL->BEARISH': {'count': 15, 'pct': '20.0000'}, 'BEARISH->NEUTRAL': {'count': 15, 'pct': '20.0000'}, 'NEUTRAL->NEUTRAL': {'count': 14, 'pct': '18.6667'}, 'BEARISH->BEARISH': {'count': 13, 'pct': '17.3333'}, 'UNAVAILABLE->UNAVAILABLE': {'count': 7, 'pct': '9.3333'}, 'BEARISH->BULLISH': {'count': 6, 'pct': '8.0000'}, 'NEUTRAL->BULLISH': {'count': 5, 'pct': '6.6667'}}, 'median_abs_next_score_change': '36.9231', 'direct_flip_count': 6, 'direct_flip_frequency_pct': '8.0000'}]
- One-day states: {'BULLISH': {'isolated_one_day_count': 35, 'dates': ['2022-04-13', '2022-04-21', '2022-04-26', '2022-09-20', '2022-10-20', '2022-12-08', '2023-03-06', '2023-09-27', '2023-09-29', '2023-10-06', '2024-01-24', '2024-01-29', '2024-02-27', '2024-03-01', '2024-06-03', '2024-07-22', '2024-07-24', '2024-09-10', '2025-01-02', '2025-02-05', '2025-05-07', '2025-06-16', '2025-06-20', '2025-07-23', '2025-08-19', '2025-08-21', '2025-11-10', '2025-11-26', '2026-02-26', '2026-04-08', '2026-04-10', '2026-04-27', '2026-04-29', '2026-07-29', '2026-08-11']}, 'BEARISH': {'isolated_one_day_count': 37, 'dates': ['2021-12-30', '2022-01-31', '2022-03-15', '2022-03-25', '2022-04-19', '2022-04-25', '2022-04-27', '2022-07-05', '2022-09-16', '2022-12-16', '2023-01-04', '2023-01-20', '2023-02-13', '2023-02-15', '2023-08-14', '2023-08-18', '2023-08-31', '2023-09-28', '2023-10-04', '2023-10-09', '2023-10-18', '2024-01-23', '2024-02-12', '2024-04-18', '2024-05-07', '2024-06-04', '2024-08-08', '2024-08-14', '2024-10-31', '2025-02-06', '2025-04-09', '2025-06-13', '2025-06-18', '2026-05-12', '2026-05-21', '2026-07-08', '2026-08-24']}}
- Stability result: STABLE_WITH_SOME_FAST_FLIPS

## Normalization And Confidence

- Normalization result: NO_CLASSIFICATION_ARTIFACTS
- Multiplier distribution: {'usable_rows': 1224, 'min': '1.5385', 'p10': '1.5385', 'p25': '1.5385', 'median': '1.5385', 'mean': '1.5722', 'p75': '1.5385', 'p90': '1.6667', 'p95': '1.6667', 'p99': '2.0000', 'max': '6.6667'}
- Confidence ceiling: {'theoretical_max': '70.5000', 'max_available_weight_observed': '65.0000', 'max_weighted_component_coverage_observed': '65.0000', 'minimum_partial_membership_penalty_observed': '0.0000', 'observed_p50': '69.0654', 'observed_p90': '70.1539', 'observed_p95': '70.4800', 'observed_max': '70.5000', 'high_mathematically_unreachable': True}
- Confidence result: CONSISTENT_BUT_CAPPED_BY_DATA_AVAILABILITY

## Scenarios

- BASELINE: direct flips=34, one-day Bullish=35, one-day Bearish=37, agreement=100.0000%
- DEADBAND_35: direct flips=20, one-day Bullish=37, one-day Bearish=28, agreement=95.1797%
- DEADBAND_40: direct flips=17, one-day Bullish=38, one-day Bearish=26, agreement=94.6895%
- HYSTERESIS_30_20: direct flips=39, one-day Bullish=24, one-day Bearish=31, agreement=95.7516%
- HYSTERESIS_35_20: direct flips=24, one-day Bullish=23, one-day Bearish=21, agreement=93.3007%
- PERSISTENCE_2: direct flips=0, one-day Bullish=33, one-day Bearish=27, agreement=97.5490%
- PERSISTENCE_3: direct flips=0, one-day Bullish=30, one-day Bearish=26, agreement=96.4052%
- SCORE_MEAN_2: direct flips=2, one-day Bullish=13, one-day Bearish=10, agreement=86.1111%
- SCORE_MEAN_3: direct flips=0, one-day Bullish=9, one-day Bearish=3, agreement=80.2288%

## Outputs

- Summary JSON: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\market_regime_audit_summary.json
- Direct flips CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\market_regime_direct_flips.csv
- Flip drivers CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\market_regime_flip_drivers.csv
- Score changes CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\market_regime_score_changes.csv
- Component transitions CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\market_regime_component_transitions.csv
- Confidence audit CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\market_regime_confidence_audit.csv
- Sensitivity CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\market_regime_sensitivity.csv
- Bulk audit directory: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\research\audits\market_regime\v1

## Decision

- Baseline decision: frozen unchanged
- Any methodology change would require a separate command.

## Known Limitations

- India VIX, Global/GIFT, and intraday confirmation remain unavailable in the historical baseline.
- Nifty 500 breadth inherits partial-history membership reconstruction.
- Counterfactual scenarios are structural diagnostics only, not adopted methodology.
