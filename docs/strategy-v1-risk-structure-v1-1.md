# Strategy V1 Risk Structure V1.1

Current phase: Step 02.9 / Command 03 - setup-specific-first stop selection

## Versioned Delta

- Previous methodology: RISK_STRUCTURE_V1 / 510f0456fe64b072
- New methodology: RISK_STRUCTURE_V1_1 / f66fbdf2fc5aecd0
- Stop selection: SETUP_SPECIFIC_FIRST_V1
- V1 remains immutable and available for comparison.
- The only intended behavioral change is validity-aware, setup-specific-first stop priority.

## Priority

1. Valid consolidation support for an active consolidation breakout.
2. Valid daily reclaim support for an active reclaim context.
3. Valid breakout invalidation for an active 20-day breakout.
4. Causal 5-day, 10-day, then 3-day swing support.
5. Other valid causal support fallbacks.

Candidates must be positive, below the assumed entry, causal, and GOOD or ACCEPTABLE under the unchanged stop-distance rules before selection.

## Unchanged Rules

- ATR stop buffer: 0.20 ATR14.
- Entry buffer: 0.10% above EOD close reference.
- Structural target first; 2R only when structural resistance is unavailable.
- Minimum/preferred reward:risk: 1.5R / 2.0R.
- Research capital: INR 100,000; maximum planned risk: 1%; whole shares; no leverage or margin.

## Structural Impact

- Rows evaluated: 26130
- Changed stop basis: 12502
- Changed stop price: 12181
- V1 ready / V1.1 ready: 9922 / 11033
- Retained / removed / introduced ready: 9557 / 365 / 1476
- Ready-set Jaccard: 0.8385

## Regression

- Stop semantics: FIX_CONFIRMED
- Target semantics: UNCHANGED_AND_VALID
- Capital semantics: UNCHANGED_AND_VALID
- Artificial 2R replacements: 0
- Planned-risk violations: 0
- Final-ready invariant violations: 0

## Boundary

- No future returns, future highs/lows, future pivots, stop/target outcomes, MFE, MAE, profitability optimization, final score, signal, backtest, paper trade, order, migration, or Supabase persistence is used.
- Daily reclaim support remains a same-day daily low reference and does not claim intraday retest precision.
- Breakout invalidations that are too tight remain invalid and fall back safely; practicality thresholds were not weakened.
