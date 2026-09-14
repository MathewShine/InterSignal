# Family D intraday continuity remediation v1

## Purpose

Family D was data-blocked because the frozen 5-minute dataset sampled DEVELOPMENT sessions but did not retain every immediately preceding market session needed by the preregistered opening-activity denominator. Sparse sampled sessions cannot stand in for the exact prior 20 sessions.

## Frozen method and scope

`FAMILY_D_INTRADAY_CONTINUITY_REMEDIATION_V1` / `PRIOR20_OPENING_VOLUME_CONTINUITY_V1` preserves the exact 100-symbol Family D scope and 4821 target symbol-sessions. For target session T, the baseline uses only the authoritative NSE sessions T-20 through T-1. Each baseline session must be strict and contain exactly the 09:15, 09:20, and 09:25 bar volumes; their sum is `opening_15m_volume`, and the denominator is the median of the 20 sums. No older replacement, current-session denominator input, future session, inferred volume, or daily-volume proxy is permitted.

## Retrieval and versioned extension

The deterministic plan was frozen before network access. Existing frozen normalized rows and auditable collateral rows inside immutable Command 05B Groww responses were reused first. Only remaining required symbol-sessions were grouped into conservative, deduplicated windows of at most 30 calendar days and requested through `GROWW_RETRIEVAL_TRANSPORT_V1_1` (10s connect, 20s read, 30s wall clock, bounded retries, circuit breaker, one-request-per-second policy). New responses live only under the versioned Family D raw extension; normalized rows use `NSE_CASH_INTRADAY_5M_V1`, Asia/Kolkata, BAR_START semantics. No Command 05B raw, normalized, derived, or manifest artifact was overwritten.

## Reconciliation and coverage

Overlaps were joined by symbol and timestamp and classified as exact, source-equivalent, explained provider difference, or unexplained difference. The reconciliation result is `PASS`. The extension added 910403 raw rows and 1035161 normalized rows.

Complete exact-prior20 continuity is available for 3752 of 4821 targets (77.82617714167185231279817465%), classified `INSUFFICIENT`. Remediable coverage excluding genuine `SYMBOL_NOT_LISTED` cases is 77.82617714167185231279817465%. Unresolved reasons are recorded row-by-row in the continuity matrix and unavailable report; a bad required session is never replaced by an older one.

## Structural-only checks

The command recomputed opening-activity availability, the frozen inclusive 1.50 threshold, D001 structural counts, yearly counts, and breakout-time structure only. It ran real pilots and manual 20-value median/ratio checks. It calculated no returns, P&L, profit factor, expectancy, win rate, drawdown, CAGR, or other performance result, and it accessed no validation data.

## Readiness and next step

`FAMILY_D_CONTINUITY_REMEDIATION_RESULT`: `MORE_INGESTION_REQUIRED`
`FAMILY_D_DATA_READINESS`: `BLOCKED`
`FAMILY_D_ARCHITECTURE_RESULT`: `DATA_BLOCKED`
`FAMILY_D_DEVELOPMENT_BACKTEST_READINESS`: `NO`

The next action is `RESOLVE_REMAINING_CONTINUITY_LIMITATIONS_BEFORE_PERFORMANCE`. This document does not authorize or run performance work.
