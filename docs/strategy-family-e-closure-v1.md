# Strategy Family E Research Closure V1

## Rationale and final status

Family E tested one frozen daily trend/pullback/reclaim control and one isolated SMA50-structure treatment. The DEVELOPMENT result was `MIXED`, but neither configuration produced positive executable evidence suitable for validation. The family is therefore `PAUSED_NO_VALIDATION_CANDIDATE`; its evidence status is `PULLBACK_RECLAIM_V1_NOT_SUPPORTED`.

## Control and treatment

`CONTROL-E-000` closed as `CLOSED_WEAK_NONVIABLE_CONTROL`. It returned -0.111087614 net with CAGR -0.03849181436177762, expectancy -0.0005557382080185902957385890056, PF 0.9164213428916390956743853995, and only one positive DEVELOPMENT year. It was nonviable but did not trigger a frozen fatal condition.

`PBR-E-001` closed as `CLOSED_FAILED_DEVELOPMENT`. It produced CAGR -0.042244485864179726, expectancy -0.001591029223899589418739234400, PF 0.9100378319999767608767492316, and passed four of seven standard criteria.

## Failed SMA50-structure hypothesis

The filtered-out cohort contained 2365 complete events with win rate 0.4748414376321353065539112051, expectancy 0.004387781636205847273216909032, and PF 1.169664673116664250764126489. The retained cohort contained 8183 events with win rate 0.4448246364414029084687767322, expectancy 0.0005468048785054629092716720023, and PF 0.9834301638892258266589878744. Attribution is `NEGATIVE`: the filter removed the descriptively stronger cohort.

## Descriptive lessons

All stop exits were losing and time exits had approximately a 59.5% win rate. This is descriptive attribution only. Stop removal was not tested and is not authorized. Capacity rejection was material at approximately 85.10% for the control and 80.94% for E001, but capacity pressure does not rescue the negative control expectancy or PF. Win rates were 44.6341% and 44.2118%; the 60% aspiration was not achieved, and conclusions were not changed to chase it.

Pullback-depth, reclaim-strength, entry-gap, stop-distance, MFE/MAE, holding-path, exit-attribution, and capacity reports remain preserved for cross-family research.

## Governance and handoff

Validation was not accessed and Strategy V2 was not created. Family E V1 cannot continue through incremental moving-average, pullback-window, reclaim, stop, holding-period, volume, or oscillator tweaks. Future Family E work requires a genuinely new independently justified and preregistered architecture.

Family F Catalyst Momentum is next planned for data-readiness assessment only. Its high-level concept is external/corporate catalyst plus price confirmation, volume confirmation, and continuation behavior. No parameters are defined and implementation has not started. Historical catalyst/news/event coverage must be assessed for source reliability, timestamp semantics, and point-in-time availability before preregistration.

Closure hash: `4899cdbfe54b0ea636faa8ff0b4504b6ef60242e7eabdf682b2b913cfb001c00`. This closure is research-only and makes no live, validation, or deployment claim.
