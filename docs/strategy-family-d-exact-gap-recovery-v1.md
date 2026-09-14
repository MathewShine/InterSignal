# Family D exact prior20 gap recovery v1

## Purpose

Command 02 reached 77.82617714167185231279817465% exact prior20 continuity, below the frozen 95% gate for a bounded Family D development evaluation. This command therefore retried only the immutable population of 217 defective required symbol-sessions. It did not change Family D, weaken prior20, substitute older sessions, run performance, or access validation.

## Exact population and Groww retry

The population contained 105 `MISSING_OPENING_BARS`, 48 `PROVIDER_HISTORY_UNAVAILABLE`, and 64 `SESSION_QUALITY_FAILURE` cases. Its hash is `504a0e88f6e4f5399a906d84c562010dbcebc333d4503e04821cc0f646eed2d5`. Nearby same-symbol gaps were deduplicated into 211 bounded requests of no more than 7 calendar days through `GROWW_RETRIEVAL_TRANSPORT_V1_1`. Every missing-opening case explicitly required 09:15, 09:20, and 09:25; partial openings remained unresolved. No bar was synthesized.

Groww exact retry recovered 0 sessions. Identity correction recovered 0; no unsupported alias was invented. The versioned layer `FAMILY_D_EXACT_GAP_RECOVERY_DATA_V1` stores complete source lineage and uses one source per symbol-session. Existing Command 05B and Command 02 rows were not overwritten.

## Alternate-source gate and reconciliation

The repository audit result is `NO_APPROVED_ALTERNATE_SOURCE`. The approved provider pilot states that Zerodha/Kite had no credentials or configured adapter and was not contacted, while generic CSV and NSE daily-file adapters are not an approved real intraday source. Therefore no new provider was contacted and unresolved gaps are classified `ALTERNATE_SOURCE_AUTHORIZATION_REQUIRED`.

Exact overlapping Groww rows were compared across timestamp and OHLCV. There were 6986 overlap rows, 0 explained differences, and 0 unexplained differences. Alternate-source volume compatibility is `INCONCLUSIVE` because no alternate rows were authorized or used.

## Continuity and readiness

After recovery, 3752 of 4821 targets have all exact immediately preceding 20 strict sessions (77.82617714167185231279817465%, `INSUFFICIENT`). 1069 remain incomplete. Remediable coverage is 85.89743589743589743589743590%; only targets blocked exclusively by project-recorded special sessions are excluded from that secondary diagnostic, and the ordinary 95% gate is not relaxed.

The frozen structural control count remains 2292 and D001 subset violations are 0. No trade P&L, win rate, expectancy, profit factor, equity, drawdown, CAGR, or other outcome measure was computed.

`FAMILY_D_EXACT_GAP_RECOVERY_RESULT`: `ALTERNATE_SOURCE_AUTHORIZATION_REQUIRED`
`FAMILY_D_DATA_READINESS`: `BLOCKED`
`FAMILY_D_DEVELOPMENT_BACKTEST_READINESS`: `NO`

The next action is `REVIEW_RECOVERY_AND_SEPARATELY_AUTHORIZE_AN_APPROVED_HISTORICAL_NSE_INTRADAY_SOURCE_FOR_EXACT_UNRESOLVED_GAPS`. A separate explicit authorization is required before any alternate-provider retrieval or performance command.
