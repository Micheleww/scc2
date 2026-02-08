---
oid: 01KGCV31KR2Z3Y3Y4GPPNNNGRZ
layer: CANON
primary_unit: X.DISPATCH
tags: [C.CAPABILITY, A.ROUTER, A.EXECUTOR, A.VERIFIER, A.AUDITOR]
status: active
---

# Capability Catalog (v0.1.0)

Purpose: enumerate the minimum SCC capabilities that agents can invoke or extend.

Canonical machine-readable catalog:
- `docs/ssot/03_agent_playbook/capability_catalog.json`

## Minimum capabilities (v0.1.0)
- `CAP_DOCFLOW_AUDIT`: run docflow audit → report under `artifacts/scc_state/`.
- `CAP_RAW_TO_TASKTREE`: generate `docs/DERIVED/task_tree.json` from WebGPT exports.
- `CAP_REVIEW_JOB`: write progress + feedback (raw-b) + metrics.
- `CAP_CODEX_DELEGATION`: dispatch parallel CodexCLI parents via `/executor/codex/run`.
- `CAP_TASKCODE_GUARD`: validate TaskCode triplet via `tools/ci/skill_call_guard.py`.

