---
oid: 01KGCV31QWFC0CF1433Z8ZJGC3
layer: CANON
primary_unit: X.DISPATCH
tags: [W.WORKSPACE, V.GUARD]
status: active
---

# WorkspaceSpec (v0.1.0)

Purpose: define the minimum workspace invariants used by SCC.

Canonical machine-readable spec:
- `docs/ssot/03_agent_playbook/workspace_spec.json`

## Minimum invariants (normative)
- workspace_id: `scc-top`
- Repo root contains `docs/START_HERE.md` (唯一入口).
- SSOT trunk is under `docs/ssot/`.
- Inputs are under `docs/INPUTS/`.
- Derived (regenerable) outputs are under `docs/DERIVED/`.
- Evidence/outputs are under `artifacts/` and `evidence/` (append-only preferred).

## Multi-project workspaces (normative)
When multiple production projects exist in one workspace:
- Every contract MUST declare `project_id`.
- Dispatch MUST derive `allowed_globs[]` from the project catalog and then further narrow by `contract.scope_allow`.
Refs:
- `docs/ssot/02_architecture/PROJECT_GROUP__v0.1.0.md`
- `docs/ssot/02_architecture/project_catalog.json`

