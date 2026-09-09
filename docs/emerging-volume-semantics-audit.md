# Emerging Volume Semantics Audit

Current phase: Step 02.5 / Command 03 - Emerging volume-confirmation semantics

## Boundary

- This audit inspects current code semantics and existing candidate rows only.
- It does not use future returns, MFE, MAE, winner/loser labels, profitability optimization, entry scores, backtesting, live data, orders, migrations, or Supabase persistence.
- MOMENTUM_CANDIDATES_V1 rules, thresholds, ranking, and config hash remain unchanged.

## Semantics

- Audit version: EMERGING_VOLUME_SEMANTICS_AUDIT_V1
- Candidate version: MOMENTUM_CANDIDATES_V1
- Candidate config hash: d111957c7a24da96
- RVOL20 role: supporting_evidence
- Mandatory gate: False
- Logic: Emerging requires mandatory_gates_passed and research_eligible, (return_3d >= 0.005 OR return_5d >= 0.015), return_10d >= -0.010, up_days_ratio_10 >= 0.50, and at least 4 Emerging evidence flags. relative_volume_20d >= 1.20 adds EMERGING_RELATIVE_VOLUME as one evidence flag, but it is not directly required by passes_emerging().

## RVOL20 Distribution

- All Emerging-eligible median RVOL20: 1.1379; pct >=1.20: 46.7080%; pct <1.00: 41.7001%
- Emerging-only median RVOL20: 0.9593; pct >=1.20: 31.6004%
- Both-eligible median RVOL20: 2.4656; pct >=1.50: 100.0000%
- Primary Emerging median RVOL20: 0.9593; Primary Confirmed median RVOL20: 2.4380

## Low-RVOL Evidence

- current_day_confirmation;healthy_10d_structure;high_up_days_ratio;near_20d_high;positive_benchmark_rs_5d;strong_3d_momentum;strong_5d_momentum: 12755 (17.0766%)
- healthy_10d_structure;high_up_days_ratio;near_20d_high;positive_benchmark_rs_5d;strong_3d_momentum;strong_5d_momentum: 7992 (10.6998%)
- current_day_confirmation;healthy_10d_structure;high_up_days_ratio;positive_benchmark_rs_5d;strong_3d_momentum;strong_5d_momentum: 5839 (7.8173%)
- healthy_10d_structure;high_up_days_ratio;near_20d_high;positive_benchmark_rs_5d;strong_5d_momentum: 3684 (4.9322%)
- healthy_10d_structure;high_up_days_ratio;positive_benchmark_rs_5d;strong_5d_momentum: 3518 (4.7099%)
- healthy_10d_structure;high_up_days_ratio;positive_benchmark_rs_5d;strong_3d_momentum;strong_5d_momentum: 3516 (4.7073%)
- current_day_confirmation;healthy_10d_structure;high_up_days_ratio;near_20d_high;positive_benchmark_rs_5d;strong_5d_momentum: 3422 (4.5814%)
- above_20d_high;current_day_confirmation;healthy_10d_structure;high_up_days_ratio;near_20d_high;positive_benchmark_rs_5d;strong_3d_momentum;strong_5d_momentum: 3207 (4.2936%)
- current_day_confirmation;healthy_10d_structure;high_up_days_ratio;near_20d_high;strong_3d_momentum: 3196 (4.2788%)
- current_day_confirmation;healthy_10d_structure;high_up_days_ratio;strong_3d_momentum: 3052 (4.0861%)

## Sensitivity

- Emerging RVOL 1.20: retained=109201, removed=0 (0.0000%), retained below threshold=74693
- Emerging RVOL 1.25: retained=109143, removed=58 (0.0531%), retained below threshold=77976
- Emerging RVOL 1.30: retained=109092, removed=109 (0.0998%), retained below threshold=81215

## Counterfactual Hard Gates

- HARD_GATE_1_00: retained=50755, removed=58446, median/day=40.0, p95/day=82
- HARD_GATE_1_20: retained=34508, removed=74693, median/day=26.0, p95/day=55
- HARD_GATE_1_30: retained=27877, removed=81324, median/day=21.0, p95/day=44
- HARD_GATE_1_50: retained=16935, removed=92266, median/day=13.0, p95/day=29

## Hybrid Diagnostics

- HYBRID_RVOL20_1_20_OR_RVOL5_1_30: retained=41141, removed=68060 (37.6746% retained)
- HYBRID_RVOL20_1_20_OR_RVOL5_1_50: retained=37748, removed=71453 (34.5674% retained)

## Semantic Consistency

- Result: CONSISTENT_BUT_LOOSE
- Reason: The implementation matches secondary/supporting volume-confirmation language, but RVOL20 is loose enough that most Emerging-eligible rows sit below 1.20 and threshold changes remove very few rows.

## Regression And Safety

- Candidate dataset unchanged: True
- Feature dataset unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO bulk records were persisted to Supabase.

## Known Limitations

- This is semantic/structural analysis only; no profitability or outcome claims are made.
- RVOL5 is diagnostic in this audit; current Emerging implementation uses RVOL20 for the configured volume evidence flag.
- Candidate-state conversion uses future candidate state, not future price outcome.
