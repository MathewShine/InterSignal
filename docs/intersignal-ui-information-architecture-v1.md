# InterSignal UI Information Architecture V1

This is an information architecture only. No UI code or frontend feature is started.

## Primary navigation

The planned top-level pages are Home / Command Center, Research, Strategies, Evidence, Portfolio, Market, Data, Governance, Alerts, and Settings.

### Home / Command Center

The Command Center summarizes system status, market state, portfolio state, research status, data freshness, strategy status, alerts, and broker connectivity. Because there is no validated strategy, it must show no signal recommendation. Status cards link to their authoritative detail pages rather than duplicating or mutating source state.

### Research

The Research page presents the family matrix, experiment timeline, evidence, validation records, blocked studies, reports, and artifacts. Frozen hashes and lineage remain visible. Future experiment plans may be drafted under governance but cannot execute from the planning view.

### Strategies and Evidence

Strategies exposes lifecycle, configuration hash, authorization, validation state, and production readiness. Evidence supports classification, source, lineage, hash, and positive, negative, or blocked views. The pages use the shared registries and do not infer promotion from a metric or label.

### Portfolio

The Portfolio page plans holdings, allocation, performance, risk, cash, benchmarks, broker synchronization state, and goals. Broker synchronization is a status concept only until a connection is separately authorized.

### Market and Data

Market covers market state, benchmarks, breadth, calendars, and instrument universe. Data covers sources, coverage, freshness, quality, lineage, ingestion runs, failures, and licensing status. Quality and licensing restrictions must be visible before derived data is treated as usable.

### Governance

Governance presents authorizations, validation runs, strategy lifecycle, append-only audit log, policy violations, and manual overrides. It also exposes hashes, blocked reasons, data quality, run count, and production-readiness semantics.

### Alerts

Alerts presents open items, severity, ownership, acknowledgement, history, and resolution or suppression reason. It observes state and does not become an authority for portfolio, broker, data, or strategy state.

### Settings

Settings captures market, exchange, calendar, currency, data source, broker adapter, and policy configuration. Provider selection remains behind adapter contracts and does not change core business logic.

## Information design rules

- Every governed object links to version, hash, lineage, and relevant audit events.
- Development, validation, post-outcome, and blocked evidence remain visibly distinct.
- A strategy status is never inferred from performance alone.
- Unknown, stale, blocked, unauthorized, and not-applicable states are explicit.
- Broker connectivity does not imply trading authorization.
- Shadow observation does not imply paper or production readiness.
- With zero validated strategies, the Command Center presents governance state—not recommendations.
