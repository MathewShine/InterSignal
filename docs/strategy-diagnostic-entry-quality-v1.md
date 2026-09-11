# Strategy Diagnostic Entry Quality V1

## Scope

`STRATEGY_DIAGNOSTIC_ENTRY_QUALITY_V1` is Step 02.13 / Command 03 under `STRATEGY_DIAGNOSTIC_FRAMEWORK_V1` (`SWING_STRATEGY_DIAGNOSTICS_V1`). It asks whether frozen Strategy V1 opportunities tend to arrive after material price extension or momentum maturity. It is **HISTORICAL RESEARCH ONLY**, descriptive, gross before costs, and ineligible for promotion.

The command consumes the frozen Daily Features, Momentum Candidates, Daily Setup Evaluation, Market Regime, Entry Evaluation, Risk Structure V1/V1.1, Strategy Score V1, Strategy Outcome V1, and Portfolio Backtest V1 artifacts. It derives entry-quality fields only in the diagnostic layer. It does not edit any baseline, generate an alternate equity curve, rerank an opportunity, reject or admit a trade, change scores, or create an entry filter.

## Pre-registration and finite experiment family

Exactly ten `ENTRY_QUALITY_DIAGNOSTIC` experiments are allowed:

| ID | Name | Fixed purpose |
|---|---|---|
| EXP-ENTRYQ-001 | BASELINE_ENTRY_QUALITY_PROFILE | Source/admitted/skipped/slot-skipped profile |
| EXP-ENTRYQ-002 | ATR_EXTENSION_BUCKETS | Fixed ATR extension bands |
| EXP-ENTRYQ-003 | BREAKOUT_DISTANCE_BUCKETS | Fixed percent-distance bands |
| EXP-ENTRYQ-004 | PRIOR_DAY_MOVE_BUCKETS | Fixed decision-day return bands |
| EXP-ENTRYQ-005 | MULTI_DAY_MOMENTUM_MATURITY | Separate 5d/10d/20d bands and maturity class |
| EXP-ENTRYQ-006 | GAP_X_PRIOR_MOVE_INTERACTION | Gap/prior-move matrix and maturity/gap subsection |
| EXP-ENTRYQ-007 | RVOL_X_EXTENSION_INTERACTION | Upstream RVOL state by ATR extension |
| EXP-ENTRYQ-008 | RS_X_EXTENSION_INTERACTION | Upstream benchmark-RS state by ATR extension |
| EXP-ENTRYQ-009 | SCORE_X_EXTENSION_INTERACTION | Frozen score 80–85 by ATR extension |
| EXP-ENTRYQ-010 | CANDIDATE_STAGE_X_EXTENSION | Candidate stage by extension and maturity |

The runner writes all definitions, bucket edges, reference priorities, maturity rules, classifications, parameter hashes, pre-registration hashes, and frozen dependencies before deriving metrics or inspecting results. Completed experiments are immutable. The suite contains no additional ID, numerical search, adaptive bucket, predictive model, automatic selector, or promotion path.

## Causal structural-reference hierarchy

The diagnostic reference is selected using this fixed hierarchy:

1. `SETUP_PRIOR_HIGH_20D_BREAKOUT_OR_RECLAIM_REFERENCE`: the frozen Setup `prior_high_20d`, available at the decision-day close and used as the general breakout/reclaim structure proxy.
2. `RISK_V1_1_TECHNICAL_INVALIDATION_ANCHOR`: the frozen selected technical invalidation level when the prior high is unavailable.
3. `RISK_V1_1_ENTRY_REFERENCE_PRICE`: the frozen decision-day entry reference as the final causal fallback.
4. `UNAVAILABLE`: retained explicitly if none of the above exists.

No future bar is used to select or calculate the reference. Breakout-distance reporting is restricted to rows using the prior-20-session-high structure; fallback references support general extension measurement but are marked unavailable for the breakout-specific table.

For actual frozen next-open entry `E`, structural reference `S`, and frozen ATR14 `A`:

`entry_extension_pct = (E / S - 1) × 100`

`entry_extension_atr = (E - S) / A`

Stop distance is independently recalculated from frozen entry and stop in percent and ATR units. Target headroom is independently reported as `(target − entry) / entry × 100` and `(target − entry) / initial_risk_per_share`. No alternate indicator is constructed.

## Locked descriptive buckets

ATR extension: `<0.5`, `0.5–<1`, `1–<1.5`, `1.5–<2`, `2–3` inclusive, and `>3 ATR`, plus `UNAVAILABLE`.

Breakout/reference distance: `≤1%`, `>1–2%`, `>2–3%`, `>3–5%`, `>5–8%`, and `>8%`, plus `UNAVAILABLE`.

Prior-day move: `≤0%`, `>0–2%`, `>2–4%`, `>4–6%`, `>6–8%`, and `>8%`, plus `UNAVAILABLE`.

Five-day return: `<3%`, `3–<6%`, `6–<10%`, `10–15%`, `>15%`. Ten-day return: `<5%`, `5–<10%`, `10–<15%`, `15–25%`, `>25%`. Twenty-day return: `<10%`, `10–<20%`, `20–<30%`, `30–50%`, `>50%`. Every dimension retains `UNAVAILABLE`.

