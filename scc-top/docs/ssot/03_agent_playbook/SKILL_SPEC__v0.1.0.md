---
oid: 01KGCV31PTC2CNRKV9BM3KXXWQ
layer: CANON
primary_unit: X.DISPATCH
tags: [V.SKILL_GUARD, A.ROUTER, A.EXECUTOR, A.VERIFIER, A.AUDITOR]
status: active
---

# SkillSpec (v0.1.0)

Purpose: define the minimum skill/tool taxonomy used by SCC agents, and the guardable invariants.

Canonical machine-readable spec:
- `docs/ssot/03_agent_playbook/skill_spec.json`

## Guard rule (normative)
- Any task that claims DONE must be verifiable by the appropriate guard(s).
- For TaskCode-based CI flow, the guard is: `tools/ci/skill_call_guard.py`.

## Minimum skills (v0.1.0)
- `SHELL_READONLY`: inspect repo (rg/cat/ls); no writes.
- `SHELL_WRITE`: write within allowed workspace roots.
- `PATCH_APPLY`: apply code/doc patches.
- `SELFTEST`: run acceptance commands/tests.
- `DOCFLOW_AUDIT`: run docflow audit and write report under artifacts.
- `REVIEW_JOB`: generate progress + feedback + metrics.

## Evidence rule (normative)
Normative docs MUST NOT embed large evidence; they must link to:
- `artifacts/...` and `docs/INPUTS/...`

