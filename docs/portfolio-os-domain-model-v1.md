# InterSignal Portfolio OS domain model v1

## Scope

`INTERSIGNAL_PORTFOLIO_OS_FOUNDATION_V1` is the broker-neutral backend/domain foundation for portfolios, accounts, cash, securities, holdings, lots, transactions, valuations, exposures, benchmarks, performance, attribution, risk, goals, and events. It does not include a user interface, broker adapter, order execution, a live feed, strategy creation, or database persistence.

The core models are immutable Pydantic records. Identifiers are stable strings, timestamps are timezone-aware UTC values, monetary calculations use `Decimal`, and persisted local records are append-only JSONL. Canonical artifact hashes use `INTERSIGNAL_CANONICAL_SHA256_V1`.

## Aggregate and identities

`Portfolio` is the aggregate root. A portfolio declares its type, base currency, market scope, lifecycle status, benchmark IDs, account IDs, optional strategy IDs, goal IDs, and metadata. Lifecycle updates append another portfolio state; records are never deleted.

`PortfolioAccount` identifies an account independently of any provider API. Provider values (`GROWW`, `ZERODHA`, `MANUAL`, `SIMULATED`, and `OTHER`) are labels only. `BrokerSyncState` records `NEVER_SYNCED`, `SYNC_PENDING`, `SYNCED`, `STALE`, or `ERROR`; this command performs no sync or connector call.

`SecurityReference` is the broker-neutral instrument identity. It supports equities, ETFs, mutual funds, indexes, cash, and other instruments. Market, exchange, symbol, optional ISIN, currency, and optional metadata are not tied to a single exchange or sector taxonomy. Sector and industry may be carried as metadata.

## Positions and state

`CashBalance` is a point-in-time account balance. `Holding` is a derived position snapshot, and `PositionLot` retains FIFO acquisition history and remaining cost basis. Holdings may optionally carry strategy attribution, evidence, and lineage references; no strategy reference is required.

`PortfolioValuation` records gross market value, cash, net liquidation value, cost basis, realized and unrealized P&L, and total P&L. `ValuationSnapshot` seals a valuation together with the associated holding and cash-account identities and a canonical hash.

`ExposureSnapshot` represents gross/net exposure and security, sector, strategy, account, and currency weights. `PortfolioRiskSnapshot` stores descriptive risk state and stable flags. Neither model emits a recommendation.

## Benchmarks, performance, attribution, and goals

`BenchmarkReference` and `PortfolioBenchmarkComparison` represent versioned comparison data without making alpha claims. `PortfolioPerformancePoint` provides a deterministic portfolio time series; `PortfolioMetrics` derives total return, CAGR, drawdown, volatility, positive-period rate, turnover, costs, and cash utilization.

`PortfolioAttribution` supports simple contribution accounting by security, strategy, sector, and transaction cost. `PortfolioGoal` is deliberately lightweight and has no recommendation or planning engine.

## Events and repositories

Every service mutation emits an append-only `PortfolioEvent`. Stable event categories cover portfolio creation, account linking, transaction recording, holdings rebuilds, valuations, risk snapshots, benchmark linking, status changes, and manual adjustments.

Eight repository interfaces isolate domain logic: `PortfolioRepository`, `AccountRepository`, `TransactionRepository`, `HoldingRepository`, `ValuationRepository`, `RiskRepository`, `BenchmarkRepository`, and `PortfolioEventRepository`. Both in-memory and JSONL implementations are included. The JSONL implementation stores data beneath `data/platform/portfolio_os/` and has no Supabase dependency.

## Synthetic fixtures and boundaries

The initial export contains exactly two clearly marked synthetic examples: one research-only portfolio and one manually entered investment portfolio. They contain no real account information, live signal, validated strategy, broker connection, or production-live semantics.

Known limitations include no FX conversion, no corporate-action processor, no tax-lot optimization, no derivatives-specific accounting, no SIP engine, no broker reconciliation adapter, and no persistence transaction spanning multiple JSONL files.
