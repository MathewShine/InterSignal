# Strategy Family D: Opening Range / Stocks-in-Play V1

## Status and scope

`STRATEGY_FAMILY_D_OPENING_RANGE_V1` / `INTRADAY_OPENING_RANGE_STOCKS_IN_PLAY_V1` is a preregistered, long-only intraday research family governed by `FAMILY_D_RESEARCH_PROTOCOL_V1` and `RESEARCH_EXPERIMENT_GOVERNANCE_V2`. Its status is `PREREGISTERED_RESEARCH_FAMILY`; promotion and validation are not allowed.

Every output is labelled `BOUNDED_100_SYMBOL_INTRADAY_DEVELOPMENT_RESEARCH`. The immutable scope is the existing selected 100-symbol Groww NSE cash dataset from 2022-01-01 through 2024-12-31: 4,821 usable symbol-sessions, of which 4,812 are strict and 9 carry warnings. Structural research uses strict sessions only. This is not full-Nifty500 intraday evidence and the symbol set was not selected using Family D outcomes.

No final DEVELOPMENT performance was run. No returns, profit factor, expectancy, equity curve, or drawdown was calculated. Validation remains sealed, Strategy V2 was not created, and no live or persisted action is part of this command.

## Eligibility and portfolio architecture

A formation session requires point-in-time Nifty500 membership, adjusted daily close of at least ₹100, a 20-session median daily traded value of at least ₹10 crore, corporate-action structural eligibility, and a strict intraday session. Family D is long-only, begins future research with ₹500,000, permits no leverage, and must close every position in the same session.

At most five positions may be open. Each admitted trade may plan 0.50% of current portfolio equity as risk, so maximum planned simultaneous risk is 2.50%. Shares are `floor(allowed risk rupees / (entry price - stop price))`, further capped by available cash and whole-share/no-leverage constraints. A zero or invalid stop distance rejects the trade. No maximum stop-distance filter is present; absolute, percentage, and ATR-equivalent distance (when available) are future diagnostics only.

The frozen project cost configuration is `INDIA_EQUITY_COST_MODEL_V1`, profile `NSE_CASH_DELIVERY_RESEARCH_V1`, hash `9f20882e8fc4c6333c53637e516704ea73cc1db0cecb1ac2d9a5155996789c48`, using `COST-SCENARIO-002` (5 bps slippage per side). It remains a delivery-research proxy; Command 01 did not invent an intraday cost model.

## Opening-range mechanics

The opening range is exactly the first 15 minutes of the Asia/Kolkata cash session: the 09:15, 09:20, and 09:25 five-minute bars. ORH is their maximum high and ORL their minimum low. A signal is the first completed five-minute bar from 09:30 through 11:30 inclusive whose close is strictly above ORH; equality does not qualify. Execution is the next valid five-minute bar open, never the signal close. Without that next bar there is no entry.

The fixed initial stop is ORL. There is no ATR buffer, trailing stop, breakeven move, or profit target. A valid entry must be strictly above ORL. The primary time exit is the first valid executable bar open at or after 15:20, before market close.

Post-entry ordering uses `EXECUTION_ORDERING_V1`. A stop touch before the time exit exits at the stop-market reference. If a later bar opens below the stop, the open-through reference is that bar's open. With no target, target/stop ambiguity cannot occur; entry-bar stop interaction follows the same frozen ordering. Only one position per symbol per session is allowed and a failed breakout cannot reenter.

## Control and one treatment

`CONTROL-D-000` (`ORB15_PLAIN_V1`) is the reference control: 15-minute opening range, strict completed-bar close breakout, next-five-minute-open entry, ORL stop, and 15:20 time exit. It has no stocks-in-play filter. When same-timestamp signals exceed capacity, it ranks breakout excess `(signal close / ORH) - 1` descending, then symbol ascending.

Exactly one treatment is registered: `ORB-D-001` (`ORB15_WITH_OPENING_ACTIVITY_V1`). It adds only one rule. Current opening volume is the sum of the first three five-minute bar volumes. Its baseline is the median opening volume across the preceding 20 valid trading sessions, excluding the current session. The ratio is current opening volume divided by that median and must be at least 1.50. Treatment capacity ranks this ratio descending, then symbol ascending. No alternate threshold was tested.

