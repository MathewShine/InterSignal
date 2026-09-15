# InterSignal Strategy Family G research closure V1

## Scope and decision

`FAMILY_G_RESEARCH_CLOSURE_V1` closes `STRATEGY_FAMILY_G_REGIME_VOLATILITY_V1` under `REGIME_PARTICIPATION_CLOSURE_V1`. Family G is `PAUSED_NO_VALIDATION_CANDIDATE`; validation was not accessed and Strategy V2 was not created. This command uses the frozen Command 03 DEVELOPMENT outputs and does not rerun either portfolio.

Family G asked one narrow question: can a quarterly NIFTY 500 close-above-SMA200 all-in/all-cash participation gate improve an otherwise unchanged Family A 6M momentum strategy? The result was `MIXED`, and the sole preregistered treatment, `REGIME-G-001`, was `PARTIALLY_SUPPORTED` but not advanced.

## Family A control reproduction

`CONTROL-G-000` is frozen as `PRESERVED_STRONG_REFERENCE_CONTROL`. It independently reproduced the Family A `MOM-A-002` / ₹500,000 `A2-002` implementation in DEVELOPMENT:

- net ending equity: ₹955,331.6799
- net return: +91.06633598%
- net CAGR: 24.10585067%
- maximum drawdown magnitude: 22.92216992%
- annualized volatility: 21.22551802%
- Sharpe-like value: 1.14236622

This remains DEVELOPMENT evidence only. Family G's treatment result does not weaken the previously observed Family A evidence and does not upgrade Family A to validated.

## SMA200 treatment result

`REGIME-G-001` is frozen as `CLOSED_PARTIALLY_SUPPORTED_NOT_ADVANCED`. Its net ending equity was ₹701,280.9627, net return was +40.25619254%, net CAGR was 11.94573675%, and maximum drawdown magnitude was 30.72712578%. Profitability, temporal support, costs, sample size, and accounting passed. The only quality dimension that passed was lower annualized volatility. Return preservation and the drawdown objective failed, so there is no validation candidate.

The gate excluded two quarters, and both were profitable in the control:

| Rebalance | Control interval return | Classification |
| --- | ---: | --- |
| 2022-06-30 | +13.77159596% | `MISSED_GAIN` |
| 2023-03-31 | +19.97507309% | `MISSED_GAIN` |

The normalized direct gate effect was approximately -₹262,351.79 and is frozen as `NEGATIVE`. Subsequent whole-share sizing, capital-path, and transaction-cost differences provided an approximately +₹8,301.07 partial offset, but the final treatment-minus-control ending-equity gap remained approximately -₹254,050.72.

## Drawdown, cost, and volatility lessons

The treatment did not operate as a successful drawdown-control overlay. Maximum drawdown worsened from 22.92216992% for the control to 30.72712578% for the treatment, a relative worsening of approximately 34.05%.

Treatment costs were ₹3,659.37, or approximately 20.7566%, lower. That saving did not compensate for missed profitable exposure. Treatment annualized volatility also fell from 21.22551802% to 20.29481462%, but its Sharpe-like value fell materially from 1.14236622 to 0.66819252. Reduced volatility alone is not evidence of improved risk-adjusted performance.

## Negative evidence and interpretation boundary

`EDGE-NEGATIVE-G-SMA200-GATE-001` records that the exact quarterly NIFTY 500 close>SMA200 gate failed to preserve return and failed to improve drawdown. Its status is `RESEARCH_EVIDENCE_NOT_VALIDATED`.

This is not evidence that “SMA200 never works” or that “market regime filters never work.” Only the frozen combination of a quarterly decision, NIFTY 500, close>SMA200 condition, and all-in/all-cash participation was evaluated. No VIX, breadth, alternative SMA, different benchmark, monthly schedule, multi-regime score, partial exposure, or second treatment was tested.

## Preserved research assets and future policy

`NIFTY500_BENCHMARK_PREHISTORY_V1` remains shared market-index infrastructure. The quarterly ledger, cash-quarter attribution, path-effect analysis, drawdown attribution, cost/turnover analysis, and normalized-quarter diagnostic remain available for later cross-family work.

`FAMILY_G_FUTURE_RESEARCH_POLICY = REQUIRES_GENUINELY_NEW_REGIME_ARCHITECTURE`. Family G V1 must not continue through casual changes such as SMA150, SMA250, NIFTY 50, monthly decisions, VIX or breadth thresholds, a multiple-regime score, or partial-exposure percentages. Any future Family G study requires an independently justified architecture and a new preregistration.

## A–G cycle and handoff

`STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS = COMPLETE_FOR_CURRENT_RESEARCH_CYCLE`. This means the planned discovery pass is complete; it does not mean that a production strategy has been selected.

`NEXT_PLANNED_PHASE = CROSS_FAMILY_EVIDENCE_SYNTHESIS`. The handoff is planning-only: compare Families A–G, identify reusable evidence, separate positive, negative, and data-blocked findings, decide whether any candidate merits a validation design, and determine whether a genuinely new family is justified. No synthesis is performed by this closure command.

## Safety and governance

The closure produces research governance artifacts only. It creates no live signals or orders, makes no broker or network calls, performs no remote migration or Supabase persistence, changes no Family G parameter, accesses no validation data, creates no Strategy V2, and starts no new family.
