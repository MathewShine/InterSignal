# Strategy V1 Historical Outcomes

STATUS: ACTIVE_HISTORICAL_OUTCOME_BASELINE

Step 02.11 — Historical Outcome Labeling: COMPLETE

## Frozen baseline

- Version: STRATEGY_OUTCOME_V1
- Profile: SWING_DAILY_OUTCOME_V1
- Config hash: `2ea683a8f8b5b041`
- Dataset: `data/research/outcomes/swing/daily/v1/strategy_outcomes_v1.csv.gz`
- Dataset SHA-256: `5c4ec28cb54f6567b04c3444a3f1d0dde5f03ac3c6518743268f9e4fda100538`
- Score dependency: STRATEGY_SCORE_V1 / SWING_DAILY_EOD_V1 / `e257c76b90e25cb7`
- Risk dependency: RISK_STRUCTURE_V1_1 / `f66fbdf2fc5aecd0`

The Command 02 structural audit is documented in [Strategy V1 Historical Outcomes Audit](strategy-v1-historical-outcomes-audit.md). Its identity is STRATEGY_OUTCOME_AUDIT_V1, its overall result is STABLE_WITH_REVIEW_NOTES, and its approved decision is A_FREEZE_UNCHANGED. Independent completeness verification passed 105/105 checks.

## Locked methodology

- Decision time is EOD T. The hypothetical entry is the next valid session open, never the T close.
- Entry is revalidated for forward safety, open above the frozen stop, effective reward:risk of at least 1.5, quantity of at least one, valid capital/risk, and no leverage.
- Stop and target remain frozen from RISK_STRUCTURE_V1_1.
- The canonical horizon remains four trading sessions.
- If stop and target first appear in the same daily bar, the outcome is AMBIGUOUS; no intraday ordering is inferred.
- Canonical states are TARGET_FIRST, STOP_FIRST, NEITHER_WITHIN_HORIZON, AMBIGUOUS, INVALID_ENTRY, and INSUFFICIENT_FORWARD_DATA.
- Right-censoring remains separate from FORWARD_DATA_UNSAFE. An unavailable horizon is not treated as failure.
- Transaction costs and slippage are NOT_MODELED.

## Future-data boundary

The outcome layer may use future data for evaluation. Frozen features, candidates, setup, regime, entry, risk, and score layers must not consume outcome data. These rows are historical research labels, not signals, executed trades, orders, or live-performance results.

## Verified baseline counts

- Total rows: 14,251
- Primary ENTRY_ELIGIBLE source rows: 4,268
- Valid next-open entries: 3,296
- Invalid entries: 972
- Forward-data unsafe: 700
- Effective R:R invalid: 260
- Open at or below stop: 12
- Quantity zero: 0
- TARGET_FIRST / STOP_FIRST / AMBIGUOUS / NEITHER_WITHIN_HORIZON: 115 / 724 / 1 / 2,456

All 700 unsafe primary rows were unsafe on the entry session; later-window-only unsafe count was zero. The existing conservative safety policy and next-open R:R revalidation therefore remain unchanged.

## Research notes and handoff

FOUR_SESSION_HORIZON_RESULT is LIKELY_TOO_SHORT, but this is a research note rather than a baseline defect. Extended 5/6/8/10-session results remain audit-only. DESCRIPTIVE_PATTERN is WEAK; this is neither a profitability conclusion nor a basis for changing rules.

Same-symbol opportunities overlap materially: maximum streak 4 and four-session overlap rate about 31.159%. Concurrent valid opportunities had median 15, p90 31.8, p95 37, and maximum 74; naive all-entry notional exceeded ₹100,000 on 654 days. A future portfolio backtest must handle concurrency, available capital, duplicate and same-symbol overlap, portfolio risk, and deterministic opportunity selection. Those rules are intentionally not implemented here.

## Deliberate omissions

No cost model, slippage model, exit optimization, portfolio allocator, ledger, compounded P&L, signal generation, execution, broker action, migration, or Supabase persistence is part of this baseline.
