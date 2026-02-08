# Connectors Registry (MVP)

SCC treats executors, proxies, and tool backends as "connectors". The goal is to make integrations auditable and permissionable, instead of growing one-off glue.

Registry:
- `connectors/registry.json` (`schema_version`: `scc.connector_registry.v1`)

What this enables:
- A single place to declare connector IDs, endpoints, scopes, and allowed roles.
- CI gate validation: `python tools/scc/gates/run_ci_gates.py --submit artifacts/<task_id>/submit.json` runs the `connectors` gate.

Notes:
- This is an MVP. It does not yet enforce connector usage at dispatch-time; it only documents and validates the control-plane inventory.

