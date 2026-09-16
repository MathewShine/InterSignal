# InterSignal Product Platform Charter V1

`INTERSIGNAL_PRODUCT_PLATFORM_CHARTER_V1` freezes the Month-1 planning profile `MONTH_1_PLATFORM_SCOPE_FREEZE_V1`. It defines product direction, priority, boundaries, governance, and handoff criteria. It starts no implementation.

## Product vision

InterSignal is an **Investment Intelligence Platform** spanning three core domains: `TRADE`, `INVEST`, and `RESEARCH`. They share `PORTFOLIO OS`, `BROKER CONNECTION`, `DATA LAYER`, `RISK / GOVERNANCE`, and `AUDITABILITY` capabilities.

The architecture is loosely coupled and adapter-driven. Core business and strategy logic must not depend directly on Groww, Zerodha, one data vendor, or one country. India is the first market; market, exchange, calendar, currency, instrument universe, data source, and broker remain configurable for later UK and US support.

## Month-1 priority freeze

| Priority | Modules |
|---|---|
| `P0` | Research Workbench; Portfolio OS Foundation; Data Lineage / Provenance; Strategy / Evidence Registry |
| `P1` | Portfolio & Risk Analytics; Shadow Observation Framework Design; Data Ingestion Observability; Governance / Audit UI |
| `P2` | Broker Abstraction Design; Alert / Monitoring Foundation |
| `DEFERRED` | Live automated execution; paper-trading deployment rehearsal; Family H; Strategy V2; new strategy research; full Family D intraday acquisition; Family F catalyst acquisition; broker order automation; autonomous AI strategy selection |

P0 establishes the platform’s durable information model. P1 makes that model observable and governable. P2 defines later integration and operations contracts without connecting anything.

## Governance baseline

The charter consumes and verifies `POST_RESEARCH_STRATEGY_PROGRAM_REVIEW_V1` at hash `a152b0e489005ecb506887082c99bee35a8e3c77e199f4c0ada2d7e0089a18cc` and the Family A closure at hash `ca43d6ffaab3612603cd48fa2f34974fd7b37d1f0f73c4d683b3c2ba00f446ad`.

The frozen state remains:

- A–G: `COMPLETE_NO_VALIDATED_STRATEGY`
- Program Review: `COMPLETE`
- Primary programme: `PRODUCT_PLATFORM_PROGRAM`
- Secondary programme: `FORWARD_DATA_PROGRAM`
- Month 1: `ACTIVE_PLATFORM_CHARTER`
- Strategy research: `PAUSED`
- Strategy V2: `NOT_CREATED`
- Family H: `NOT_PLANNED`
- Paper trading: `NOT_READY`
- Live trading: `NOT_READY`

No current family is upgraded. No production candidate is created.

## Module responsibilities

The Research Workbench will eventually browse strategy families, show experiment lineage and frozen hashes, compare development and validation evidence, inspect positive, negative, blocked, and data-limited evidence, prepare governed future experiment plans, and export reports. It will not mutate frozen evidence or execute research by itself.

Portfolio OS owns portfolios, accounts, holdings, cash, transactions, exposures, realized and unrealized P&L, benchmarks, allocation, attribution, goals, risk state, and broker account mappings. Its authoritative state must be reconstructable from auditable transactions and snapshots.

Data Lineage owns stable identities, versions, source references, transformations, configurations, code versions, quality state, authorization references, and hashes throughout the canonical path:

`SOURCE → RAW → NORMALIZED → DERIVED → FEATURE → CANDIDATE → SIGNAL → POSITION → TRADE → OUTCOME → EVIDENCE`

Every derived object must retain upstream provenance. A lineage break blocks governed downstream use and emits an audit event.

The common evidence registry supports `POSITIVE_EVIDENCE`, `NEGATIVE_EVIDENCE`, `BLOCKED_RESEARCH`, `VALIDATION_EVIDENCE`, `POST_OUTCOME_EVIDENCE`, and `DATA_INFRASTRUCTURE_EVIDENCE`. Existing A–G identifiers remain preserved. The canonical Family C observation label `EDGE-EVIDENCE-C-COMPRESSION-001` retains its relationship to the existing source registry ID `EVIDENCE-C-COMPRESSION-001`.

The strategy registry lifecycle is `IDEA`, `PREREGISTERED`, `DEVELOPMENT_EVALUATED`, `VALIDATION_CANDIDATE`, `VALIDATION_EVALUATED`, `PAUSED`, `REJECTED`, `DATA_BLOCKED`, `SOURCE_BLOCKED`, and `PRODUCTION_CANDIDATE`. Registry design does not authorize lifecycle movement.

## Shadow, broker, and execution boundary

The shadow design is `RESEARCH_SHADOW_MODE` and remains `DESIGN_ONLY_NOT_ACTIVATED`. It may later observe frozen hypotheses on genuinely new data that was not used for model selection. Family A remains `FROZEN_RESEARCH_BENCHMARK`, not a production candidate. Family C evidence `EDGE-EVIDENCE-C-COMPRESSION-001` remains `SIGNAL_LEVEL_RESEARCH_OBSERVATION_ONLY` and does not create a strategy.

Shadow observation must not place orders, simulate deployment readiness, mutate a strategy, or reuse a known holdout for model selection.

The broker abstraction defines only provider-neutral contracts for market data, account information, holdings, positions, future orders, order status, and historical data. Groww, Zerodha, and future brokers are possible adapters. No broker is connected, no credentials are needed, and no orders are placed.

## Product-owner gates

Separate product-owner approval is required for the first implementation module, shadow activation, broker connection, data acquisition, Family D/F feasibility execution, paper trading, and live trading. The default without approval is `DO_NOT_START`.

## Month-1 completion semantics

Month 1 succeeds when architecture, boundaries, lineage, registry models, Portfolio OS scope, shadow governance, broker abstraction, real-time and indicator architecture, and UI information architecture are frozen and a prioritized Month-2 backlog is approved. This charter completes the definition work; it does not claim that implementation or Month 1 as a programme is complete.

The immutable charter hash is recorded in `INTERSIGNAL_PRODUCT_PLATFORM_CHARTER_MANIFEST_V1`. Month 2 must not begin automatically.
