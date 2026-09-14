# Family C C001 Controlled Implementation Research V1

## Command boundary

Step 03.03 / Command 04 creates `FAMILY_C_C001_IMPLEMENTATION_RESEARCH_V1`, a preregistration, implementation architecture, and structural-pilot package. It does not run C1-IMP-001 performance and does not access validation.

Exactly one implementation experiment is registered:

- ID: `C1-IMP-001`
- Name: `C001_COMPRESSION_PRIORITY_CAPACITY_RANKING_V1`
- Family: `FAMILY_C`
- Reference control: frozen `BRK-C-001`
- Status: `PREREGISTERED`
- Promotion allowed: `false`

The hypothesis is not treated as proven. It asks whether tighter-compression priority can deploy the already-demonstrated C001 signal more effectively than the frozen breakout-strength priority when valid signals exceed available slots.

## Why this experiment exists

The frozen C001 attribution audit found:

- `C001_SIGNAL_QUALITY_ATTRIBUTION = CLEAR_POSITIVE`
- `C001_SIGNAL_TEMPORAL_CONSISTENCY = MOSTLY_CONSISTENT`
- `C001_DEVELOPMENT_ADVANTAGE_ATTRIBUTION = PRIMARILY_COMPRESSION_SIGNAL`
- `C001_CAPACITY_SELECTION_QUALITY = SELECTED_WORSE`
- `BREAKOUT_STRENGTH_CAPACITY_RANKING_RESULT = NO_DISCRIMINATION`
- frozen capacity rejection rate: 61.7848%

Frozen admitted C001 events had a 49.8291% normalized event win rate, +0.2132% normalized event expectancy, and 1.0897956256 PF. Capacity-rejected events had 52.6677%, +0.6139%, and 1.3140019101 respectively. These findings motivate a separately preregistered implementation hypothesis; they do not establish that compression-priority ranking will improve the executable portfolio.

The frozen attribution hash is `26a320930facd5c3007a75e22573e27171d6e85cb6a4ea02dc209e6975a38e4b`.

## Frozen signal and portfolio mechanics

C1-IMP-001 uses exactly the frozen BRK-C-001 signal and mechanics:

- close at T strictly greater than the maximum adjusted high from T-20 through T-1;
- ten-session compression range divided by formation close at or below exactly 8%;
- signal at T close and entry at T+1 eligible open;
- ten completed holding sessions and exit at the next eligible open;
- ₹500,000 starting capital;
- 5% of current portfolio equity target notional;
- whole shares, retained cash, no leverage;
- maximum 20 concurrent positions;
- one open position per symbol and no pyramiding;
- no stop, target, trailing exit, intraday confirmation, volume filter, or gap filter;
- frozen India cash-equity cost model and 5 bps per-side slippage.

The 4,247 valid pre-capacity C1-IMP-001 signals are exactly equal to the 4,247 frozen C001 valid pre-capacity signals. There are no missing, extra, or field-mismatched events. Their frozen `c001_signal_set_hash` is `096a11a85a72138176fb02b28efec52030e00c819c1bc67bca6fd8ae41abce9f`.

## Only experimental change

The reference BRK-C-001 same-day capacity ranking is:

- `BREAKOUT_STRENGTH_PCT` descending;
- symbol ascending.

C1-IMP-001 changes only that order to:

- `COMPRESSION_RANGE_PCT` ascending;
- `BREAKOUT_STRENGTH_PCT` descending;
- symbol ascending.

The ordering is deterministic and lexicographic. It does not use a continuous score, weighted combination, alternate threshold, second ranking variant, or any new signal input.

## Structural pilots

The synthetic pilot contains more candidates than slots and verifies all three keys. Its exact order is DELTA, BRAVO, ALPHA, CHARLIE, ECHO: tighter compression wins first; equal compression is resolved by higher breakout strength; equal compression and breakout strength are resolved by symbol ascending.

Five real capacity-constrained DEVELOPMENT dates were selected structurally by high candidate load, excluding days with frozen affordability rejections:

