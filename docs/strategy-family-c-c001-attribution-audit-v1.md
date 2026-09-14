# Family C C001 Attribution Audit V1

## Scope and purpose

This document records Step 03.03 / Command 03, `FAMILY_C_C001_ATTRIBUTION_AUDIT_V1`, under profile `COMPRESSION_BREAKOUT_CAPACITY_ATTRIBUTION_V1`.

The audit was required because Family C finished its frozen DEVELOPMENT evaluation with a `MIXED` result: the control was not viable, BRK-C-001 was `PARTIALLY_SUPPORTED`, and BRK-C-002 failed. The command separates the quality of C001's frozen compression signal from the admissions and path dependence of its ₹500,000, 20-position executable portfolio.

This is not a new strategy experiment. Event-level replay output is labeled `ATTRIBUTION_REPLAY_NOT_STRATEGY_EXPERIMENT`, and the all-signal dataset is labeled `SIGNAL_QUALITY_COHORT_ONLY`. Simultaneous cohort events are observations and are not represented as simultaneously deployable positions.

## Frozen inputs

All inputs passed the pre-run hash gate:

| Input | Frozen hash |
|---|---|
| Family config | `5ecb5604939e1230ba176dbb339ebaf15418482da7a68bbbea24370c805961a6` |
| Success criteria | `7bb950274ebe47ec7fafeb7e8659e07a457a4ddb169171aa97fe9ff9d0860a77` |
| CONTROL-C-000 result | `efdf9ccdf70f4c58d1ce40e2f1e1ccb7e7fa8ad83c5fb3832ce0994d323b991f` |
| BRK-C-001 result | `8adc1aec00041256748a8fa086b4dae562a6841b844875fc39b3dd19b61680e4` |
| BRK-C-002 result | `49afe8ee5d766afa9a0e01195fa49041605c71483df0de9ac4c354b469a9a240` |
| Development registry | `529322157a13058f0e2f73e88d471b5f15e006b8eae1c1050a0110b77d6345bc` |

The audit used only 2022-01-01 through 2024-12-31. No validation or post-2024 price was accessed. Family C Command 01 and Command 02 artifacts were hashed before and after the audit and remained unchanged.

## Event cohort and normalized cost

The cohort contains every infrastructure-eligible CONTROL-C-000 breakout with a complete frozen T+1-open entry, ten completed-session holding path, and next-open exit inside DEVELOPMENT. It contains 12,208 unique events: 4,247 pass the exact frozen `compression_range_pct <= 0.08` rule and 7,961 fail it. Every C001 event is a control breakout; subset violations are zero.

Each event reports gross return and an estimated normalized net return. Net return uses a fixed ₹25,000 reference entry notional, the frozen `INDIA_EQUITY_COST_MODEL_V1` / `NSE_CASH_DELIVERY_RESEARCH_V1` / `COST-SCENARIO-002` model, and 5 bps per-side slippage. It does not model portfolio cash interactions.

## Compression signal quality

| Metric | Compression pass | Compression fail | Pass minus fail |
|---|---:|---:|---:|
| Events | 4,247 | 7,961 | — |
| Win rate | 51.4245% | 48.0342% | +3.3904 pp |
| Net expectancy | +0.4394% | +0.1458% | +0.2936 pp |
| Net profit factor | 1.2108 | 1.0502 | +0.1606 |
| Median net return | +0.1603% | -0.3188% | +0.4790 pp |
| Median MFE | +3.6585% | +4.8311% | -1.1726 pp |
| Median MAE | -3.5804% | -4.9470% | +1.3666 pp |

`C001_SIGNAL_QUALITY_ATTRIBUTION = CLEAR_POSITIVE`.

Compression-pass events give up some median upside excursion but materially reduce median adverse excursion and improve the realized ten-session distribution. Their gross mean return is 0.8281%; the normalized net expectancy after frozen friction is 0.4394%, leaving a positive result after approximately 0.3887 percentage points of modeled cost drag.

## Temporal evidence

| Formation year | Pass events | Pass expectancy | Pass PF | Fail events | Fail expectancy | Fail PF |
|---|---:|---:|---:|---:|---:|---:|
| 2022 | 989 | -0.4660% | 0.8233 | 2,058 | -0.7843% | 0.7682 |
| 2023 | 2,050 | +0.9805% | 1.5914 | 2,547 | +1.2013% | 1.5577 |
| 2024 | 1,208 | +0.2622% | 1.1114 | 3,356 | -0.0849% | 0.9733 |

Compression-pass expectancy exceeds compression-fail expectancy in 2022 and 2024, but not in 2023. The direction is therefore `C001_SIGNAL_TEMPORAL_CONSISTENCY = MOSTLY_CONSISTENT`, not fully consistent.

## Frozen admissions and capacity

The attribution replay reconciles all 4,292 C001 signals to the frozen Command 02 portfolio: 4,247 entry-ready, 1,170 admitted, 2,624 capacity rejected, 408 already open, 45 affordability rejected, 38 terminal unavailable, three other incomplete paths, and four final-formation signals with no T+1 DEVELOPMENT session.

| Event metric | Admitted | Capacity rejected | Admitted minus rejected |
|---|---:|---:|---:|
| Count | 1,170 | 2,624 | — |
| Win rate | 49.8291% | 52.6677% | -2.8386 pp |
| Median normalized net return | -0.0052% | +0.3304% | -0.3356 pp |
| Net expectancy | +0.2132% | +0.6139% | -0.4007 pp |
| Net PF | 1.0898 | 1.3140 | -0.2242 |

`C001_CAPACITY_SELECTION_QUALITY = SELECTED_WORSE`.

