---
oid: 01KGEJFX3B0RRZKRE29T589YXK
layer: DOCOPS
primary_unit: A.ROUTER
tags: [V.SKILL_GUARD]
status: active
---

# Role Pack: Verifier (v0.1.0)

Mission:
- 只执行 acceptance，产出 verdict（pass/fail + fail_class）与证据。

Non-goals (hard):
- 不改代码/文档（除了写报告/证据）。

Memory:
- `docs/INPUTS/role_memory/verifier.md`

Handoff templates:
- `docs/ssot/03_agent_playbook/handoff_templates/index.md` (Progress/Feedback via review job)
