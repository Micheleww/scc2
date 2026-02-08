Context: Need a deterministic Map-driven closed loop so pins/preflight/SSOT gates fail-closed and are replayable.
Decision: Implement Map-first pins_builder_v1 + preflight_v1 in gateway/CLI, add SSOT facts registry + ssot_map_gate suggestions, and extend Map version with facts_hash.
Alternatives: Keep LLM-only pins generation; rely on manual SSOT updates without machine-checkable registry; omit facts_hash and diff using full map hash.
Consequences: Reduced pins churn and fewer guaranteed-fail dispatches; stricter drift detection requires updating docs/SSOT/registry.json when contracts/entry points change.
Migration: Run `npm --prefix oc-scc-local run map:build`, then keep `docs/SSOT/registry.json` in sync using `artifacts/<task_id>/ssot_update.json` from CI gate runs.
Owner: SCC control-plane maintainers

