# Strategy Family G Development Evaluation V1

## Scope and frozen hypothesis

`FAMILY_G_DEVELOPMENT_EVALUATION_V1` evaluates only `CONTROL-G-000` against `REGIME-G-001` over the frozen DEVELOPMENT window 2022-01-01 through 2024-12-31. The hypothesis is that quarterly participation only when the official NIFTY 500 close is strictly above its causal SMA200 can reduce drawdown while retaining most of the Family A momentum return. No validation data, VIX, breadth, market score, second treatment, or Strategy V2 is used.

## Control reproduction

The control reads the immutable `MOM-A-002` / `A2-002` ₹500,000 ledger. Reproduction status is `PASS`. Net ending equity is ₹955331.6799, net return is 91.0663359800%, net CAGR is 24.105850672292473%, and maximum drawdown is -22.92216992201015671886716806%.

## Frozen regime gate and quarterly ledger

The exact Command 02 matrix contains 9 pass and 2 fail decisions. A pass uses the unchanged Family A selected-symbol set and frozen whole-share/cost mechanics. A fail liquidates to 100% cash at the next open and remains cash until the next scheduled quarterly rebalance. There is no mid-quarter re-entry. The full quarterly ledger is stored in `data/reports/family_g_dev_v1_quarterly.csv`.

## Portfolio results

The treatment ends at ₹701280.9627, with net return 40.2561925400%, net CAGR 11.945736746483359%, maximum drawdown -30.72712578084777096151980811%, annualized volatility 20.2948146190893%, and Sharpe-like metric 0.6681925214711923. Control and treatment costs are ₹17629.90 and ₹13970.53 respectively.

## Skipped-quarter attribution

- 2022-06-30: control return 13.77159596075032505853906660%; `MISSED_GAIN`.
- 2023-03-31: control return 19.97507308961838985613335600%; `MISSED_GAIN`.

## Direct gate and capital-path effects

Gate-fail quarters replace the same-interval control return with 0% cash return in the normalized diagnostic.

After a skipped quarter, later pass-quarter differences arise only from changed capital, whole-share sizing, and the associated frozen transaction-cost path.

The normalized-quarter diagnostic restarts each interval at 1.0: pass quarters reuse the control interval return, while fail quarters earn exactly 0%. This is diagnostic only and is not a second backtest or tuned strategy.

## Drawdown and frozen criteria

The control maximum-drawdown peak/trough is 2022-04-18 to 2022-06-20, recovering on 2022-12-01. Its peak-to-trough segment precedes the first gate-fail interval, although the first cash interval overlaps the recovery portion of the wider drawdown episode. The treatment maximum-drawdown peak/trough is 2022-04-18 to 2023-03-28, recovering on 2023-12-04.

Relative maximum-drawdown improvement is -34.04981241040010426169685913%. The treatment result is `PARTIALLY_SUPPORTED` and the Family G result is `MIXED`.

## Next stage and governance

`FAMILY_G_NEXT_RESEARCH_STAGE = PAUSE_FAMILY_G`. The frozen gate is interpretable but does not justify post-result parameter tuning or an automatic second treatment. Parameters and success criteria were not changed after observing results. Validation remains NOT ACCESSED, and this command does not create a validation design or Strategy V2.
