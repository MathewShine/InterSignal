# Family B Development Attribution Audit V1

## Scope and governance

This document records Step 03.02 / Command 03, `FAMILY_B_ATTRIBUTION_AUDIT_V1`, using profile `RELATIVE_ABSOLUTE_MOMENTUM_ATTRIBUTION_V1`. The audit was required because the frozen development evaluation supported both Family B records even though MOM-B-001 removed no candidates and most MOM-B-002 removals were caused by unavailable SMA200 history rather than a negative trend signal.

The audit covers only 2022-01-01 through 2024-12-31. It reads the frozen Command 01 signal inputs and Command 02 result ledgers. It does not access validation, change a parameter, create a strategy, create B003, test an alternate moving average, create Strategy V2, or start Family C.

All frozen inputs were verified before attribution:

- Family config: `f98a16fcb0618a01c07242d5fe2ab3b063464d26b48c1f814200236315628076`
- Success criteria: `b7459cad23169a2cc2df9355e34141e852dc41648c64cc5215dfc04d62942d71`
- CONTROL-B-000 result: `6c4a63f5a14da5f16b6a6151f63a39afd6abbad6ec08c9eb663ce92483858263`
- MOM-B-001 result: `8b29c232e4e72f4a44b7fc810259d94390238f04d9e5ce58f053df6937945579`
- MOM-B-002 result: `07b4499bb2b50b66e52f9195ddd5e05bea6b255596ea0b2b0185c13e4bbd06a6`
- Development registry: `a163a6a16dc9ac16e5adcfb4f0f6edc7fbafe06596e94bf2e7b068965c14927f`

## Primary answers

### Q1: Why B001 differs from control

MOM-B-001 and CONTROL-B-000 have the same eligible-universe count and the same reconstructed pre-allocation top-decile symbol set on all 11 quarterly formations. B001 evaluated 302 candidates, passed all 302, and removed zero. Therefore no observed performance difference is attributed to the absolute 6M-return filter.

The first mechanical divergence occurs on the 2022-06-30 formation. The historical Family A control requires a minimum of 20 holdings, so its 19-name top decile was treated as insufficient and the prior portfolio was retained. Family B's frozen minimum is 10 holdings, so B001 executed a new 19-name portfolio. This creates a different portfolio state. The remaining nine non-equivalent rebalances are explained by that path difference, whole-share allocation residuals, trade differences, and costs. There are no unexplained differences and no implementation defect.

`B001_CONTROL_EQUIVALENCE_RESULT = EXPLAINED_NON_EQUIVALENCE`

`B001_DISTINCT_FILTER_EVIDENCE = NONE`

### Q2: Genuine B002 filter versus unavailable history

B002 evaluated 302 top-decile candidates and removed 31:

- 1 was genuinely below SMA200: AUBANK on 2022-06-30, close ₹591.70 versus SMA200 ₹612.7415.
- 30 had no valid SMA200 history.
- 0 belonged to any other removal category.

All 30 unavailable candidates otherwise belonged to the control's reconstructed top-decile candidates, and all 30 were actually held by the control portfolio applicable to their interval. Twenty-three occurred on the first formation, leaving B002 with zero qualifying holdings. B002 therefore stayed entirely in cash from 2022-04-01 through 2022-07-01 while control was 98.1159% invested.

The first interval returned −12.88628351% for control and 0% for B002. Including the avoided first control rebalance cost, this interval added ₹65,153.5554 to the B002-minus-control equity gap, or 13.03071108 percentage points of initial capital and 35.9685% of the final observed equity gap directly.

The single true filter event did change B002's target weights, but AUBANK was not actually held by the frozen control during that interval. Its actual control contribution was therefore ₹0. The isolated downstream causal effect cannot be calculated without inventing a counterfactual portfolio rule, so no statistical or validation claim is made from this observation.

### Q3: Nature of B002's apparent advantage

The result is a mixture of implementation mechanics and data-history effects, dominated by history availability and the cash/path consequences it created. It is not demonstrated to be a distinct SMA200 trend-filter advantage.

`B002_CASH_EFFECT_MATERIALITY = DOMINANT`

`B002_TREND_FILTER_EVIDENCE = CONFOUNDED_BY_HISTORY_AVAILABILITY`

`B002_DEVELOPMENT_ADVANTAGE_ATTRIBUTION = PRIMARILY_HISTORY_AVAILABILITY`

