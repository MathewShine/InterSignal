# Strategy Diagnostic Regime Context V1

## Scope and hypothesis

`STRATEGY_DIAGNOSTIC_REGIME_CONTEXT_V1` is Step 02.13 / Command 05 under `STRATEGY_DIAGNOSTIC_FRAMEWORK_V1` (`SWING_STRATEGY_DIAGNOSTICS_V1`). It asks whether frozen `MARKET_REGIME_V1` strength and its historically available inputs discriminate Strategy V1 opportunity paths and admitted-trade outcomes. It is descriptive, **HISTORICAL RESEARCH ONLY**, gross before costs, and ineligible for promotion.

The command consumes frozen feature, candidate, setup, regime, entry, Risk V1/V1.1, score, outcome, and portfolio ledgers. It does not recompute the regime, alter an admission, rerank opportunities, or run a portfolio variant.

## Frozen regime and score scales

The regime is `MARKET_REGIME_V1`, config hash `47ed769ec4115481`. Frozen target weights remain Nifty trend 30, Nifty 500 breadth 20, market-wide sector-index participation 15, Global/GIFT 15, India VIX 10, and intraday confirmation 10. Global/GIFT, VIX, and intraday confirmation are unavailable throughout the historical ledger, normally leaving 65% available weight and structurally capping confidence.

The upstream ledger contains `regime_score_raw`, the unnormalized sum of available signed contributions, and `regime_score_normalized`, the exact score used to classify Bullish at +30 or above, Neutral between −30 and +30, and Bearish at −30 or below. This command stores both. Because the requested regime-strength bands are on the published classification scale, every regime-strength, Neutral-position, and borderline bucket uses the frozen `regime_score_normalized`; no new model or score is calculated.

## Preregistered buckets

- Total normalized regime score: `<=−60`, `(−60,−30]`, `(−30,−10]`, `(−10,+10)`, `[+10,+30)`, `[+30,+50)`, `[+50,+70)`, `>=+70`.
- Bullish strength: `+30..<+45`, `+45..<+60`, `+60..<+75`, `>=+75`.
- Neutral position: `(−30,−10]`, `(−10,+10)`, `[+10,+30)`.
- Nifty trend contribution: `<=−20`, `(−20,−10]`, `(−10,+10)`, `[+10,+20)`, `>=+20`.
- Breadth contribution: `<=−12`, `(−12,−5]`, `(−5,+5)`, `[+5,+12)`, `>=+12`.
- Sector participation contribution: `<=−9`, `(−9,−3]`, `(−3,+3)`, `[+3,+9)`, `>=+9`.
- Effective R:R: `1.5..<2`, `2..<2.5`, `>=2.5`; gap: `<=0`, `0..<0.5%`, `>0.5%`.
- Causal current-state streak: 1, 2–3, 4–10, 11–20, and >20 sessions.
- Borderlines: Bullish +30..<+35, Neutral upper +25..<+30, Neutral lower −30..−25, and Bearish −35..−30.

All buckets and classification rules are stored before metric derivation. Empty and sparse buckets remain present.

## Populations and outcomes

Normal populations remain separate: 3,296 mechanically valid entry-eligible source opportunities, 728 admitted trades, and 2,398 max-position skips. Their Bullish and Neutral subsets are never merged without labels. The 324 Bearish exceptional-review rows and 28 unavailable preview rows are reported as separate research cohorts; they are not normal portfolio performance. Only valid-path members of those cohorts contribute MFE/MAE/path rates.

Opportunity metrics are four-session MFE_R, MAE_R, close return, and target-first/stop-first/neither. Admitted metrics add realized R, gross P&L, positive-gross-P&L rate, and target/stop/time exits. No combined fitness score is created.

## Components, interactions, and attribution

The Nifty trend, breadth, and sector contribution fields are exact upstream values. Sector participation is market-wide official sector-index participation, not stock-sector scoring. Component and total-score Pearson/Spearman correlations are descriptive only. Fixed interaction tables cover context × Strategy Score, setup quality, effective R:R, candidate stage, and gap. P&L attribution is the unchanged baseline portfolio grouped by preregistered buckets; no alternative portfolio is simulated.

## Confidence, boundaries, flips, and persistence

Existing `LOW`, `MEDIUM`, and `HIGH` confidence states are retained. Confidence is not a filter. Borderline rows include the next frozen regime state for descriptive transition reporting only. A date is near a flip when it is the change session from the immediately prior trading session or the immediately prior session to a next-session change. Future state is attached only after the frozen admission partition is preserved and is never entry information.

Regime streak uses only current and prior frozen states as of the decision date. It is diagnostic and does not create a persistence requirement, hysteresis, deadband, smoothing, or multi-session gate.

## Yearly stability and sample safety

The reports cover 2022, 2023, 2024, 2025, and partial 2026. They show state shares, median normalized score, strength/position distributions, component buckets, admissions, realized R, P&L attribution, and annual correlation direction. The 2023 comparison is descriptive and not causal.

Warnings are fixed: `<30 VERY_SMALL`, `30–99 SMALL`, `100–299 LIMITED`, and `>=300 ADEQUATE_FOR_DESCRIPTION`. Neutral admissions and sparse extremes must not be treated as rule-change evidence.

## Restrictions and future testing

No regime threshold, component weight, score regime points, entry rule, candidate/setup/risk rule, exit, maximum-position setting, or portfolio mechanic changes. Neutral is not excluded. There is no threshold search, reweighting, optimizer, predictive model, feature-importance model, promotion, live signal, order, migration, or Supabase write.

Any future regime-rule research requires a separate explicitly authorized and preregistered command. Command 05 stops at review.
