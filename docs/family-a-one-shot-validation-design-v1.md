# Family A one-shot validation design V1

`FAMILY_A_ONE_SHOT_VALIDATION_DESIGN_V1` seals the protocol for the exact frozen `PROVISIONAL_VALIDATION_CANDIDATE_V1`. It is a design artifact only. No validation run has occurred, no validation holdings were generated, and no 2025+ candidate performance was calculated or inspected.

## Candidate and development evidence

Cross-family synthesis selected Family A because it was the only A-G architecture to pass all ten validation-candidacy gates. That selection is not evidence that it will perform in the future. The candidate is exactly `MOM-A-002` with the `A2-002` whole-share implementation at INR 500,000: point-in-time Nifty 500, long-only six-month cross-sectional relative momentum, top decile, quarterly rebalancing, equal weighting, next-eligible-session open execution, no leverage, and the frozen delivery-equity cost model. No Family B, C, or G overlay—and no absolute-momentum, SMA, compression, regime, VIX, breadth, news, catalyst, stop, target, or intraday rule—has been added.

The frozen 2022-01-01 through 2024-12-31 development reference starts at INR 500,000 and ends at INR 955,331.6799 after costs, with a 91.06633598% total return, 24.10585067% CAGR, and 22.92216992% maximum-drawdown magnitude. These values define degradation comparisons only. Development is insufficient because it is in-sample research evidence; a separately governed temporal holdout is needed to assess generalization.

## Window, schedule, and sample

The formal validation window is 2025-01-01 through 2026-08-13. Date-only NSE calendar metadata produces entries on 2025-01-01, 2025-04-01, 2025-07-01, 2025-10-01, 2026-01-01, 2026-04-01, and 2026-07-01. The first six intervals have their next quarterly endpoint inside the window and are eligible for primary metrics. The interval beginning 2026-07-01 is incomplete at the formal end and is excluded.

No post-window data may be imported to complete that interval. A future `TERMINAL_MARK_TO_MARKET_DIAGNOSTIC` may be reported separately, but it is currently uncomputed and can never alter the primary classification. Six expected completed intervals constitute `VALIDATION_SAMPLE_ACCEPTABLE`; five or more are acceptable, exactly four is limited with `MIXED_LIMITED_SAMPLE` as the maximum classification, and fewer than four is inconclusive.

## Sealed criteria

The seven core gates are:

- A — positive after-cost performance: net ending equity exceeds starting equity and net CAGR is positive.
- B — CAGR retention: net CAGR is at least 12.052925335%.
- C — drawdown acceptability: maximum-drawdown magnitude is no more than 30%.
- D — interval consistency: at least 60% of completed intervals are positive after costs, rounded up to a whole interval (four of the expected six).
- E — cost robustness: exact frozen cost accounting passes, the result remains profitable after costs, and normalized cost drag is flagged as material above 1.50 times development. The frozen normalized definition is total modeled cost divided by average net equity; the material threshold is 4.0421728943211638281245344025%.
- F — implementation integrity: point-in-time membership, ranking, top-decile selection, timing, weighting, capital, whole shares, no leverage, costs, cash, holdings, leakage, and parameter immutability all reconcile.
- G — sample adequacy: at least five completed intervals are required for full pass eligibility.

The four secondary quality dimensions are H, nonnegative 2025 and 2026-to-end slices; I, Sharpe-like above 0.5; J, drawdown magnitude no more than 26.36049541%; and K, CAGR of at least 14.463510402%. They are descriptive quality dimensions, not standalone fatal gates.

`STRONG_PASS` requires all A-G, at least three of H-K, CAGR at or above the K threshold, and drawdown at or below the J threshold. `PASS` requires all A-G without all strong conditions. `MIXED` requires sound implementation/data, an adequate sample, positive cumulative after-cost performance, no fatal condition, and one or two failures among A-E. `MIXED_LIMITED_SAMPLE` applies to exactly four otherwise interpretable intervals. `FAIL` follows nonpositive ending gain/CAGR, drawdown above 30%, material implementation failure, three or more A-E failures, or a fatal fail. `INCONCLUSIVE` covers corrupt data, unresolved methodology error, fewer than four intervals, identity mismatch, execution contamination, or implementation-caused fatal D-F.

Fatal conditions are net return at or below -10%, net CAGR at or below -8%, drawdown above 35%, material lookahead/leakage, candidate mutation, and incorrect universe/cost/execution implementation. A-C force `FAIL`. D-F map to `INCONCLUSIVE` with run invalidation only when a provable implementation or artifact defect caused them; otherwise they force `FAIL`.

## Governance and advancement

The lifecycle is `SEALED_DESIGN -> AUTHORIZED_FOR_ONE_SHOT -> EVALUATED`. It remains `SEALED_DESIGN`, the formal run count is zero, and the maximum is one. Readiness does not grant authorization. Only a separately reviewed deterministic bug, artifact corruption, or provable implementation defect may replace a run, and the original must first be invalidated.

Generalization maps `STRONG_PASS` to `STRONG_GENERALIZATION`, `PASS` to `GENERALIZES`, both mixed states to `MIXED_GENERALIZATION`, `FAIL` to `DOES_NOT_GENERALIZE`, and `INCONCLUSIVE` to itself. Strong/pass is only eligible for Strategy V2 candidate review; mixed is not eligible without further governance, fail rejects the candidate, and inconclusive produces no decision. No Strategy V2 is created automatically, and failure cannot trigger parameter salvage against this holdout.

The structural audit found adjusted-price, liquidity, execution-open, lookback, point-in-time membership, corporate-action, and calendar inputs available. Readiness is `READY_WITH_LIMITATIONS` because membership remains reconstructed partial history with known anomalies, corporate-action data retains review/continuity statuses, and prior aggregate later-period observations limit philosophical purity. One-shot readiness is `YES`, but execution is `NOT_AUTHORIZED`.

The required disclosure is:

> The project has previously observed aggregate later-period diagnostics in other research contexts. Therefore this is a formally governed/sealed validation period, but not philosophically pristine laboratory-grade unseen data.

The sealed manifest is `FAMILY_A_ONE_SHOT_VALIDATION_DESIGN_MANIFEST_V1`. Its content-only pre-verification hash is `55301e18a013c5dfc660d9babfa152cf883d31ff2d395bf834840b2919f07110`; after recording completed verification, the review-ready design hash is `8effd2ca6233c581d88aab46d16ff48b1aa04c0ce7648be11889c094d401a494`. The next action is review and an explicit, separate authorization decision—not validation execution.
