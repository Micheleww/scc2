---
oid: 01KGCV31NRV7N75QMWE6X01JWQ
layer: CANON
primary_unit: X.DISPATCH
tags: [A.ROUTER, A.PLANNER, A.EXECUTOR, A.VERIFIER, A.AUDITOR, A.SECRETARY]
status: active
---

# RoleSpec (v0.1.0)

Purpose: define the minimum set of roles SCC uses to route tasks deterministically.

Canonical machine-readable spec:
- `docs/ssot/03_agent_playbook/role_spec.json`

## Routing contract (normative)
- Input: a task description (goal text) + optional metadata (kind, touched paths, risk flags).
- Output: exactly one `role_id` + `reason` + optional `required_skills[]`.
- Rule: routing MUST be deterministic given the same inputs and RoleSpec.

## Minimum roles (v0.1.0)
- `router`: assigns role and execution mode; MUST not edit code/docs.
- `planner`: produces a contract/plan only; MUST not execute or edit.
- `chief_designer`: produces architecture blueprint/ADR drafts; MUST not dispatch execution.
- `team_lead`: splits work into task graph/contracts; dispatches crew; supervises and stops stuck runs.
- `executor`: makes changes within allowed scope; MUST produce evidence paths.
- `verifier`: runs acceptance; MUST output verdict artifacts; fail-closed.
- `auditor`: checks invariants (SSOT entrypoints, guards, evidence); MUST not edit.
- `secretary`: summarizes raw chat into derived notes; MUST not change canonical directly.
- `factory_manager`: prioritizes, approves contracts, dispatches; MUST not execute changes directly.

## Role Packs (normative)
Role Packs are the human-readable + machine-readable bundles that define how a role operates.
Ref:
- `docs/ssot/03_agent_playbook/roles/index.md`

## Gate rules (normative)
- Any task that reaches SUBMIT must pass the applicable guard(s).
- Skill/tool usage must be auditable via artifacts and/or structured logs.

