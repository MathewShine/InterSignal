# Strategy V1 Entry Evaluation Audit

Current phase: Step 02.8 / Command 02 - structural audit only

## Boundary

- This audit reads ENTRY_EVALUATION_V1 and does not mutate the baseline.
- It uses no future returns, MFE/MAE, stop/target hits, profitability labels, backtests, risk/reward, orders, or Supabase writes.
- Future entry states are used only for state-transition and churn analysis.

## Version

- Audit version: ENTRY_EVALUATION_AUDIT_V1
- Entry version/hash: ENTRY_EVALUATION_V1 / 5a8c1c82e9b36be5

## Funnel

- Candidate rows: 142202
- Setup eligible rows: 29748 (20.9195%)
- Progressed rows: 26130 (87.8378% of setup eligible)
- Ready for risk rows: 22670
- Exceptional long review rows: 324

## Results

- Structural stability: MODERATELY_SENSITIVE
- Funnel sanity: HEALTHY_BUT_HIGH_PASS_THROUGH
- Penalty consistency: CONSISTENT_WITH_INHERITED_BLOCKERS
- Exceptional-long result: SELECTIVE
- Baseline decision: FREEZE_UNCHANGED

## Key Findings

- Setup-to-entry progression is structurally explainable: True
- Blocking penalty rows: 77685 versus NOT_READY rows: 72159.
- Blocking rows by readiness: {'NOT_READY': 72159, 'WATCH': 5526, 'CONDITIONALLY_READY': 0, 'READY_FOR_RISK_EVALUATION': 0, 'EXCEPTIONAL_LONG_REVIEW': 0}
- Exceptional-long review rate: 8.5919% of bearish setup-eligible rows.

## Integrity

- Entry dataset unchanged: True
- Feature dataset unchanged: True
- Candidate dataset unchanged: True
- Setup dataset unchanged: True
- Regime dataset unchanged: True
- ZERO orders were placed.
- ZERO remote migrations were applied.
- ZERO records were persisted to Supabase.

## Limitation

- This audit is structural. It cannot prove profitability, stop placement, target quality, or risk/reward feasibility.
