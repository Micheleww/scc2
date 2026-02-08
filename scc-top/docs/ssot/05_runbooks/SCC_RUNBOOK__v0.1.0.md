---
oid: 01KGCV320P7HXQRPXP9SC8V452
layer: CANON
primary_unit: S.CANONICAL_UPDATE
tags: [X.DISPATCH, V.VERDICT, P.REPORT]
status: active
---

# SCC Runbook（v0.1.0 / SSOT）

目标：把 SCC 的“任务执行与审计”固化为**可运行的状态机**，让多人/多 Agent 协作时保持 **可控 / 可审计 / 可扩展**。

本页是单页 SSOT：当文档冲突时，以本页为准，并将冲突回写到本页或其直接链接的规范文件。

## 0) 核心原则（必须遵守）

- **事实源优先**：事实来自 `artifacts/` / `evidence/` / 数据库与可重放日志；README/聊天只做入口与索引。
- **Patch-only 执行**：Executor 只能提交最小 diff；验证由 Verifier/测试裁决；失败才扩大范围/升模型/扩权限。
- **事件化交付**：每次动作都要落盘事件（task/event/evidence），确保可追溯、可重放、可回滚。
- **失败可收敛**：重试≤3；失败进入 DLQ；必须给出下一步“可执行修复任务”而不是抽象总结。

## 1) 文档与协议入口

- Task schema：`docs/spec/integration/task_schema.json`
- Event model：`docs/arch/ops/SCC_EVENT_MODEL__v0.1.0.md`
- Evidence/Artifacts：`docs/arch/ops/SCC_EVIDENCE_STORAGE__v0.1.0.md`
- Roles：`docs/arch/routing/ROLE_CARDS__v0.1.0.md`
- Cleanliness：`docs/arch/ops/SCC_CLEANLINESS__v0.1.0.md`

## 2) 状态机（唯一允许的执行流程）

**SEARCH → HYPOTHESIS → FREEZE → ACT → VERIFY → DONE / FAIL**

### SEARCH（定位）
- 目标：找到可验证的失败点/缺口（日志/报错/缺文件/接口差异）。
- 产物：证据路径（log/evidence/artifact），以及最小复现步骤或触发条件。

### HYPOTHESIS（假设）
- 目标：提出 1–3 个可证伪假设，给出验证方法与预期输出。
- 禁止：直接改代码“碰运气”。

### FREEZE（冻结范围）
- 目标：冻结要改的范围与可接受的副作用（文件白名单、接口影响、回滚点）。
- 产物：`acceptance_tests`（最少 1 条）+ `rollback_plan`（最少 1 条）。

### ACT（执行）
- 目标：在冻结范围内最小改动，落盘 diff + 证据。
- 产物：patch（diff）、执行日志、产物路径、退出码。

### VERIFY（验证）
- 目标：只认测试/验证器输出（exit_code、golden、回归用例），通过才算 DONE。
- 失败：进入 FAIL（并写失败分类），生成下一条“可执行修复任务”或进入 DLQ。

## 3) 重试 / DLQ / 升级策略（收敛机制）

### 重试（≤3 次）
每次重试必须满足：
- 修改了假设/验证方式/冻结范围之一（不能重复同一动作）
- 增加了新的证据（新日志、新 diff、新指标）

### DLQ（Dead Letter Queue）
进入 DLQ 的条件（满足任一）：
- 3 次重试后仍失败
- 需要外部依赖（硬件到货/管理员权限/备份后才能做）
- 风控/登录/第三方不可控导致无法稳定复现

DLQ 要落盘：
- fail_code（结构化）
- 阻塞条件（例如“等待服务器归一化/管理员权限”）
- 继续执行的最小触发条件（例如“备份完成后执行脚本 X”）

### 升级（模型/权限/范围）
优先级（从低到高）：
1) 扩验证与证据（更细粒度日志/更窄复现）
2) 扩执行范围（但仍 patch-only）
3) 升模型（先 coder/medium，再 thinking/强模型）
4) 升权限（管理员/系统级）——需要显式记录原因与回滚

## 4) 证据与产物（最小交付）

每个任务至少交付：
- 变更：diff（或明确说明“无代码变更”）
- 证据：运行日志 / 关键输出 / 截断规则
- 产物路径：`artifacts/...` 或 `docs/...` 的可点击路径
- 可重放：命令行/脚本入口（PowerShell 为主）

推荐结构：
- 运行证据：`artifacts/<domain>/<task_id>/...`
- 共享输入：`docs/INPUTS/...`
- 审计记录：`evidence/...`（append-only）

## 5) 终止条件（何时算完成）

DONE 的最低条件：
- 验证通过（测试/验证器绿）
- 证据落盘
- 导航可发现（入口文档已链接：`docs/START_HERE.md` / `docs/arch/00_index.md`）

FAIL 的最低条件：
- 失败原因结构化（fail_code + 证据路径）
- 给出下一步可执行任务（或 DLQ 条目）