There is no gap, news/catalyst, VWAP, daily-momentum, Strategy V1 score, Family C compression, CAP4, regime, or AI filter. Overnight gap is diagnostic only.

## Structural result and data readiness

All 4,812 strict sessions have a valid exact 15-minute opening range. The structural scan found 2,293 first-breakout sessions and 2,292 daily-eligible control signals. It produced no treatment signals and no activity-ratio distribution—not as a negative treatment result, but because none of the sampled strict sessions has all 20 immediately preceding valid market sessions in the frozen intraday dataset. The ingestion was designed around selected opportunity paths rather than continuous symbol history. Substituting the last 20 sampled observations would violate the preregistered baseline.

Accordingly, `FAMILY_D_DATA_READINESS = BLOCKED` and `FAMILY_D_ARCHITECTURE_RESULT = DATA_BLOCKED`. The rule architecture and 23 deterministic pilots pass, while actual `ORB-D-001` construction cannot proceed from the current dataset. Separate authorization for continuous prior-session intraday history is required before any DEVELOPMENT backtest.

The immutable Family D scope hash is `a32faa36a1500d804a5d680ca9cba37a8e822262823cab8e5e2eefe70673d8f3`. Future performance work must verify it before evaluation. If separately authorized ingestion changes the population, that is a new explicitly versioned scope and cannot silently replace this one.

## Frozen future outcome architecture

A later performance dataset can support entry, stop event, time exit, gross and net P&L, R multiple, MFE, MAE, minutes held, exit reason, and transaction costs. These fields are architecture only and are absent from Command 01's signal dataset.

The control is viable only when all seven conditions hold: net expectancy per trade above zero; net PF at least 1.05; net total return above zero; maximum drawdown magnitude at most 30%; at least two of three DEVELOPMENT years nonnegative; at least 150 closed trades; and accounting/data integrity passes. Fatal control conditions are net PF below 0.90, net expectancy at or below -0.10R, maximum drawdown above 40%, fewer than 75 trades, or implementation/data failure.

Treatment standard criteria A–G are:

- Return preservation: if control is profitable, treatment net total return is at least 80% of control; otherwise treatment has a positive net result.
- Profitability: net expectancy is positive and net PF is at least 1.10.
- Drawdown non-degradation: drawdown magnitude worsens no more than 10% relatively; more than 20% worsening is fatal.
- Temporal support: at least two of three years are nonnegative, and treatment does not underperform control by more than 10 percentage points in more than one year.
- Cost efficiency: normalized cost drag increases no more than 25%, unless substantially fewer trades accompany higher expectancy.
- Sample adequacy: at least 100 trades passes, 60–99 is `LIMITED_SAMPLE`, and below 60 is fatal.
- Accounting/data integrity passes.

Quality dimensions H–K are a treatment-control win-rate improvement of at least 5 percentage points; expectancy at least 1.15 times a positive control expectancy (or positive when control is nonpositive); PF at least control PF plus 0.05; and at least a 10% relative drawdown reduction. Win rate of at least 60% sets descriptive `HIGH_WIN_RATE_FLAG = YES` only.

`STRONGLY_SUPPORTED` requires all A–G, at least two H–K, net PF at least 1.20, and all DEVELOPMENT years nonnegative. `SUPPORTED` requires all A–G and at least one H–K. `PARTIALLY_SUPPORTED` requires no fatal condition, at least five A–G, and interpretability. A fatal condition or fewer than five A–G is `FAILED`. Family results map to `STRONG_SUPPORT`, `SUPPORT`, `MIXED`, `WEAK`, `FAILED`, or `INCONCLUSIVE` exactly as frozen in the machine-readable criteria file.

## Validation and generalization

Validation is not authorized. It can be considered only after clean bounded DEVELOPMENT evidence and a later decision about broader intraday-universe ingestion. Even strong bounded evidence would first require assessing whether the selected 100 symbols materially limit generalization; it would not authorize immediate validation.
