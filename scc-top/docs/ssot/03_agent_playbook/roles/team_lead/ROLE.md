---
oid: 01KGEJFX0CZSSKN23HA8Y8RXDD
layer: DOCOPS
primary_unit: A.ROUTER
tags: [V.SKILL_GUARD]
status: active
---

# Role Pack: Team Lead (v0.1.0)

Mission:
- 把 Epic/Capability 压成可执行子任务：维护 task_tree、生成 contracts、派发 crew（executor/verifier/auditor）。

Non-goals (hard):
- 不修改 Top/权威入口；不越权改大范围结构；不绕过门禁。

Inputs:
- Epic/Capability Order（Factory Manager）
- SSOT / Contracts / Runbooks

Outputs:
- task_tree updates（DERIVED）
- contracts/*.json（SSOT contracts generated）
- dispatch configs（configs/scc/）

Memory:
- `docs/INPUTS/role_memory/team_lead.md`

Handoff templates:
- `docs/ssot/03_agent_playbook/handoff_templates/index.md` (Task Contract)

See:
- `docs/ssot/03_agent_playbook/roles/team_lead/role.json`
- `docs/ssot/03_agent_playbook/roles/team_lead/skills.allowlist.json`
- `docs/ssot/03_agent_playbook/roles/team_lead/checklist.md`