The admitted event win rate above uses normalized event costs; the frozen portfolio-admitted win rate remains 49.7436% under actual whole-share notionals and costs.

On 283 formation dates with both admitted and capacity-rejected events, the pooled same-day admitted-minus-rejected differences are -3.7943 percentage points of win rate, -0.4814 percentage points of median return, -0.2362 percentage points of expectancy, and -0.1753 PF. Market-day matching therefore does not explain away the inferior admitted cohort.

## Ranking quality

The frozen same-day ranking is breakout strength descending, then symbol ascending. Across capacity-constrained ranked sets, normalized event expectancy by within-day quartile was:

| Same-day rank quartile | Events | Win rate | Net expectancy | Net PF |
|---|---:|---:|---:|---:|
| Top | 958 | 50.8351% | +0.6080% | 1.2661 |
| Second | 778 | 52.8278% | +0.8434% | 1.4476 |
| Third | 868 | 52.6498% | +0.2642% | 1.1294 |
| Bottom | 675 | 52.1481% | +0.7059% | 1.3886 |

The sequence is non-monotonic and the top quartile does not beat the bottom quartile. `BREAKOUT_STRENGTH_CAPACITY_RANKING_RESULT = NO_DISCRIMINATION`.

## Capacity pressure and portfolio-state dependence

| Year | Valid signals | Admitted | Capacity rejected | Rejection rate | Constrained days |
|---|---:|---:|---:|---:|---:|
| 2022 | 989 | 308 | 536 | 54.1962% | 77 |
| 2023 | 2,050 | 455 | 1,439 | 70.1951% | 162 |
| 2024 | 1,208 | 407 | 649 | 53.7252% | 117 |

Immediately before processing C001 entries, the executable portfolio averaged 15.3842 open positions; the median was 17 and p90 was 20. Across 622 entry days, 46.7846% began with at least 18 positions and 11.8971% began exactly full. The frozen overall capacity-rejection rate remains 61.7848%.

Signal-load diagnostics reinforce the distortion: admission rates fall from 56.7691% on 1–5-signal days to about 8% on days with more than 20 signals. Higher-load cohorts have stronger event expectancy, reaching +3.1090% for the 31+ bucket, yet most such signals cannot be admitted.

`C001_CAPACITY_EFFECT_MATERIALITY = MATERIAL`.

## Holding path

Average/median gross return after 1, 3, 5, and 10 completed sessions:

| Horizon | Compression pass | Compression fail |
|---|---:|---:|
| 1 | -0.2223% / -0.2615% | -0.2404% / -0.3723% |
| 3 | -0.0821% / -0.1637% | -0.1839% / -0.4323% |
| 5 | +0.1051% / -0.0810% | -0.0417% / -0.3801% |
| 10 | +0.6513% / +0.4336% | +0.2665% / -0.1093% |

These values diagnose continuation development only. They do not create alternate exits or alter the frozen ten-session hold.

## Breakout-strength and entry-gap context

Compression-pass expectancy exceeds compression-fail expectancy in four of five breakout-strength buckets: 0–1%, 1–2%, 3–5%, and above 5%. The exception is 2–3%. This indicates that compression generally adds information beyond raw breakout strength, while remaining non-uniform.

Compression-pass expectancy exceeds compression-fail expectancy in all five entry-gap buckets. The greater-than-3% pass bucket contains only 33 events, so its large observed expectancy is descriptive and not a basis for a gap filter.

The compression-range distribution for all 12,208 complete control events is p10 5.3718%, p25 7.0502%, median 9.5572%, p75 12.9647%, and p90 17.0245%. For the 1,170 admitted C001 positions it is p10 4.4052%, p25 5.3274%, median 6.3567%, p75 7.2025%, and p90 7.7189%. No alternate compression cutoff was tested.

## Win-rate, costs, and attribution

The event-level compression-pass win rate is 51.4245%, the frozen portfolio win rate is 49.7436%, and the capacity-rejected event win rate is 52.6677%. None reaches 60%, so `C001_60PCT_WIN_RATE_OBSERVED = NO`. The 60% threshold remains descriptive and was not optimized toward.

The frozen portfolio findings remain turnover of 112.1057736468 times starting equity and ₹109,155.36 of modeled costs. The all-signal compression edge remains positive after the frozen normalized friction model, but the executable admission process loses a meaningful portion of that signal-quality advantage.

`C001_DEVELOPMENT_ADVANTAGE_ATTRIBUTION = PRIMARILY_COMPRESSION_SIGNAL`. Capacity does not manufacture the edge; it harms realized selection. C002 remains `FAILED`, with `C002_RESEARCH_STATUS = DEPRIORITIZED`, and was not reevaluated.

## Governance and next stage

No strategy, parameter, stop, target, trailing rule, intraday confirmation, combined filter, alternate holding period, alternate compression threshold, or alternate capacity was created or tested. The frozen 20-day breakout, 10-day compression window, 8% cutoff, ten-session hold, ₹500,000 capital, 5% target notional, and 20-position limit are unchanged.

No stop or target is inferred from MFE/MAE, and no 1/3/5-session path is treated as an alternate exit. No validation data was accessed. No Strategy V2 or Family D work was started.

Because compression signal quality is clearly positive but the frozen portfolio selects worse opportunities under material capacity pressure, `FAMILY_C_C001_NEXT_STAGE = PREREGISTER_NEW_C001_IMPLEMENTATION_HYPOTHESIS`. This recommendation requires a separate command and preregistration; it is not implemented here and does not authorize validation access.

The frozen audit hash is recorded in `data/research/strategy_families/family_c/v1/c001_attribution_audit/manifests/family_c_c001_attribution_result_v1.json` and the machine-readable summary.
