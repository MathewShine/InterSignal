# Family B MOM-B-002 clean development reevaluation V1

## Scope and frozen inputs

`FAMILY_B_B002_CLEAN_DEVELOPMENT_REEVALUATION_V1` implements the
`SMA200_REMEDIATED_DEVELOPMENT_EVALUATION_V1` profile. It is a controlled,
DEVELOPMENT-only reevaluation of frozen experiment `MOM-B-002`
(`RELATIVE_6M_PLUS_200DMA_TREND_V1`). Performance is restricted to
2022-01-01 through 2024-12-31. The 2020-01-01 onward prehistory in
`DAILY_HISTORY_PREHISTORY_V2` is used only for causal signal formation,
liquidity history, and corporate-action adjustment; it contributes zero
performance observations. Validation and all post-2024 prices remain
unaccessed.

The pre-run gate verified the exact frozen B002 parameter hash
`0b7c8efec15017f9d2a0370bd8545d4463ff042ed13cb749d936c7979d0c91fe`,
preregistration hash
`d07d53efb5ee43e403236d3e67359abe6573cf137e00c6a41ad2c90bb87788fe`,
Family B config hash
`f98a16fcb0618a01c07242d5fe2ab3b063464d26b48c1f814200236315628076`,
and success-criteria hash
`b7459cad23169a2cc2df9355e34141e852dc41648c64cc5215dfc04d62942d71`.
It also verified attribution-audit hash
`cdcef2b88766f501f6b7d21a2c1dd1cc93f79287f79c09d02dfef7f84142a0f1`.

## Why the original result was confounded

The frozen original B002 run had 30 SMA-unavailable top-decile candidate rows.
The attribution audit therefore classified its apparent advantage as primarily
history availability rather than demonstrated SMA200 filtering. In particular,
the truncated data prevented the first 2022 B002 portfolio from forming, so the
original result avoided a difficult invested period. That historical result and
its conclusions remain immutable; this command creates a separate clean record.

Command 04 added official-source prehistory without overwriting the frozen V1
overlap. This reevaluation verified and consumed the exact remediation hashes:

- configuration: `f7c60aaafc2661b163fb8c59c3b0ac5a68801b686e17a76ddd72938852a0657c`;
- raw extension: `e28b00f7bbff8ae85da54cfc0bbc6cbd06192a085f7663645c7e0392d61bc017`;
- adjusted extension: `3293f8e27ea17c0ef72946c538cab4463b4c08adf59c348fed9f3ea6bee9ad3d`;
- SMA readiness: `7757839611d462b86cc09f3559e1664020a024795995744f50d6d5023ff46c5a`;
- remediation manifest: `540baa503ac2f548a3f2b0e5107ddb5e823cf327ea6d06f93d61eaa52a31f6cf`.

## Unchanged strategy and implementation

The strategy remains top 10% by 126-session compounded return, followed by the
strict formation adjusted-close-above-exact-SMA200 rule. Every available SMA
uses exactly 200 valid adjusted observations ending no later than formation.
The portfolio remains long-only, equal-weight, quarterly, minimum 10 qualifying
names, ₹500,000 capital, whole-share next-open execution, no leverage, no stop,
and no target. No backfill or missing-SMA imputation is permitted.

Costs remain `INDIA_EQUITY_COST_MODEL_V1`,
`NSE_CASH_DELIVERY_RESEARCH_V1`, `COST-SCENARIO-002`, with 5 bps per side
slippage. The executable whole-share result is primary; the equal-weight
percentage result is diagnostic only. No B002 parameter changed, no alternate
SMA or combined filter was tested, B001 was not rerun, and no B003, Strategy V2,
or Family C work was created.

## Clean candidate availability and genuine filter impact

Across 302 frozen top-decile candidate rows, 294 qualify after the clean SMA
gate. The eight exclusions comprise one true below-SMA200 row, five genuine
recent-listing unavailable rows, two corporate-action unavailable rows, and
zero other unavailable rows. Thus the true removal rate is 1/302
(0.3311258278%) and the legitimate-unavailable removal rate is 7/302
(2.3178807947%). No dataset-truncation category remains. All 11 schedules have
at least 10 qualifying names; the qualifying range is 18 to 34 with median 27.

The single genuine exclusion is `AUBANK` at the 2022-06-30 formation: close
₹591.70 versus SMA200 ₹612.7415. Its next execution date is 2022-07-01. The
frozen synchronized control did not include AUBANK because it retained its
prior portfolio on that rebalance, so there is no realized control contribution
for this name. Clean B002 redistributed the notional candidate equal weight
from 5.2631578947% to 5.5555555556% per retained name, a +0.2923976608 percentage
point allocation change. This is descriptive and does not create a new
criterion. Because the exclusion is real but its realized portfolio effect is
not independently observable in the control, trend-filter evidence is `WEAK`
and attribution is `EVIDENCE_TOO_SPARSE`.

## Synchronized executable results

The `CONTROL-B-000` reproduction is labeled `CONTROL_REPRODUCTION_ONLY` and
matches its frozen reference exactly. It starts at ₹500,000 and ends net at
₹955,331.6799: 91.06633598% net total return, 24.1058506723% net CAGR,
-22.9221699220% net maximum drawdown, 21.2255180249% net annualized volatility,
1.1423662152 net Sharpe-like metric, 58.3333333333% positive-month rate, and
80.0% positive rebalance-period rate. Annualized one-way turnover is
4.3351435182x, modeled cost is ₹17,629.90, average cash is 10.5126727677%, and
the all-schedule holdings range is 22/27/35 minimum/median/maximum. Net yearly
returns are 0.82163300% (2022), 51.1810010060% (2023), and 25.3525668285%
(2024).

