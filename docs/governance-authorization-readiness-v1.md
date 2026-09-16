# InterSignal authorization and readiness v1

## Authorization semantics

Authorization is explicit and scoped by subject and type. New requests begin as `REQUESTED`; they are never automatically approved. Valid decisions are `APPROVED`, `REJECTED`, `REVOKED`, `EXPIRED`, and `NOT_REQUIRED`. Every transition records actor, time, reason, conditions, and related artifacts in append-only history.

An approved authorization may have an expiry. It cannot be used at or after expiry. Conditions are stored as explicit text and are never assumed satisfied. Service consumers must request an active authorization matching both subject and authorization type before recording an override or waiver.

The initial seed has one unresolved `DATA_ACQUISITION` request for Family F’s catalyst-history source. It records the licensing gate but grants no permission and starts no acquisition. Broker connection, shadow, paper, live, promotion, and production are not authorized.

## Readiness

Readiness is an assessment, not an authorization. Each assessment records boolean criteria, the exact false criteria, warnings, evidence/artifact linkage, and one of `READY`, `READY_WITH_LIMITATIONS`, `NOT_READY`, `BLOCKED`, or `INCONCLUSIVE`.

The current snapshot is:

- research: `NOT_READY`, operationally `PAUSED` and not active discovery;
- platform modules: `READY_WITH_LIMITATIONS` because 04.01–04.04 are complete while 04.05 is not started;
- paper trading: `NOT_READY`, with no validated or approved candidate;
- live trading: `NOT_READY`, lacking candidate, paper/shadow evidence, risk, broker, data, and production authorization;
- production: `NOT_READY`, with zero production candidates and zero validated production strategies;
- broker: `NOT_READY` and `NOT_CONNECTED`.

## Operational gates

Broker connection requires a future `BROKER_CONNECTION` authorization. Historical intraday or catalyst acquisition requires a future scoped `DATA_ACQUISITION` approval and explicit licensing conditions. Paper, live, promotion, and production require their corresponding authorizations in addition to readiness.

No open request, policy pass, readiness status, or audit record implies permission. The owning service remains responsible for any later authorized action.

## Limitations

V1 has no identity provider, cryptographic signature, quorum approval, delegated role hierarchy, notification system, scheduled expiry worker, UI, broker action, or execution engine. Expiry is enforced when authorization is used and checked by integrity inspection.
