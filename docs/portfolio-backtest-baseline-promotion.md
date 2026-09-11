# Portfolio Backtest Baseline Promotion

STATUS: ACTIVE_MECHANICAL_BACKTEST_BASELINE

- Baseline: PORTFOLIO_BACKTEST_V1 / SWING_PORTFOLIO_BACKTEST_V1 / `6e98307afead0ffa`
- Audit: PORTFOLIO_BACKTEST_AUDIT_V1 — STABLE_WITH_REVIEW_NOTES
- Decision: A FREEZE UNCHANGED
- Step 02.12 — Portfolio Backtest Foundation: COMPLETE

The mechanical baseline is frozen unchanged. Independent audit work found accounting, chronology, and exit mechanics clean. Ranking is deterministic but highly sensitive, and selection distortion is high because finite portfolio capacity admitted only 728 of 3,296 mechanically valid opportunities.

The weak gross result is preserved rather than optimized away. Results remain HISTORICAL RESEARCH / GROSS BEFORE COSTS: costs, slippage, taxes, and fees are not modeled. Future portfolio-backtest profiles or methodology variants must use separately registered versions and must not silently replace this baseline.

See `docs/strategy-v1-portfolio-backtest-audit.md` for the structural audit and `docs/strategy-v1-portfolio-backtest-foundation.md` for the frozen contract.
