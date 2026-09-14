# InterSignal Family B Development Evaluation V1

Command: `FAMILY_B_DEVELOPMENT_EVALUATION_V1`
Profile: `RELATIVE_ABSOLUTE_MOMENTUM_DEVELOPMENT_V1`
Family: `STRATEGY_FAMILY_B_RELATIVE_ABSOLUTE_MOMENTUM_V1`
Development partition: 2022-01-01 through 2024-12-31
Validation: `NOT_ACCESSED`

## Frozen hypothesis and pre-run gate

This command evaluates whether a stock-level positive-trend requirement improves downside robustness without destroying return quality relative to pure 6M cross-sectional momentum. It evaluates exactly `CONTROL-B-000`, `MOM-B-001`, and `MOM-B-002` in `EXECUTABLE_INTEGER_SHARE_500K` primary mode and `IDEALIZED_EQUAL_WEIGHT_PERCENTAGE` diagnostic mode.

The pre-run gate verified before performance access:

- Family B config: `f98a16fcb0618a01c07242d5fe2ab3b063464d26b48c1f814200236315628076`;
- success criteria: `b7459cad23169a2cc2df9355e34141e852dc41648c64cc5215dfc04d62942d71`;
- control reference: `b84ca4ac1a88daed38efd60a9142aee175fe1dbeabb02445788915f8889adc87`;
- B001 parameters: `b65843f0fadd6b75b205d3b4d37ea0e40e212bc28e06b98debb75589014e9446`;
- B001 preregistration: `bd5c08bdf5ecf16e364b718302d9df6de426cb9c15c54aceacb24e90ab7ac203`;
- B002 parameters: `0b7c8efec15017f9d2a0370bd8545d4463ff042ed13cb749d936c7979d0c91fe`;
- B002 preregistration: `d07d53efb5ee43e403236d3e67359abe6573cf137e00c6a41ad2c90bb87788fe`; and
- Family A closure: `51e2190c25f3146609ac173cc345e2a8adc0b6c9efb824633d735dc976581250`.

No parameter or success criterion changed. No B003 or combined B001+B002 filter was created. The cost model remains `INDIA_EQUITY_COST_MODEL_V1` / `NSE_CASH_DELIVERY_RESEARCH_V1` / `COST-SCENARIO-002` with 5 bps per side.

## Frozen success and fatal criteria

Standard support requires all A–G:

A. treatment net CAGR at least 85% of control;
B. drawdown improves materially by at least 15%, or does not worsen by more than 10%;
C. at least two of three development years nonnegative and more than 15 percentage points of control underperformance in no more than one year;
D. normalized modeled cost-drag increase no greater than 25%;
E. at least 80% of schedules with at least 10 qualifying holdings;
F. full-development average cash no greater than 35%; and
G. clean accounting and data integrity.

Fatal failure is triggered by CAGR preservation below 70%, drawdown worsening above 20%, breadth below 60%, average cash above 50%, implementation/data failure, or lookahead. Strong support additionally requires at least 90% return preservation, at least 15% drawdown improvement, no negative year, and clean accounting.

## CONTROL-B-000

The control reproduced the frozen Family A A2-002 executable ₹500k reference exactly across all checked metrics without overwriting it.

| Metric | Result |
|---|---:|
| Starting equity | ₹500,000.00 |
| Gross ending equity | ₹972,961.58 |
| Net ending equity | ₹955,331.68 |
| Gross return | 94.5923% |
| Net return | 91.0663% |
| Net CAGR | 24.1059% |
| Max drawdown | -22.9222% |
| Annualized volatility | 21.2255% |
| Sharpe-like metric | 1.1424 |
| Positive-month rate | 58.3333% |
| Positive rebalance-period rate | 80.0% |
| Annualized turnover | 4.3351x |
| Total modeled costs | ₹17,629.90 |
| Full-development average cash | 10.5127% |
| Holdings range (min/median/max) | 22 / 27 / 35 |

Yearly net returns were 0.8216% in 2022, 51.1810% in 2023, and 25.3526% in 2024. The worst month was February 2023 at -8.4915%; the worst rebalance period was 2022-04-01 through 2022-07-01 at -12.8863%. The longest net drawdown lasted 155 sessions and was unrecovered at development end.

## MOM-B-001

`MOM-B-001` retains top-decile stocks only when the same 6M compounded return is strictly positive. In this development sample, all 302 top-decile candidates were already positive, so the absolute filter removed zero names. Its performance difference from the control is therefore not evidence of an incremental positive-return filter effect; it mainly reflects the frozen Family B 10-name breadth rule versus the historical control schedule’s Family A sufficiency behavior.

