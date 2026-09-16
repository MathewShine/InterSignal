# Family A one-shot validation V1

## Governed authorization and replacement history

The exact frozen `MOM-A-002 / A2-002` candidate was authorized under `FAMILY_A_VALIDATION_AUTHORIZATION_V1` with authorization hash `bb1789cb5744cb9f777bf48dc1493b3fc115c3726cb95b86b844d067d8408631`.

### Invalidated First Attempt

Holdout computation was attempted during attempt 1, but result serialization failed before any performance result, report, or manifest was persisted. The deterministic serializer referenced nonexistent `end_gross_equity` and `end_net_equity` keys; the frozen period schema instead contains period P&L and period-return fields. Attempt 1 was formally classified `INVALIDATED_IMPLEMENTATION_DEFECT` and sealed under invalidation hash `67996558f869866d689826a22196b70ba0829646f3642dfcd436c1325abe76fb`.

No candidate parameter, criterion, validation input, portfolio computation, holding, return, cost, schedule, or terminal policy changed. The serializer-only repair maps each ending equity to its entry post-rebalance equity plus the already-computed period P&L. A deterministic offline fixture verifies the repair. The governed replacement was explicitly authorized under hash `1ce5421d2662a071f21c8729793e53e798f7bd64020363b6a6d7b70014e82fe9`. Only attempt 2 counts as the single completed formal validation run.

## Frozen candidate and protocol

- Command version: `FAMILY_A_ONE_SHOT_VALIDATION_V1`
- Profile: `MOM_A_002_FORMAL_HOLDOUT_VALIDATION_V1`
- Candidate: `PROVISIONAL_VALIDATION_CANDIDATE_V1`
- Strategy: point-in-time Nifty 500, price and liquidity gates, exact 6M momentum, top decile, quarterly rebalance, equal weight, whole shares, no leverage
- Implementation: `A2-002`, INR 500,000 starting capital, frozen next-open execution and frozen transaction costs
- Candidate identity hash: `0e8ef3cc26d4146258f25fdd4c269867a383d2f098d9df0e367d4b0ff86beacc`
- Validation design hash: `8effd2ca6233c581d88aab46d16ff48b1aa04c0ce7648be11889c094d401a494`
- Input snapshot hash: `e265caeb28c0bfc41c2edcfd36f78fa39abd45f647c036e00d7ed5c888087adf`
- Validation window: 2025-01-01 through 2026-08-13
- Primary completed intervals: 6
- Terminal interval beginning 2026-07-01: excluded from primary pass/fail and reported only as a mark-to-market diagnostic

No tuning, threshold change, alternate variant, overlay, Strategy V2, or Family H was introduced.

## Primary performance

| Metric | Validation result |
|---|---:|
| Starting equity | INR 500,000.00 |
| Gross ending equity | INR 542,462.46 |
| Net ending equity | INR 538,691.57 |
| Gross return | 8.49249200% |
| Net return | 7.73831400% |
| Net CAGR | 5.1124658026% |
| Max drawdown magnitude | 13.0647919507% |
| Annualized volatility | 12.4926883496% |
| Sharpe-like | 0.4689181476 |
| Positive completed intervals | 2 of 6 (33.3333333333%) |
| 2025 return | 1.2823500% |
| 2026 through primary end return | 6.3742241368% |
| Total one-way turnover | 3.5144815042x |
| Transaction costs | INR 3,770.89 |
| Normalized cost drag | 0.7518375615% |
| Average cash | INR 270,473.73 |
| Average holdings | 16.3333 |

## Completed intervals

| Interval | Execution to endpoint | Net return | Positive | Turnover | Entry cost | Holdings |
|---:|---|---:|---|---:|---:|---:|
| 1 | 2025-01-01 to 2025-04-01 | 0.000000% | No | 0.000000x | INR 0.00 | 0 |
| 2 | 2025-04-01 to 2025-07-01 | 0.000000% | No | 0.000000x | INR 0.00 | 0 |
| 3 | 2025-07-01 to 2025-10-01 | 0.000000% | No | 0.000000x | INR 0.00 | 0 |
| 4 | 2025-10-01 to 2026-01-01 | 1.5369201875% | Yes | 0.9221107800x | INR 777.59 | 33 |
| 5 | 2026-01-01 to 2026-04-01 | -6.7642652423% | No | 1.2074229723x | INR 1,447.11 | 31 |
| 6 | 2026-04-01 to 2026-07-01 | 14.6855225646% | Yes | 1.3849477519x | INR 1,546.19 | 34 |