## First-schedule and interval attribution

At the 2022-03-31 formation, control selected 23 holdings. B002 had zero candidates with available SMA200, 23 unavailable observations, zero qualifying holdings, no portfolio, and 100% cash. The execution date was 2022-04-01.

The interval bridge uses each frozen interval's B002-minus-control net P&L difference minus the difference in rebalance costs at the interval start. The 11 interval contributions sum exactly to the final ₹181,140.4972 net-equity gap. This is attribution arithmetic over frozen ledgers, not a new backtest.

## Year attribution

The frozen annual return differences were:

- 2022: B002 led by 18.55621814 percentage points.
- 2023: B002 trailed by 0.29867848 percentage points.
- 2024: B002 led by 0.83794037 percentage points.

To identify when the final advantage originated while preserving compounding, the audit uses an exact temporal telescoping bridge. A year's return difference is carried through B002's later realized annual returns and through control's earlier realized annual returns. On this basis, the 2022-origin contribution is ₹176,654.4248, or 97.52342935% of the total final relative advantage. The 2023 contribution is negative and the 2024 contribution is modest. The three contributions reconcile to ₹181,140.4972.

## Cash and missing-history effects

The first history-unavailable event left ₹500,000 in B002 cash rather than the ₹490,595.2077 invested by control. The seven later SMA-unavailable removals did not create another insufficient-breadth event: their weights were redistributed across the remaining qualifying names, subject to frozen whole-share mechanics. Their isolated effects cannot be distinguished from allocation and portfolio-state dependence without a new counterfactual rule.

`B002_HISTORY_NEUTRAL_ATTRIBUTION_REPLAY` was not run. Its status is `ATTRIBUTION_REPLAY_NOT_IDENTIFIABLE`. Treating an observation as unknown does not determine whether it should pass, fail, receive weight, or leave cash; choosing one would change missing-SMA behavior and create a new trading rule. No shorter average, external data, future data, or partial-window SMA was imputed.

## Mature-history diagnostics

For descriptive purposes only, broad SMA history maturity is defined as the first formation with at least 90% top-decile SMA200 coverage and sufficient breadth, with coverage remaining at least 90% thereafter. The first such formation is 2022-06-30, executed 2022-07-01, with 94.73684211% coverage.

From that execution through development end, normalized returns were 119.69403033% for control and 127.67128148% for B002, a B002 difference of 7.97725115 percentage points. Maximum drawdowns over that span were −21.52481602% for control and −22.38587109% for B002. Average holdings Jaccard overlap was 89.61968424% across ten rebalances.

For calendar 2023–2024, compounded frozen returns were 89.50926532% for control and 90.39916806% for B002, a difference of only 0.88990274 percentage points. No success threshold is attached to either diagnostic subperiod.

## Timeline

The normalized-equity report contains only the three frozen curves: CONTROL-B-000, MOM-B-001, and MOM-B-002. It annotates first portfolio executions, the B002 insufficient-breadth event, every SMA-unavailable formation, the single true below-SMA removal, and the descriptive mature-history start. No new strategy curve was generated.

## Validation-design readiness

`FAMILY_B_VALIDATION_DESIGN_READINESS = NO_CANDIDATE_READY`

B001 is not ready solely on its performance result because its filter had no distinct effect. B002 is not ready because its apparent development advantage is primarily an early-history availability artifact and the one genuine trend-filter observation cannot establish meaningful evidence. The previously recorded next stage has not been executed.

## Limitations

- The control and Family B use different frozen minimum-breadth rules, which prevents B001 performance from identifying its zero-threshold filter.
- There is only one genuine below-SMA200 top-decile rejection.
- A history-neutral counterfactual is not identifiable without defining a new missing-data rule.
- Point-in-time membership history retains the previously frozen partial-confidence limitation.
- New listings can lack 200 sessions even after broad market-history maturity.
- Position-level reference contributions describe what control held; they are not causal counterfactual estimates for B002.

## Security and immutability

The audit made no broker calls, placed no orders, emitted no live signals, wrote no secrets, performed no network writes, ran no remote migrations, and persisted nothing to Supabase or another database. Frozen Command 01/02 artifacts were read and hash-verified, not modified.

The frozen audit result hash is:

`cdcef2b88766f501f6b7d21a2c1dd1cc93f79287f79c09d02dfef7f84142a0f1`
