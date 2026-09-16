# InterSignal Portfolio OS risk and analytics v1

## Descriptive analytics

Portfolio OS v1 computes descriptive state only. It does not generate trading signals, advice, target positions, or orders.

Performance metrics are deterministic functions of ordered `PortfolioPerformancePoint` records and the immutable transaction ledger:

- total return from first and last portfolio value;
- annualized CAGR when the interval and values permit it;
- maximum peak-to-trough drawdown;
- annualized volatility from daily return population variance;
- positive-period rate;
- turnover from traded gross value divided by average portfolio value;
- explicit fees and taxes;
- average cash utilization.

Benchmark comparisons contain portfolio return, benchmark return, active return, relative drawdown, and tracking difference over an explicit period. They are comparisons only and make no alpha claim.

## Exposure

Exposure snapshots use the latest holdings and cash. Gross and net exposure are normalized by net liquidation value. Security, sector, strategy, account, and currency maps are normalized weights. Sector and industry labels come from optional instrument metadata; no NSE-only or other market-specific taxonomy is embedded in the model.

If more than the base currency is present, the snapshot is retained but carries `FX_CONVERSION_REQUIRED`. The values are not silently converted or summed as though FX rates were one.

## Risk state and flags

`PortfolioRiskSnapshot` stores drawdown, volatility, concentration, top-one and top-five weights, cash percentage, turnover, cost drag, gross exposure, and net exposure. Stable flags include:

- `CONCENTRATION_HIGH`
- `CASH_LOW`
- `TURNOVER_HIGH`
- `COST_DRAG_HIGH`
- `STALE_VALUATION`
- `MISSING_PRICE`
- `DATA_QUALITY_WARNING`
- `FX_CONVERSION_REQUIRED`

The current exposure helper flags concentration above 40%, cash below 5%, and currency conversion requirements. Other flags can be supplied by later deterministic validation policies. No flag is a trading recommendation.

## Attribution

The initial attribution implementation groups latest unrealized P&L by security and sector, apportions it to any explicit strategy weights, and reports explicit transaction costs as a negative contribution. It never infers a strategy ID or evidence relationship. Because this is a simple snapshot method, it is not a time-weighted, factor, Brinson, or causal attribution system.

## Integrity

The export integrity summary counts broken references, negative holding violations, cash reconciliation errors, duplicate transaction IDs, valuation mismatches, and event-sequence errors. The two synthetic seed portfolios must export as `HEALTHY` with all counters zero.

## Known limitations

Risk statistics are based only on locally supplied performance points; there is no market feed, covariance model, VaR, stress engine, factor model, recommendation engine, or alert delivery. Staleness thresholds and richer flag policies are deferred. Multi-currency analytics require a future explicit FX conversion layer.
