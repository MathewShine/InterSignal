# InterSignal Platform Architecture V1

This document is the architecture-level output of the Month-1 charter. It defines boundaries and contracts only; it contains no backend, frontend, broker, data-acquisition, or trading implementation.

## Platform shape

The platform has three product domains—Trade, Invest, and Research—over shared Portfolio OS, Data, Risk, Governance, Audit, Alerts, and Broker Abstraction capabilities. Domain logic depends on stable contracts. Provider clients live behind adapters and cannot leak vendor-specific objects into the core model.

| Boundary | Owns | May depend on | Must not own or call directly |
|---|---|---|---|
| Research | Hypotheses, experiments, candidates, evidence, validation plans | Data, Governance, registries | Broker adapters, execution |
| Trade | Future signal evaluation, execution decisions, order intents | Portfolio OS, Data, Risk, broker contracts, Governance | Provider-specific APIs, research mutation |
| Invest | Goals, allocation, long-horizon intelligence | Portfolio OS, Data, Risk, Alerts | Research internals, provider code |
| Portfolio OS | Accounts, holdings, cash, transactions, attribution, portfolio state | Data contracts, broker read contracts, Risk | Strategy selection, broker implementation |
| Broker | Provider adapters and future transport | External APIs behind adapters | Research, analytics, policy authority |
| Data | Sources, ingestion, normalization, quality, lineage | Provider adapters, configuration | Strategy and order decisions |
| Risk | Limits, exposure, risk state, future gates | Portfolio OS, Data, Governance policy | Alpha generation, broker transport |
| Governance | Authorization, lifecycle, evidence and audit policy | Registries, append-only audit | Prediction, broker transport |
| Alerts | Alert rules, severity, routing, acknowledgement | Read-only telemetry | Authoritative state mutation, orders |

Dependencies must remain acyclic. Alerts observe but do not own system state. Governance defines and records policy but does not generate alpha. Risk may gate a future decision but cannot create a strategy.

## Canonical model

Research entities are StrategyFamily, Strategy, Experiment, Candidate, Evidence, Authorization, ValidationRun, and ArtifactHash. Portfolio entities are Portfolio, Account, Holding, CashBalance, Transaction, Exposure, PnL, Benchmark, Allocation, Attribution, RiskState, and Goal. Data entities are DataSource, Dataset, DataPartition, LineageNode, QualityCheck, CorporateAction, Instrument, and MarketCalendar. Broker entities are BrokerAccountMapping, BrokerAdapter, and future-only OrderIntent and OrderRecord. Operational entities are Alert, JobRun, AuditEvent, and ManualOverride.

Each entity has a stable ID and version. Derived entities retain upstream IDs and hashes. Configurations and evidence retain content hashes. Lifecycle changes require append-only audit events.

## Data and provenance

The market-data layer separates daily, intraday, real-time, corporate-action, fundamental, catalyst, benchmark, and broker-account data. Each category is partitioned by source, licence, frequency, market, quality, retention, and lineage.

The canonical lineage sequence is:

`SOURCE → RAW → NORMALIZED → DERIVED → FEATURE → CANDIDATE → SIGNAL → POSITION → TRADE → OUTCOME → EVIDENCE`

Required metadata includes object and version IDs, creation time, upstream IDs and hashes, transformation ID, configuration hash, code version, dataset partition, quality state, and applicable authorization ID.

## Future real-time path

The future path is broker/feed → real-time normalization → bar aggregation → indicator calculation → pattern state → strategy evaluation → risk gate → execution decision. It is a design, not an active pipeline.

The extensible indicator layer may represent VWAP, ATR, moving averages, relative volume, relative strength, momentum, opening range, breadth, volatility, support/resistance, and price structure. Indicators may support strategy logic, execution, risk, monitoring, or analytics; they do not automatically imply alpha.

Pattern states may represent breakout, reclaim, pullback, compression, opening-range behavior, trend, momentum continuation, and support/resistance interaction. Defining these states activates no strategy.

## Risk and observability

Portfolio analytics are planned for total equity, cash, exposure, sector exposure, concentration, turnover, transaction costs, drawdown, volatility, rolling returns, contribution, benchmark-relative performance, and risk limits. Metric definitions require lineage. No risk limit is activated by this design.

Planned operational alerts cover data-feed outage, stale data, job failure, broker disconnect, risk breach, strategy-error condition, missing source, and validation-integrity issues. Alerts carry severity, source, owner, timestamps, object ID, runbook, and audit event ID through open, acknowledged, resolved, or reasoned-suppression states.

## Portability

India is first. The same core contracts must later support UK and US markets through configuration for market, exchange, calendar, currency, instrument universe, data source, and broker. Groww and Zerodha are potential adapters, not core dependencies.
