# Momentum Candidate Audit

Current phase: Step 02.5 / Command 02 - structural candidate funnel audit

## Boundary

- This audit uses candidate states and same-day features only.
- It does not use future returns, MFE, MAE, winner/loser labels, target hits, stop hits, profitability optimization, entry scores, risk/reward, position sizing, backtesting, live feeds, orders, migrations, or Supabase persistence.
- MOMENTUM_CANDIDATES_V1 thresholds remain unchanged.

## Version

- Audit methodology: MOMENTUM_CANDIDATE_AUDIT_V1
- Candidate methodology: MOMENTUM_CANDIDATES_V1
- Candidate config hash: d111957c7a24da96
- Baseline candidate hash unchanged: True
- Feature hash unchanged: True

## Baseline Distribution

- all_candidates: min=0, p10=35, p25=68, median=111.0, mean=116.1781, p75=161, p90=202, p95=228, p99=289, max=327
- emerging: min=0, p10=26, p25=51, median=86.0, mean=89.2165, p75=122, p90=152, p95=178, p99=220, max=272
- confirmed: min=0, p10=7, p25=13, median=24.0, mean=26.9616, p75=38, p90=52, p95=59, p99=76, max=107
- both_eligible: min=0, p10=6, p25=12, median=22.0, mean=25.2917, p75=36, p90=49, p95=57, p99=74, max=98

## Composition

- Emerging-only rows: 109201 (76.7929% of candidates)
- Confirmed-only rows: 2044 (1.4374% of candidates)
- Both-eligible rows: 30957 (21.7697% of candidates)
- Primary Emerging rows: 109201 (76.7929% of candidates)
- Primary Confirmed rows: 33001 (23.2071% of candidates)

## Persistence

- ANY_CANDIDATE_STREAK: count=37680, median=2.0, mean=3.7739, p90=8, p95=11, max=60
- EMERGING_STREAK: count=46998, median=2.0, mean=2.3235, p90=5, p95=6, max=29
- CONFIRMED_STREAK: count=18566, median=1.0, mean=1.7775, p90=3, p95=5, max=14

## Transitions

- emerging_to_emerging: 62203 (57.0110%)
- emerging_to_confirmed: 13336 (12.2229%)
- emerging_to_rejected: 33525 (30.7267%)
- confirmed_to_confirmed: 14435 (43.7769%)
- confirmed_to_emerging: 14548 (44.1196%)
- confirmed_to_rejected: 3980 (12.0701%)
- rejected_to_emerging: 32372 (7.8104%)
- rejected_to_confirmed: 5196 (1.2536%)

## Emerging To Confirmed

- Emerging eligible events: 140158
- Already both-eligible events: 30957
- Later-conversion pool: 109201
- within_1_sessions: 13336 / 109201 (12.2123%)
- within_2_sessions: 22167 / 109201 (20.2993%)
- within_3_sessions: 28657 / 109201 (26.2424%)
- within_5_sessions: 37846 / 109201 (34.6572%)
- within_10_sessions: 51391 / 109201 (47.0609%)

## Confirmed Persistence

- Remains Confirmed next session: 14435 (43.7769%)
- Drops to Emerging next session: 14548 (44.1196%)
- Becomes Rejected next session: 3980 (12.0701%)
- Becomes Unavailable next session: 11 (0.0334%)

## Concentration

- CUMMINSIND: 548 candidate days, longest streak 28, 45.5150% of eligible days
- MCX: 539 candidate days, longest streak 33, 44.7674% of eligible days
- TVSMOTOR: 525 candidate days, longest streak 22, 43.6047% of eligible days
- GLENMARK: 521 candidate days, longest streak 37, 43.2724% of eligible days
- HINDALCO: 517 candidate days, longest streak 19, 42.9402% of eligible days
- WELCORP: 505 candidate days, longest streak 30, 41.9435% of eligible days
- BHARATFORG: 504 candidate days, longest streak 22, 41.8605% of eligible days
- BSE: 501 candidate days, longest streak 18, 41.6113% of eligible days
- JINDALSTEL: 498 candidate days, longest streak 16, 41.3621% of eligible days
- HAL: 497 candidate days, longest streak 18, 41.2791% of eligible days