Clean B002 starts at ₹500,000 and ends gross at ₹982,256.8915 and net at
₹964,048.5815. Gross total return is 96.45137830%; net total return is
92.80971630%, net CAGR is 24.4824335199%, and net maximum drawdown is
-24.5429495732%. Net annualized volatility is 21.4329166800%, the net
Sharpe-like metric is 1.1477587179, the positive-month rate is 58.3333333333%,
and the positive rebalance-period rate is 80.0%. Annualized one-way turnover is
4.5543670239x and modeled cost is ₹18,208.31. Average cash is 10.5221590737%,
average invested capital is 89.4778409263%, and the all-schedule holdings range
is 18/27/34 minimum/median/maximum.

The clean executable yearly returns are 2.0420744200% (2022),
50.4678339525% (2023), and 25.5758040583% (2024). Relative to control they are
+1.2204414200, -0.7131670535, and +0.2232372298 percentage points respectively.
Clean B002 compounds to 88.9511923350% across 2023–2024, versus
89.5092653181% for control, a -0.5580729830 percentage point difference.

The diagnostic idealized clean B002 result ends net at ₹995,191.5974 with
99.0383194756% net total return and 25.8096099152% net CAGR. The executable
implementation gap is -6.2286031756 percentage points of net total return and
-1.3271763953 percentage points of net CAGR.

## Original versus clean B002

The frozen original B002 result remains ₹1,136,472.1771 net ending equity,
127.29443542% net return, 31.5056303953% net CAGR, and -22.3858710919% maximum
drawdown. The clean net CAGR is 7.0231968754 percentage points lower and the
clean drawdown is worse. Original 2022 return was 19.37785114%; clean 2022 is
2.04207442%, a -17.33577672 percentage point change. The original +18.55621814
percentage point 2022 advantage over control is reduced to +1.22044142 points.
It therefore does not mathematically disappear, but nearly all of it disappears
after causal SMA availability is restored. The comparison is diagnostic and
does not use the contaminated original result as control.

## Frozen criteria and decisions

The unchanged Governance V2 criteria produce:

- A return preservation: PASS (`RETURN_PRESERVATION_RATIO =
  1.0156220518`, above both 0.85 pass and 0.90 strong boundaries);
- B drawdown: PASS (`DRAWDOWN_RELATIVE_IMPROVEMENT = -0.0707079503`;
  no material improvement, but no worsening beyond 10%);
- C temporal support: PASS (three nonnegative years and zero years more than
  15 percentage points behind control);
- D cost efficiency: PASS (normalized cost-drag increase 0.0328084674);
- E breadth: PASS (100% of schedules meet minimum breadth);
- F capital deployment: PASS (average cash fraction 0.1052215907);
- G accounting/data integrity: PASS (cash/equity reconciliation, chronology,
  point-in-time membership, causality, remediation lineage, exact SMA200, and
  missing-SMA handling are all clean).

No fatal condition triggers, so
`MOM_B_002_CLEAN_REEVALUATION_RESULT = SUPPORTED`. This aggregate frozen-result
classification does not establish distinct filter causality. The evidence and
governance decisions are therefore:

- `B002_CLEAN_TREND_FILTER_EVIDENCE = WEAK`;
- `B002_CLEAN_DEVELOPMENT_ATTRIBUTION = EVIDENCE_TOO_SPARSE`;
- `B002_VALIDATION_DESIGN_READINESS = MORE_DEVELOPMENT_EVIDENCE_REQUIRED`;
- `FAMILY_B_POST_REMEDIATION_STATUS = CONTINUE_DEVELOPMENT_RESEARCH`;
- B001 remains `NO_DISTINCT_FILTER_EVIDENCE`.

The recommended next action is governance review of the sparse clean evidence
before designing any new, separately preregistered DEVELOPMENT research. This
command does not authorize or access validation.

## Immutable outputs and safety

The immutable result hashes are:

- `clean_control_result_hash`:
  `b0cac6bbdd31e4a2c6534fd7cc4b6eba9981693506444a20164df1246b0259ae`;
- `clean_b002_result_hash`:
  `48f70f4101175574968f2035afdb1534752a914889198d236cbd782bfe9dc6c2`;
- `b002_clean_reevaluation_hash`:
  `a6a287f60c0a995d165279a5ddb7c666eefcb174b7a6e1c3788a5634c3834987`.

Outputs live under
`data/research/strategy_families/family_b/v1/clean_reevaluation/` with control,
B002, comparison, ledger, and manifest subdirectories, plus the nine required
machine reports under `data/reports/`. Frozen Strategy V1, CAP4, all Family A
work, Family B Commands 01–04, and the original control/B001/B002 records remain
unchanged. The run generated zero live signals, live orders, broker calls,
remote migrations, database writes, Supabase persistence, network calls, or
secrets.

Known limitations are the five genuine recent-listing candidate rows, two
corporate-action excluded candidate rows, frozen partial-confidence
point-in-time membership reconstruction, descriptive-only filter attribution,
and the partial final holding period ending 2024-12-31.
