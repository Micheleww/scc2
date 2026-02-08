---
oid: 01KGCV31RXZTJZS7V7VEP80C9X
layer: CANON
primary_unit: K.CONTRACT_DOC
tags: [K.ACCEPTANCE, V.VERDICT]
status: active
---

# Contract Minimum Spec (v0.1.0)

## 0. Purpose
Define the minimum contract fields required for any executable task.

Schema (machine-readable, SSOT canonical):
- `docs/ssot/04_contracts/contract.schema.json`

## 1. Minimum fields (mandatory)
- goal: what to achieve
- project_id: which production project this task belongs to (must exist in catalog)
- scope_allow: allowed changes (or EMPTY)
- constraints: hard constraints
- acceptance: executable checks (machine-oriented; command + evidence expectations)
- stop_condition: when to stop / fail-closed rules
- commands_hint: suggested commands for executor/verifier

## 2. Required references
- inputs_ref: pins/map/paths/oids needed
- outputs_expected: artifacts/verdict expected

Project catalog (authoritative):
- `docs/ssot/02_architecture/project_catalog.json`

## 3. Verifier rule (mandatory)
Verifier MUST judge only by acceptance outcomes.
No “looks good” verdicts without checks.

## 4. Template (copy)
goal:
scope_allow:
constraints:
acceptance:
stop_condition:
commands_hint:
inputs_ref:
outputs_expected:

## 5. Changelog
- v0.1.0: initial