| Metric | Result |
|---|---:|
| Starting equity | ₹500,000.00 |
| Gross ending equity | ₹990,241.77 |
| Net ending equity | ₹971,782.66 |
| Gross return | 98.0484% |
| Net return | 94.3565% |
| Net CAGR | 24.8147% |
| Max drawdown | -22.9222% |
| Drawdown relative improvement | 0.0000% |
| Annualized volatility | 21.3724% |
| Positive-month rate | 58.3333% |
| Positive rebalance-period rate | 80.0% |
| Annualized turnover | 4.5724x |
| Total modeled costs | ₹18,459.11 |
| Full-development average cash | 10.6035% |
| Holdings range (min/median/max) | 19 / 27 / 35 |
| Average qualifying count | 27.4545 |
| Return-preservation ratio | 1.0294 |

Yearly net returns were 2.3582% in 2022, 51.1103% in 2023, and 25.6558% in 2024. It passed A–G and triggered no fatal condition. Because drawdown did not improve by the strong-support minimum, `MOM_B_001_DEVELOPMENT_RESULT = SUPPORTED`.

During the 12 control-negative months, average control return was -3.7886% and average B001 return -3.8511%, a -0.0625 percentage-point difference. Its upside-capture ratio in control-positive months was 1.0226. Average executable holdings overlap was 92.7273% by Jaccard and 93.6759% relative to control holdings. Turnover increased by 0.2373x annualized.

Idealized net return was 100.6783% versus executable 94.3565%, an implementation gap of -6.3218 percentage points. Idealized net CAGR was 26.1544% versus executable 24.8147%.

## MOM-B-002

`MOM-B-002` retains top-decile stocks only when formation adjusted close is strictly above the exact SMA200. The filter removed 31 of 302 candidates (10.2649%): one true below-SMA rejection and 30 unavailable signals. Twenty-three of those unavailable signals occurred on the first formation date, which had insufficient local history and therefore remained cash without backfilling.

| Metric | Result |
|---|---:|
| Starting equity | ₹500,000.00 |
| Gross ending equity | ₹1,155,739.44 |
| Net ending equity | ₹1,136,472.18 |
| Gross return | 131.1479% |
| Net return | 127.2944% |
| Net CAGR | 31.5056% |
| Max drawdown | -22.3859% |
| Drawdown relative improvement | 2.3397% |
| Annualized volatility | 19.8833% |
| Positive-month rate | 55.5556% |
| Positive rebalance-period rate | 80.0% |
| Annualized turnover | 4.1283x |
| Total modeled costs | ₹19,267.26 |
| Full-development average cash | 18.1322% |
| Holdings range (min/median/max) | 0 / 27 / 34 |
| Average qualifying count | 24.6364 |
| Return-preservation ratio | 1.3070 |

The sole insufficient-breadth schedule was 2022-03-31. Yearly net returns were 19.3779% in 2022, 50.8823% in 2023, and 26.1905% in 2024. It passed A–G and triggered no fatal condition. Because its 2.3397% drawdown improvement was below the 15% strong threshold, `MOM_B_002_DEVELOPMENT_RESULT = SUPPORTED`.

During the 12 control-negative months, average B002 return was -2.5937%, 1.1949 percentage points better than control. Its upside-capture ratio was 1.0231. Average executable holdings overlap was 81.4724% by Jaccard and 82.2397% relative to control. Annualized turnover decreased by 0.2068x.

Idealized net return was 132.9458% versus executable 127.2944%, an implementation gap of -5.6514 percentage points. Idealized net CAGR was 32.5874% versus executable 31.5056%.

## Cash interpretation

Cash is measured over all development trading sessions, including the common period before the first eligible quarterly execution. The mutually exclusive decomposition reconciles exactly:

- control: 8.2100 percentage points before first formation plus 2.3027 points of invested-period whole-share residual/drift, totaling 10.5127%;
- B001: 8.2100 points before formation plus 2.3936 points of residual/drift, totaling 10.6035%;
- B002: 8.2100 points before formation, 8.3445 points from the insufficient-breadth/no-portfolio interval, and 1.5777 points of residual/drift, totaling 18.1322%.

B002’s lower drawdown cannot automatically be treated as alpha because it includes a longer cash interval. Nevertheless, its full-development average cash remains below the frozen 35% threshold.

## Family result and next stage

Both treatments are `SUPPORTED`; therefore:

- `FAMILY_B_DEVELOPMENT_RESULT = SUPPORT`
- `FAMILY_B_NEXT_RESEARCH_STAGE = FREEZE_CANDIDATE_FOR_VALIDATION_DESIGN`

This stage label does not authorize validation. It means a later command may freeze a candidate and design validation only after governance review and explicit human approval. No tuning, validation access, Strategy V2 creation, Family C work, live signals, orders, broker calls, migrations, or Supabase writes occurred.

## Immutable outputs

- CONTROL-B-000 result: `6c4a63f5a14da5f16b6a6151f63a39afd6abbad6ec08c9eb663ce92483858263`
- MOM-B-001 result: `8b29c232e4e72f4a44b7fc810259d94390238f04d9e5ce58f053df6937945579`
- MOM-B-002 result: `07b4499bb2b50b66e52f9195ddd5e05bea6b255596ea0b2b0185c13e4bbd06a6`
- Development registry: `a163a6a16dc9ac16e5adcfb4f0f6edc7fbafe06596e94bf2e7b068965c14927f`
