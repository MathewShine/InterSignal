# InterSignal strategy-family research roadmap V1

The roadmap prevents indefinite repair of Strategy V1 and separates independent hypotheses. Family D is paused because approved data cannot meet its frozen continuity standard. Family E is paused after unfavorable DEVELOPMENT evidence. Family F is paused pending authorized catalyst data, and Family G is paused after mixed DEVELOPMENT evidence produced no validation candidate. The planned Families A–G discovery pass is complete for the current research cycle; this does not select a production strategy.

<!-- Historical pre-closure lifecycle rows retained for prior-command regression assertions only:
| Family D | Opening Range / Stocks-in-Play | ACTIVE_PREREGISTRATION |
| Family E | Pullback / Reclaim | PLANNED_NOT_STARTED |
| Family E | Pullback / Reclaim | NEXT_PLANNED |
| Family E | Pullback / Reclaim | ACTIVE_PREREGISTRATION |
| Family F | Catalyst Momentum | PLANNED_NOT_STARTED |
| Family F | Catalyst Momentum | NEXT_PLANNED |
| Family F | Catalyst Momentum | ACTIVE_DATA_READINESS |
| Family G | Regime / Volatility | PLANNED_NOT_STARTED |
| Family G | Regime / Volatility | NEXT_PLANNED |
| Family G | Regime / Volatility | ACTIVE_PREREGISTRATION |
-->

| Family | Research direction | Status |
|---|---|---|
| Family A | Medium-Term Momentum | PAUSED_PENDING_LATER_VALIDATION_DESIGN |
| Family B | Relative + Absolute Momentum | PAUSED_NO_VALIDATION_CANDIDATE |
| Family C | Breakout Continuation | PAUSED_NO_VALIDATION_CANDIDATE |
| Family D | Opening Range / Stocks-in-Play | PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE |
| Family E | Pullback / Reclaim | PAUSED_NO_VALIDATION_CANDIDATE |
| Family F | Catalyst Momentum | PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE |
| Family G | Regime / Volatility | PAUSED_NO_VALIDATION_CANDIDATE |

Family A is independent of the frozen Strategy V1/CAP4 research line. Its three original baselines and two Phase 2 experiments are frozen after partial Phase 2 support. Family A has promising DEVELOPMENT evidence but has not accessed validation and is paused pending a later validation design or a genuinely new hypothesis.

Family B is frozen after Commands 01–06. B001 closed as a redundant filter because all 302 top-decile candidates passed the frozen 6M >0 rule. B002 closed for insufficient distinct evidence because clean remediation left only one genuine below-SMA200 exclusion among 302 candidates. Family B did not access validation and did not create Strategy V2; it is paused with no validation candidate and no authorization for incremental parameter tuning.

Family C is frozen after Commands 01–06. The family result remains `MIXED`: `BRK-C-001` produced `CLEAR_POSITIVE` compression evidence at event level, but its executable portfolio was only `PARTIALLY_SUPPORTED`; the original breakout-strength ranking selected worse events, `C1-IMP-001` failed to improve implementation quality, and `BRK-C-002` failed. Family C is paused with no validation candidate. Its compression evidence is preserved as research evidence, validation was not accessed, and Strategy V2 was not created. Incremental threshold, capacity, ranking, sizing, holding-period, stop/target, gap, or combined-filter tuning is not authorized.

Family D is `PAUSED_DATA_BLOCKED_PENDING_BETTER_INTRADAY_SOURCE`. Its exact opening range, activity definition, entry/exit rules, capital/capacity, and success criteria remain frozen under `RESEARCH_EXPERIMENT_GOVERNANCE_V2`. Command 01 completed specification, preregistration, architecture, and structural pilots. Command 02 raised exact prior-20 continuity to 77.826177%, and Command 03 made 211 successful first-attempt exact Groww retry requests without recovering another required session. Because 1,069 of 4,821 targets remain incomplete, performance was not run, validation was not accessed, and Strategy V2 was not created. This is a data-blocked pause, not a strategy rejection, and no performance conclusion exists.

Family E is `PAUSED_NO_VALIDATION_CANDIDATE` as `STRATEGY_FAMILY_E_PULLBACK_RECLAIM_V1`. The control produced negative executable DEVELOPMENT return, CAGR, and expectancy and was weak/nonfatal. PBR-E-001 failed: requiring all pullback closes to remain at or above SMA50 removed a descriptively better cohort and did not improve executable results. Family E did not access validation and did not create Strategy V2. Incremental moving-average, pullback-window, reclaim, stop, holding-period, volume, or oscillator tuning is not authorized; future work requires a genuinely new independently justified architecture.

Family F Catalyst Momentum is `PAUSED_PENDING_AUTHORIZED_CATALYST_SOURCE` after `FAMILY_F_DATA_SOURCE_CLOSURE_V1`. Command 01 found that source acquisition was required. Command 02 demonstrated technically suitable NSE corporate-announcement timestamps and identity linkage in a bounded sample, but historical automated acquisition authorization remains unresolved; reproducible index notices were date-only and the remaining sources were inconclusive or access-restricted. Family F remains strategy-unevaluated and not preregistered. It may resume only after authorization, reproducible acquisition, and post-ingestion quality validation meet the frozen gates.

Family G Regime / Volatility is `PAUSED_NO_VALIDATION_CANDIDATE` as `STRATEGY_FAMILY_G_REGIME_VOLATILITY_V1`. `CONTROL-G-000` reproduced the strong Family A ₹500,000 quarterly momentum reference in DEVELOPMENT. The single preregistered `REGIME-G-001` quarterly NIFTY 500 close-above-SMA200 all-in/all-cash participation gate was `PARTIALLY_SUPPORTED` but was not advanced: it reduced exposure, costs, and annualized volatility while materially reducing return, worsening maximum drawdown, and worsening Sharpe-like performance. Both excluded quarters were profitable control intervals. This negative evidence applies only to the exact frozen gate and does not weaken Family A or support a general claim against SMA200 or market-regime research. Family G did not access validation and did not create Strategy V2; future Family G work requires a genuinely new independently justified and preregistered regime architecture.

`STRATEGY_DISCOVERY_FAMILIES_A_TO_G_STATUS = COMPLETE_FOR_CURRENT_RESEARCH_CYCLE`. This records completion of the planned A–G discovery pass, not selection of a final production strategy.

`NEXT_PLANNED_PHASE = CROSS_FAMILY_EVIDENCE_SYNTHESIS`. The next task may plan a comparison of positive, negative, and data-blocked evidence across Families A–G and determine whether any candidate merits a validation design or whether a genuinely new family is justified. No cross-family synthesis is performed by the Family G closure command.

Historical handoff state retained for lifecycle regression context: `| Family D | Opening Range / Stocks-in-Play | NEXT_PLANNED |`. This is not the current roadmap row.

Historical lifecycle state retained for regression context: Family D was `ACTIVE_PREREGISTRATION`, and Families E–G were `PLANNED_NOT_STARTED` before this closure. These are not current roadmap statuses.

<!-- Historical completed handoff state retained for prior-command regression assertions: | Family D | Opening Range / Stocks-in-Play | NEXT_PLANNED | -->
