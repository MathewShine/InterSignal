# Strategy Family C DEVELOPMENT Evaluation V1

## Scope and frozen hypotheses

`FAMILY_C_DEVELOPMENT_EVALUATION_V1` evaluates the preregistered `STRATEGY_FAMILY_C_BREAKOUT_CONTINUATION_V1` family only on the 2022-01-01 through 2024-12-31 DEVELOPMENT partition. It compares `CONTROL-C-000` with compression treatment `BRK-C-001` and volume-expansion treatment `BRK-C-002`. Prehistory is used only by the already-frozen causal signal calculations. No 2025 price, validation record, Strategy V2 work, or Family D work is accessed.

The pre-run gate verified family config hash `5ecb5604939e1230ba176dbb339ebaf15418482da7a68bbbea24370c805961a6`, control hash `407034bc6451f60386492a1a445112e0fa7e05e374ef21119c04b9dd9060d393`, success-criteria hash `7bb950274ebe47ec7fafeb7e8659e07a457a4ddb169171aa97fe9ff9d0860a77`, both treatment parameter and preregistration hashes, and Family B closure hash `32e510424551e01fd54aac4711fa90fa08c711856c80b812d797b3a2f8faf6b0` before outcomes were loaded.

## Portfolio mechanics

The primary `EXECUTABLE_INTEGER_SHARE_500K` mode starts at ₹500,000, targets 5% of current equity per new position, uses whole shares and retained cash, permits no leverage, and caps the portfolio at 20 positions. Exits execute before entries. Same-day candidates rank by breakout strength descending and symbol ascending. An already-open symbol cannot re-enter or pyramid.

Formation is T close, entry is actual T+1 open, holding sessions are exactly T+1 through T+10, and exit is T+11 open. Entry gaps are recorded but never filtered. A formation whose complete exit path is unavailable by 2024-12-31 is excluded as `TERMINAL_PATH_UNAVAILABLE_WITHIN_DEVELOPMENT`; no 2025 price is used. The unchanged `INDIA_EQUITY_COST_MODEL_V1` / `NSE_CASH_DELIVERY_RESEARCH_V1` / `COST-SCENARIO-002` model applies 5 bps slippage per side.

`IDEALIZED_PERCENTAGE_PORTFOLIO` is a fractional-share diagnostic using the same signals, chronology, capacity, costs, and 5% target. It is not the classification basis.

## DEVELOPMENT results

The control closed 1,386 executable positions and ended at ₹486,232.10 net, a -2.7536% total return and -0.9264% CAGR. Net profit factor was 0.9849, net expectancy was +0.0086% per position, win rate was 46.39%, and maximum drawdown was 36.30%. Yearly net returns were -27.12%, +29.91%, and +2.71%. It is not `CONTROL_VIABLE`, but no frozen fatal control condition triggered.

Compression treatment C001 closed 1,170 positions and ended at ₹549,122.28 net, a +9.8245% return and +3.1731% CAGR. Net profit factor was 1.0730, net expectancy +0.2093%, win rate 49.74%, and maximum drawdown 22.08%. Yearly returns were -10.05%, +5.46%, and +15.77%. Six of seven standard criteria passed; treatment profitability failed because PF remained below 1.10. Win-rate improvement failed, while profit-factor, expectancy, and material drawdown improvements passed. `BRK_C_001_DEVELOPMENT_RESULT = PARTIALLY_SUPPORTED`.

Volume treatment C002 closed 1,371 positions and ended at ₹428,130.92 net, a -14.3738% return and -5.0411% CAGR. Net PF was 0.9172, net expectancy -0.1775%, win rate 45.15%, and maximum drawdown 37.26%. Yearly returns were -26.49%, +21.48%, and -4.11%. Four of seven standard criteria and none of four quality dimensions passed. `BRK_C_002_DEVELOPMENT_RESULT = FAILED`.

None of the three strategies reached the descriptive 60% high-win-rate ambition. Capacity rejection was material in all three primary portfolios: 75.99% for control, 61.78% for C001, and 71.35% for C002, using valid entry-ready signals as the denominator. The cap remains frozen at 20.

## Attribution and diagnostics

Compression removed 8,055 of 12,347 control signals (65.24%). It improved executable win rate by 3.35 percentage points, PF by 0.0882, expectancy by 0.2007 percentage points, CAGR by 4.10 percentage points, drawdown by 14.21 percentage points, and reduced capacity pressure by 14.21 percentage points. The improvement is meaningful but does not satisfy the frozen PF threshold.

Volume expansion removed 3,557 signals (28.81%). It reduced win rate by 1.24 percentage points, PF by 0.0676, expectancy by 0.1860 percentage points, and CAGR by 4.11 percentage points while slightly worsening drawdown. The frozen volume treatment is not supported.

MFE/MAE quartiles, entry-gap buckets, breakout-strength buckets, and average/median returns after 1, 3, 5, and 10 sessions are persisted as descriptive diagnostics. They do not authorize a new threshold, gap filter, stop, target, trailing exit, or holding-period change. Compression and volume distributions are descriptive; no alternate cutoff and no combined filter were tested.

The idealized mode did not overturn the primary findings. Relative to executable results, its net-return gaps were -2.90 percentage points for control, -4.07 for C001, and -0.31 for C002. Executable whole-share results remain the decision basis.

## Governance decision

`FAMILY_C_DEVELOPMENT_RESULT = MIXED`: C001 is partially supported while C002 failed, and the control was not viable. `FAMILY_C_NEXT_RESEARCH_STAGE = CONTINUE_CONTROLLED_DEVELOPMENT`. This does not authorize tuning, validation access, or promotion. Any further DEVELOPMENT hypothesis requires separate authorization and continued Governance V2 controls.

All cash/equity reconciliations, point-in-time membership checks, chronology checks, corporate-action eligibility checks, 20-position limits, terminal-path exclusions, and result-hash checks pass. Parameters and success criteria remain unchanged. Validation remains `NOT_ACCESSED`.