- 2023-04-28
- 2023-05-02
- 2023-11-30
- 2023-12-01
- 2023-12-04

Across 163 candidate rows, compression-priority ordering changes 18 row-level selection states: nine frozen admissions become hypothetical capacity rejections and nine frozen capacity rejections become hypothetical slot selections. The pilots report symbols, compression, breakout strength, old rank, new rank, old admission status, and hypothetical new slot status.

These pilots do not simulate affordability or portfolio path, and calculate no trade returns, ending equity, CAGR, drawdown, or strategy result. Their sole purpose is to prove the ranking implementation and demonstrate that it makes non-trivial ordering changes on real frozen signal sets.

## Frozen future metrics

A separately authorized controlled DEVELOPMENT evaluation must report net total return, net CAGR, max drawdown, position win rate, net expectancy, net PF, average winner, average loser, turnover, transaction costs, capacity rejection rate, average concurrent positions, average cash, and 2022/2023/2024 returns.

It must also report admitted and rejected normalized event expectancy and PF plus admitted-minus-rejected win-rate, expectancy, and PF differences.

## Frozen numerical criteria

Capacity quality passes only if at least two of three admitted-quality dimensions improve materially against exact stored C001 references:

- admitted normalized event expectancy must be at least 1.15 times the frozen value;
- admitted normalized event PF must be at least the frozen value plus 0.05;
- admitted normalized event win rate must improve by at least 3 percentage points.

The remaining standard criteria are:

- portfolio net expectancy above zero and PF at least 1.10;
- net CAGR at least 90% of frozen C001 net CAGR;
- max drawdown may not worsen by more than 10% relatively;
- at least two of three years must be nonnegative, with more than 10 percentage points of reference underperformance in no more than one year;
- normalized cost drag may not exceed 120% of the frozen value;
- at least 500 closed positions for normal interpretation, 250–499 as limited sample, and below 250 as fatal;
- all accounting and data-integrity checks must pass.

The exact reference values and formulas are stored in the hashed success-criteria record.

## Future classification

`STRONGLY_SUPPORTED` requires all A–H, improvement on all three admitted-quality dimensions, net CAGR above frozen C001, and PF of at least 1.15.

`SUPPORTED` requires all A–H and at least two admitted-quality improvements. `PARTIALLY_SUPPORTED` requires no fatal failure, at least six A–H passes, and at least one admitted-quality improvement. `FAILED` applies on a fatal condition, fewer than six A–H passes, or clear worsening on at least two admitted-quality dimensions. `INCONCLUSIVE` is reserved for unresolved mechanics or data.

The 60% high-win-rate flag remains descriptive and is not a mandatory success criterion.

## Frozen architecture hashes

| Record | Hash |
|---|---|
| Implementation research config | `d9de8dbbf0e288066565fcf9a4ef2b4cd494ed3f07760529298669226a119662` |
| C1-IMP-001 parameters | `6a5b49423e3fb30c708c9e1ae6a7cf5a5c0cf7306666d4f35f7428123d36915c` |
| C1-IMP-001 preregistration | `a5939b4d11282d0c8e40a2e1d9cebde79d8b62bf5d4a315adfcb8f853c366c7a` |
| Implementation success criteria | `90365ad9e45328a918bb714e03df78dfc049c0e335e9c6893216594c690978c0` |
| C001 signal set | `096a11a85a72138176fb02b28efec52030e00c819c1bc67bca6fd8ae41abce9f` |

Governance V2 passes 14 of 14 checklist items. `C1_IMP_001_ARCHITECTURE_RESULT = READY_FOR_CONTROLLED_DEVELOPMENT_TEST`.

## Governance status

The Family C roadmap status is `ACTIVE_CONTROLLED_IMPLEMENTATION_RESEARCH`. Family A and Family B closure states are unchanged, and Families D–G remain unstarted.

No C1-IMP-001 performance has run. No 2025 or validation data was accessed. No Strategy V2 was created. The next step requires a separate explicit command to run exactly one controlled DEVELOPMENT evaluation against frozen BRK-C-001.