Gap/prior interaction: gap `≤0`, `>0–0.5%`, `>0.5–1%`, `>1–2%`, `>2%`; prior move `≤2%`, `>2–4%`, `>4–6%`, `>6%`.

Realized-R bands are `≤−1R`, `>−1 to <−0.25R`, `−0.25 to +0.25R`, `>0.25 to 1R`, and `>1R`. MFE bands are `<0.5`, `0.5–<1`, `1–<1.5`, `1.5–<2`, and `≥2R`. Diagnostic MAE bands are `<0.25`, `0.25–<0.5`, `0.5–<1`, `1–<1.5`, and `≥1.5R`.

## Momentum maturity mapping

Maturity is derived only from frozen causal 5d/10d/20d returns and is not a strategy score:

- `EARLY`: 5d `<3%`, 10d `<5%`, and 20d `<10%`.
- `EXTENDED`: 5d `>15%`, or 10d `>25%`, or 20d `>50%`.
- `MATURE`: otherwise, 5d `≥10%`, or 10d `≥15%`, or 20d `≥30%`.
- `DEVELOPING`: all other fully available combinations.
- `UNAVAILABLE`: one or more required returns are unavailable.

This mapping was fixed before outcome aggregation and cannot be treated as a new entry rule.

## Population and outcome conventions

The population is exactly the 3,296 mechanically valid frozen primary opportunities. Frozen Portfolio Backtest V1 identifies exactly 728 admitted trades and 2,568 skipped opportunities. `SKIP_MAX_POSITIONS` identifies the slot-skipped comparison. Command 03 neither changes these assignments nor simulates alternative admissions.

Source-level path evaluation uses frozen Strategy Outcome V1 MFE/MAE and target-first/stop-first/neither fields. Realized R, gross P&L, and target/stop/time exits are attached only to the 728 actually admitted baseline trades. This distinction is retained in every bucket table.

RVOL categories (`WEAK`, `NORMAL`, `GOOD`, `STRONG`, `EXCEPTIONAL`) and RS categories (`WEAK`, `NEUTRAL`, `POSITIVE`, `STRONG`) come directly from the frozen Setup evaluation rather than being re-estimated. Candidate categories remain `EMERGING_ONLY`, `CONFIRMED_ONLY`, and `BOTH_ELIGIBLE`.

## Associations and classifications

Pearson and tied-rank Spearman correlations describe score association with ATR extension, prior-day return, 5d/10d/20d returns, target distance percent/R, and effective R:R for both source and admitted populations. No significance test, predictive regression, machine learning, or p-value-based selection is performed.

`ENTRY_EXHAUSTION_RESULT` requires consistency across five predeclared comparisons: remaining MFE, realized R, stop-first rate, target headroom, and mature-versus-early MFE. Four or five supporting comparisons is `STRONG_ASSOCIATION`; three is `MATERIAL_ASSOCIATION`; one or two is `MIXED`; zero is `NO_CLEAR_EVIDENCE`; required cohorts under 30 are `INCONCLUSIVE`.

The score, gap, RVOL, RS, and candidate-stage classifications likewise use the exact pre-registered rules stored in the registry and summary. These structural labels are diagnostic associations, not recommendations. If exhaustion reaches material or strong consistency, the only permissible flag is `ENTRY_EXHAUSTION_HYPOTHESIS_SUPPORTED_FOR_LATER_TESTING`; it still does not authorize a Strategy V1 change.

Sample flags are fixed: fewer than 30 `VERY_SMALL`, 30–99 `SMALL`, 100–299 `LIMITED`, and at least 300 `ADEQUATE_FOR_DESCRIPTION`. `CONFIRMED_ONLY`, Neutral regime, and sparse interaction cells must be interpreted with their emitted warnings.

## Pilot, reproducibility, and storage

Before full aggregation, the runner validates fourteen real frozen examples: low/moderate/high extension, large prior move, mature momentum, specified score/extension combinations, strong RVOL/RS extension, Emerging and Both-eligible stages, and baseline stop/target/time exits. The pilot records the reference, ATR, entry, both extension values, prior/multi-day returns, gap, RVOL/RS, outcomes, and assigned bucket.

Every experiment runs twice from its locked definition with before/after frozen-hash guards. Canonical tables must match. Command 03 artifacts live under `data/research/diagnostics/strategy/v1/entry_quality_command_03/`, separate from Commands 01 and 02. Ten completed records are appended to the shared registry only after verifying that the prior 19 parameter and pre-registration hashes remain unchanged, yielding exactly 29 records.

## Research restrictions and limitations

This command creates no chase filter or other entry filter, changes no score threshold or weight, and changes no ranking, stop, target, holding horizon, risk, maximum positions, or portfolio mechanics. It performs no live action and writes nothing to a broker, database, migration target, or Supabase.

The analysis is observational. Associations can reflect setup construction, candidate eligibility, ranking, regime, or other confounding structure and do not establish causality. The prior 20-session high is a broad structural proxy rather than a unique setup-specific breakout level. Results remain historical and gross before costs and slippage. Any follow-up requires a separately pre-registered later experiment; Command 03 itself stops at review.
