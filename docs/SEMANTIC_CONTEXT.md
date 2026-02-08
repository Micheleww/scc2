# Semantic Context (Read-Only, Permissioned) (MVP)

SCC already has SSOT + artifacts. `semantic_context/` is a lightweight, permissioned shared context layer for control-plane roles to reduce repeated pins churn and standardize "what we know".

Data:
- `semantic_context/index.jsonl` (JSONL; each row is `schema_version: scc.semantic_context_entry.v1`)

CI gate:
- `semantic_context` gate is executed by `tools/scc/gates/run_ci_gates.py`.

Intended usage:
- Control-plane roles (planner/factory_manager/retry_orchestrator/etc) may reference it.
- Patch-producing executors should not rely on it unless role policy explicitly permits it.

