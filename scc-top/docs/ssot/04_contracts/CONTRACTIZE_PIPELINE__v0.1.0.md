---
oid: 01KGCY1PF25RR6WZY42XD24VS5
layer: CANON
primary_unit: K.CONTRACT_DOC
tags: [D.TASKTREE, K.SCHEMA, K.CONTRACT_DOC, X.DISPATCH, V.VERDICT]
status: active
---

# Contractize Pipeline (v0.1.0)

Goal: turn a derived task tree (`docs/DERIVED/task_tree.json`) into per-task contract JSON files under SSOT, so executors/verifiers can run deterministically.

## 0. Inputs / Outputs
- Input: `docs/DERIVED/task_tree.json`
- Output contracts: `docs/ssot/04_contracts/generated/<task_id>.json`

## 1. Job runner
- `python tools/scc/ops/contractize_job.py --taskcode CONTRACTIZE_PIPELINE_V010 --area control_plane --run-mvm`

Notes:
- The job mints OIDs for generated contracts (Postgres registry) and embeds them inline in JSON.
- The job produces a REPORT + evidence bundle under `docs/REPORT/<area>/artifacts/<TaskCode>/`.

## 2. Next step (dispatch)
After contracts are generated, the leader may select a subset and dispatch via the existing delegation runbook:
- `docs/ssot/03_agent_playbook/DISPATCH_RUNBOOK__v0.1.0.md`

Fast path (auto-build a safe batch config from `contract_ref`):
- `python tools/scc/ops/dispatch_from_task_tree.py --taskcode CONTRACTIZE_DISPATCH_CONFIG_V010 --limit 5 --area control_plane --emit-report --run-mvm`