## Churn

- Candidate churn rate median=44.8980%, p90=62.7119%, p95=68.8312%.

## Evidence Distributions

- EMERGING: return_5d median=0.0303, return_20d median=0.0485, relative_volume_20d median=0.9593, distance_to_prior_20d_high_pct median=-0.0272.
- CONFIRMED: return_5d median=0.0637, return_20d median=0.1157, relative_volume_20d median=2.4380, distance_to_prior_20d_high_pct median=-0.0063.

## Sensitivity

- BASELINE: candidates=142202, emerging=109201, confirmed=33001, median/day=111.0, p95/day=228, Jaccard=1.0000, stability=STABLE
- RVOL_EMERGING_1_25: candidates=142144, emerging=109143, confirmed=33001, median/day=111.0, p95/day=228, Jaccard=0.9996, stability=STABLE
- RVOL_EMERGING_1_30: candidates=142093, emerging=109092, confirmed=33001, median/day=111.0, p95/day=228, Jaccard=0.9992, stability=STABLE
- RVOL_CONFIRMED_1_40: candidates=142483, emerging=106387, confirmed=36096, median/day=111.0, p95/day=228, Jaccard=0.9980, stability=STABLE
- RVOL_CONFIRMED_1_60: candidates=141943, emerging=111605, confirmed=30338, median/day=111.0, p95/day=227, Jaccard=0.9982, stability=STABLE
- LIQUIDITY_5CR: candidates=156303, emerging=119618, confirmed=36685, median/day=122.5, p95/day=243, Jaccard=0.9098, stability=STABLE
- LIQUIDITY_20CR: candidates=119603, emerging=92602, confirmed=27001, median/day=93.0, p95/day=195, Jaccard=0.8411, stability=MODERATELY_SENSITIVE
- MOMENTUM_LOOSER: candidates=152106, emerging=113653, confirmed=38453, median/day=121.0, p95/day=238, Jaccard=0.9349, stability=STABLE
- MOMENTUM_STRICTER: candidates=95836, emerging=73949, confirmed=21887, median/day=69.0, p95/day=169, Jaccard=0.6739, stability=HIGHLY_SENSITIVE
- HIGH_PROXIMITY_LOOSER: candidates=143363, emerging=110340, confirmed=33023, median/day=111.0, p95/day=231, Jaccard=0.9919, stability=STABLE
- HIGH_PROXIMITY_TIGHTER: candidates=141350, emerging=108364, confirmed=32986, median/day=110.0, p95/day=226, Jaccard=0.9940, stability=STABLE
- CONSERVATIVE_COMBINED: candidates=95115, emerging=74944, confirmed=20171, median/day=69.0, p95/day=167, Jaccard=0.6689, stability=HIGHLY_SENSITIVE

## Funnel Sanity

- Final structural status: HEALTHY
- Median breadth, confirmed selectivity, streak profile, and churn are within structural audit guardrails.

## Outputs

- Summary JSON: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\momentum_candidate_audit_summary.json
- Sensitivity CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\momentum_candidate_sensitivity.csv
- Transition matrix CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\momentum_candidate_transition_matrix.csv
- Streak summary CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\momentum_candidate_streak_summary.csv
- Period summary CSV: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\reports\momentum_candidate_period_summary.csv
- Bulk audit directory: C:\Users\cores\OneDrive\Desktop\Personal Project\InterSignal\data\research\audits\momentum_candidates\v1

## Known Limitations

- Membership remains partial-history/uncertain metadata inherited from upstream features.
- Sector context remains metadata only because historical sector-relative features were not point-in-time verified upstream.
- Conversion analysis is candidate-state progression only, not financial outcome analysis.