The terminal diagnostic from 2026-07-01 through 2026-08-13 returned 2.0123389952% net and ended at INR 547,774.81. It does not affect any criterion, classification, or Strategy V2 decision.

## Sealed criteria and classification

| Gate | Result | Basis |
|---|---|---|
| A — Positive after-cost performance | PASS | Net equity above INR 500,000 and CAGR above zero |
| B — CAGR retention | FAIL | 5.1124658026% below 12.052925335% |
| C — Drawdown acceptability | PASS | 13.0647919507% at or below 30% |
| D — Interval consistency | FAIL | 2 positive intervals; 4 required |
| E — Cost robustness | PASS | Exact costs, profitable after costs, 0.7518375615% drag |
| F — Implementation integrity | FAIL | First three primary rebalances were not executed because the frozen eligibility layer produced zero eligible securities |
| G — Sample adequacy | PASS | 6 completed intervals |
| H — Year slices | PASS | 2025 and 2026 primary-period returns nonnegative |
| I — Sharpe-like | FAIL | 0.4689181476 is not above 0.5 |
| J — Drawdown retention | PASS | 13.0647919507% at or below 26.36049541% |
| K — CAGR quality | FAIL | 5.1124658026% below 14.463510402% |

Fatal condition F, `INCORRECT_UNIVERSE_COST_OR_EXECUTION_IMPLEMENTATION`, triggered through the sealed implementation-integrity mapping. The frozen mapping therefore produces:

- `VALIDATION_RESULT = INCONCLUSIVE`
- `FAMILY_A_GENERALIZATION_RESULT = INCONCLUSIVE`
- `STRATEGY_V2_ADVANCEMENT_STATUS = NO_DECISION`

This classification is not a candidate-performance `FAIL` and is not a generalization rejection. It reflects the sealed integrity gate and must not be reinterpreted after the outcome.

## Development comparison

| Metric | Development | Validation | Change / retention |
|---|---:|---:|---:|
| Net return | 91.06633598% | 7.73831400% | -83.32802198 pp |
| Net CAGR | 24.10585067% | 5.1124658026% | 21.2084023609% retention |
| Max drawdown magnitude | 22.92216992% | 13.0647919507% | -9.8573779693 pp |
| Normalized cost drag | 2.6947819295% | 0.7518375615% | -1.9429443681 pp |

## Data quality and limitations

The point-in-time membership history remains an official-events partial reconstruction with three known reconstruction anomalies. The corporate-action layer retains manual-review and continuity-break statuses. At the first three formations it excluded all 500 point-in-time members, producing no holdings until the 2025-10-01 rebalance. Across all seven formations, 1,548 member-windows were corporate-action excluded, 509 lacked sufficient liquidity history, and 12 lacked formation price or execution-open records. Portfolio cash and equity reconciliations had zero violations, selected valuation records had zero missing observations, and no post-2026-08-13 data was loaded.

The project has previously observed aggregate later-period diagnostics in other research contexts. Therefore this is a formally governed/sealed validation period, but not philosophically pristine laboratory-grade unseen data.

## Final governance state

- Lifecycle: `EVALUATED`
- Attempt count: 2
- Invalidated attempt count: 1
- Completed valid formal runs: 1
- Validation run count: 1 of 1
- Remaining formal runs: 0
- `SECOND_FORMAL_VALIDATION_RUN_ALLOWED = NO`
- Candidate changed: no
- Criteria changed: no
- Strategy V2 created: no
- Family H created: no

The next action is governance review of the sealed `INCONCLUSIVE` outcome and its first-three-rebalance eligibility limitation. This document does not authorize another validation run or Strategy V2 work.
