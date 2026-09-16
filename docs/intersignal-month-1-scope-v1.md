# InterSignal Month-1 Scope V1

Month 1 is a platform-definition phase under `MONTH_1_PLATFORM_SCOPE_FREEZE_V1`. Its output is an implementation-ready decision framework, not implemented product capability.

## In scope

- Freeze the Investment Intelligence Platform vision.
- Freeze P0, P1, P2, and deferred priorities for all ten planned modules.
- Define the module dependency map and prevent circular dependencies.
- Define the canonical domain model and Portfolio OS entities.
- Define end-to-end lineage and provenance requirements.
- Define strategy and evidence registry schemas without changing current states.
- Define portfolio/risk metric scope.
- Define research-only shadow governance without activation.
- Define a broker-neutral interface without connection or calls.
- Define market-data categories and ingestion-observability concepts.
- Define future real-time, indicator, and pattern architecture.
- Define governance, append-only audit, alerting, and UI information architecture.
- Prepare Month-2 backlog categories that require product-owner approval.

## Explicit non-goals

Month 1 excludes production trading, autonomous execution, new alpha discovery, Family H, Strategy V2, auto-optimizing indicators, unrestricted AI strategy generation, Family D or Family F data acquisition, and live capital deployment.

Also deferred are live automated execution, paper-trading deployment rehearsal, new strategy research, broker order automation, and any automatic transition into Month 2.

## Deliverables

| ID | Deliverable | Month-1 state |
|---|---|---|
| M1-01 | Platform architecture document | Frozen in charter |
| M1-02 | Module dependency map | Frozen in charter |
| M1-03 | Canonical domain model | Frozen in charter |
| M1-04 | Data lineage specification | Frozen in charter |
| M1-05 | Strategy/evidence registry specification | Frozen in charter |
| M1-06 | Portfolio OS domain model | Frozen in charter |
| M1-07 | Shadow-mode governance specification | Frozen in charter |
| M1-08 | Broker abstraction contract | Frozen in charter |
| M1-09 | Real-time engine design | Frozen in charter |
| M1-10 | UI information architecture | Frozen in charter |
| M1-11 | Month-2 backlog categories | Frozen; approval pending |

## Product-owner decisions

The product owner must separately approve:

1. The first implementation module.
2. Shadow observation activation.
3. A broker connection.
4. Data acquisition.
5. Family D/F feasibility execution.
6. Paper trading.
7. Live trading.

Until approval, the state is `DO_NOT_START`.

## Month-2 handoff categories

The handoff contains categories only: foundation implementation candidate; registry and lineage; Portfolio OS; UI shell and read models; data observability; shadow-design readiness; broker contracts; portfolio and risk analytics; and governance, audit, and alerting. Each remains `REQUIRES_PRODUCT_OWNER_APPROVAL`; no Codex implementation command is generated.

## Success criteria

The definition phase succeeds when architecture is frozen, module boundaries are clear, lineage and registry models are complete, Portfolio OS scope is complete, shadow governance is complete, the broker abstraction is defined, real-time and indicator architecture is documented, UI IA is documented, and the prioritized Month-2 backlog is approved.

The first nine conditions are defined by this charter. Month-2 backlog approval remains a future product-owner decision, so Month 1 is active rather than declared complete.

## Risks and controls

| Risk | Primary control |
|---|---|
| Scope creep | Frozen priorities, non-goals, and owner gates |
| Premature execution focus | Inactive Trade/order paths until validation and approval |
| Overengineering | Approve one bounded vertical slice at a time |
| Vendor lock-in | Provider-neutral broker and data adapters |
| Data licensing | Rights/provenance tracking and acquisition approval |
| Research/product coupling | Separate research, registry, portfolio, data, and execution boundaries |
| AI overreach | No autonomous selection or unrestricted generation |
| Unclear production readiness | Explicit lifecycle, authorization, validation, and readiness fields |
