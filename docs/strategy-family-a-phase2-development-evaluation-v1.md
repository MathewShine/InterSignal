# Family A Phase 2 Development Evaluation V1

## Frozen scope

`FAMILY_A_PHASE2_DEVELOPMENT_EVALUATION_V1` evaluates exactly the two experiments preregistered under `FAMILY_A_PHASE2_RESEARCH_V1` / `MOMENTUM_IMPLEMENTATION_EFFICIENCY_V1`. Before evaluation, the runner verifies the Phase 2 config hash, both parameter and preregistration hashes, and the immutable MOM-A-002 Command 02 result hash. A mismatch stops with `FAMILY_A_PHASE2_FREEZE_MISMATCH`.

Only the 2022-01-01 through 2024-12-31 DEVELOPMENT partition is loaded. No 2025+ data, Family A validation data, database, Supabase, broker, or live execution path is used.

## A2-001 — retention-band evaluation

A2-001 preserves 6M compounded momentum, quarterly rebalancing, top-10% entry, equal weighting, ₹100,000 capital, long-only direction, and the frozen cost model. Existing executable holdings remain eligible through the top 15%; a rank outside the top 15% or any mandatory eligibility failure causes exit. Replacement is deterministic from current top-10% candidates. The resolver uses actual positive-share holdings at each rebalance, not merely the prior intended list.

Relative to frozen MOM-A-002, annualized turnover fell from 3.9274x to 3.5129x (about 10.55%) and modeled cost fell from ₹5,800.01 to ₹5,379.46 (about 7.25%). Average retention rose from 33.81% to 41.87%. Net return was 72.21% versus 77.23%, while maximum drawdown moved from -21.32% to -22.25%. All three calendar years remained positive and rebalance success remained 80%.

The frozen classification policy labels turnover/cost improvement material at at least 25%/20%, moderate at 15%/10%, and minor when both improve but remain below those thresholds. Performance is preserved when return, CAGR, drawdown, yearly breadth, and rebalance success jointly remain inside the documented guardrails; it is modestly degraded when broader, still non-material guardrails hold. On those multi-metric rules, A2-001 is `MINOR_IMPROVEMENT`, `MODEST_DEGRADATION`, and `PARTIALLY_SUPPORTED`.

## A2-002 — ₹500k capital-fidelity evaluation

A2-002 runs the exact frozen MOM-A-002 selections, prices, 6M signal, quarterly schedule, top decile, equal weighting, execution, and costs. Starting capital is the only changed parameter: ₹100,000 becomes ₹500,000. Raw rupee profit is not treated as evidence of alpha; strategy-quality comparisons use percentage returns and normalized behavior.

Average cash fell from 13.12% to 2.65%, average L1 tracking difference fell from 13.15% to 2.69%, and unaffordable selection instances fell from 17 to zero. The ₹500k executable produced 91.07% net return, 24.11% net CAGR, -22.92% maximum drawdown, and 80% rebalance success. Its percentage behavior moved materially closer to the idealized portfolio, while a remaining net-return gap means the fidelity label is `IMPROVED_BUT_MATERIAL_GAP`, not an alpha claim.

Capital improvement is material only when cash, mean weight error, and L1 tracking error each improve by at least 40% and unaffordable instances decline. Distortion reuses the frozen cash/L1 thresholds. A2-002 is therefore `MATERIAL_IMPROVEMENT`, `LOW_DISTORTION`, and `SUPPORTED`.

## Costs, accounting, and yearly stability

Costs are reported in rupees, as a percentage of initial capital, as a percentage of average net equity, per rebalance, and per unit turnover. The ₹100k and ₹500k comparisons use normalized cost rates because larger capital naturally produces larger rupee notionals. Every rebalance reconciles prior cash plus sale proceeds, less sell costs, purchases, and buy costs, to new cash. Daily equity reconciles cash plus market value. Both experiments have zero unexplained accounting or equity violations.

Separate 2022, 2023, and 2024 rows report net return, drawdown, turnover, cost drag, rebalance success, cash, and weight error. Both experiments are `CONSISTENT` because all three development years are positive.

## Interpretation and governance

A2-001 and A2-002 answer different questions. A2-001 tests turnover reduction with performance preservation; A2-002 tests implementation fidelity at practical capital. No combined retention-plus-₹500k experiment was run, no overall winner was selected, and no alternative band, capital, signal, regime, stop, target, or intraday rule was tested.

The combined Family A Phase 2 result is `PARTIAL_SUPPORT`: A2-002 is supported, while A2-001 is only partially supported. The next-stage recommendation is `CONTINUE_CONTROLLED_DEVELOPMENT`. This does not authorize validation. A separate human-approved command remains mandatory, and no Strategy V2 is created here.
