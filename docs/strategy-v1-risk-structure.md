# Strategy V1 Risk Structure

## Step Status

- Step 02.9 - Risk Structure Foundation: **COMPLETE**
- Current forward baseline: `RISK_STRUCTURE_V1_1`
- Supersedes for forward use: `RISK_STRUCTURE_V1`
- Promotion reason: setup-specific invalidation-priority correction
- Historical V1 remains preserved for reproducibility and audit comparison.
- Methodology delta: [Strategy V1 Risk Structure V1.1](strategy-v1-risk-structure-v1-1.md)
- Structural audit: [Risk Structure Audit](strategy-v1-risk-structure-audit.md)
- Promotion record: [Risk Structure Baseline Promotion](risk-structure-baseline-promotion.md)

## Current Forward Baseline

- Research capital: INR 100,000
- Maximum risk per trade: 1.00%
- Minimum/preferred reward:risk: 1.5R / 2.0R
- Stop buffer: 0.20 ATR14
- Entry reference buffer: 0.10%
- Instrument and sizing: whole-share NSE cash equity, no leverage or margin
- Final strategy score: `NOT_IMPLEMENTED`
- Trade signal: `NOT_GENERATED`

## Historical V1 Foundation

Original phase: Step 02.9 / Command 01 - Stop, target, reward:risk, and position-risk foundation

## Boundary

- RISK_STRUCTURE_V1 evaluates only deterministic structure for rows handed off by ENTRY_EVALUATION_V1.
- The layer is DAILY_EOD and produces NEXT_SESSION_RISK_CONTEXT.
- Entry execution price remains unknown; the engine uses EOD close plus a deterministic long buffer.
- No final score, buy/sell signal, backtest, paper trade, live order, short, leverage, margin, remote migration, or Supabase write is implemented.

## Version

- Risk methodology/config hash: RISK_STRUCTURE_V1 / 510f0456fe64b072
- Entry: ENTRY_EVALUATION_V1 / 5a8c1c82e9b36be5
- Setup: DAILY_SETUP_EVALUATION_V1 / 1dcc8d7790116e56
- Regime: MARKET_REGIME_V1 / 47ed769ec4115481

## Methodology

- Capital baseline is INR 100,000 with maximum 1.00% risk per trade.
- Stops are selected from technical invalidation levels first, then buffered by 0.20 ATR.
- Causal swing lows use current session T and prior sessions only; no future pivot confirmation is used.
- Structural targets are used only when available. Otherwise the default research reference is 2R.
- Minimum reward:risk is 1.5R and preferred reward:risk is 2.0R.
- Quantity is the lower of risk-budget quantity and cash-affordability quantity, whole shares only.

## Results

- Full generation completed: True
- Total rows risk evaluated: 26130
- Valid stops: 24965 (95.5415%)
- R:R >= 1.5: 10935 (41.8485%)
- R:R >= 2.0: 10137 (38.7945%)
- Capital valid: 26123 (99.9732%)
- Ready for final scoring: 9922 (37.9717%)
- Rejected by risk layer: 13072

## Integrity

- DAILY_FEATURES_V1 unchanged: True
- MOMENTUM_CANDIDATES_V1 unchanged: True
- DAILY_SETUP_EVALUATION_V1 unchanged: True
- MARKET_REGIME_V1 unchanged: True
- ENTRY_EVALUATION_V1 unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO records were persisted to Supabase.

## Known Limitations

- Structural resistance is limited to upstream same-day historical level references.
- Target, stop, and position values are research references, not executable order instructions.
- No portfolio allocator is implemented despite a preferred maximum concurrent position count.
- No slippage, brokerage, gap-open, or intraday fill model is implemented.
