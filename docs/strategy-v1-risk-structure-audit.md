# Strategy V1 Risk Structure Audit

Current phase: Step 02.9 / Command 02 - RISK_STRUCTURE_V1 structural audit

## Boundary

- This is a structural audit only.
- RISK_STRUCTURE_V1 was not modified.
- No future returns, future highs/lows, stop-hit labels, target-hit labels, MFE/MAE, profitability optimization, final score, signal, paper trade, live order, leverage, or Supabase write is used.

## Version

- Audit version: RISK_STRUCTURE_AUDIT_V1
- Risk version/config hash: RISK_STRUCTURE_V1 / 510f0456fe64b072

## Stop Semantics

- Baseline selected stop distribution: {'RECENT_SWING_LOW_5': {'count': 26060, 'pct': '99.7321'}, 'CONSOLIDATION_LOW': {'count': 48, 'pct': '0.1837'}, 'DAILY_RECLAIM_LOW': {'count': 15, 'pct': '0.0574'}, 'BREAKOUT_STRUCTURE': {'count': 7, 'pct': '0.0268'}}
- Stop semantics result: SETUP_SPECIFIC_STOPS_UNDERUSED
- Why 5d swing low dominates: RECENT_SWING_LOW_5 is generated for nearly every row because causal 5-session lows are almost always available. Rows carrying MOMENTUM_CONTINUATION enter that priority branch first, and that branch checks RECENT_SWING_LOW_5 before consolidation, reclaim, or breakout references. The selector stops at the first eligible basis.
- Multiple-stop availability: {'candidate_count_distribution': {'4_PLUS': {'count': 26130, 'pct': '100.0000'}}, 'valid_candidate_count_distribution': {'4_PLUS': {'count': 24044, 'pct': '92.0168'}, '3': {'count': 1561, 'pct': '5.9740'}, '2': {'count': 445, 'pct': '1.7030'}, '1': {'count': 69, 'pct': '0.2641'}, '0': {'count': 11, 'pct': '0.0421'}}, 'multiple_candidate_winners': {'RECENT_SWING_LOW_5': {'count': 26060, 'pct': '99.7321'}, 'CONSOLIDATION_LOW': {'count': 48, 'pct': '0.1837'}, 'DAILY_RECLAIM_LOW': {'count': 15, 'pct': '0.0574'}, 'BREAKOUT_STRUCTURE': {'count': 7, 'pct': '0.0268'}}, 'all_setup_specific_structures_unavailable': 0, 'all_setup_specific_structures_unavailable_pct': '0.0000'}
- Selected vs alternative: {'rows_with_multiple_candidates': 26130, 'selected_position_distribution': {'MIDDLE': {'count': 26080, 'pct': '99.8086'}, 'WIDEST': {'count': 43, 'pct': '0.1646'}, 'TIGHTEST': {'count': 7, 'pct': '0.0268'}}, 'median_selected_stop_distance_pct': Decimal('6.358500687636'), 'median_tightest_stop_distance_pct': Decimal('2.243953497157334742020954882'), 'median_widest_stop_distance_pct': Decimal('11.51121289228009453436503718'), 'median_alternative_stop_distance_pct': Decimal('5.35257264022845924475602197')}

## Target Semantics

- Target semantics result: CONSISTENT_STRUCTURAL_FIRST
- Structural available rows: 19444
- 2R fallback rows: 6686
- Fallback semantic violations: 0

## Capital Risk

- Capital risk result: HEALTHY_BUT_LOW_UTILIZATION
- Planned-risk violations: 0
- Quantity drivers: {'RISK_LIMITED': {'count': 26123, 'pct': '99.9732'}, 'CASH_LIMITED': {'count': 7, 'pct': '0.0268'}}
- Concurrency feasibility: {'median_position_notional': Decimal('12790.652875'), 'p75_position_notional': Decimal('17271.4542'), 'p90_position_notional': Decimal('22849.68686'), 'pct_position_notional_gt_25k': '7.1357', 'pct_position_notional_gt_33_3k': '2.0056', 'pct_position_notional_gt_50k': '0.2419'}

## Decision

- Structural stability: STABLE
- Baseline decision: B. remain provisional pending a specific semantic fix
- Recommended next action: Create a separate methodology-change command to decide whether multi-flag rows should prioritize setup-specific invalidation before momentum-continuation swing lows.

## Regression

- DAILY_FEATURES_V1 unchanged: True
- MOMENTUM_CANDIDATES_V1 unchanged: True
- DAILY_SETUP_EVALUATION_V1 unchanged: True
- MARKET_REGIME_V1 unchanged: True
- ENTRY_EVALUATION_V1 unchanged: True
- RISK_STRUCTURE_V1 unchanged: True
