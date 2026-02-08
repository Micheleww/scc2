# INDEX (Single Entry)

## Core
- `docs/NAVIGATION.md`（endpoints / control plane）
- `docs/AI_CONTEXT.md`（pins-first JSON 载体）
- `docs/EXECUTOR.md`（atomic 执行约束）
- `docs/PROMPT_REGISTRY.md`（提示词资产库 / 渲染 / 审计）
- `docs/SCC_USAGE_GUIDE.md`（SCC 系统完整使用指南 — 所有 AI agent 必读：架构 / 任务生命周期 / API / 角色 / Pins / 提交合同 / 错误码 / Token 优化）
- `docs/SSOT.md`（Designer-only L0）
- `docs/SSOT/registry.json`（Map 驱动的 SSOT facts 登记表：modules/entry_points/contracts）

## Ops
- `docs/SECURITY_SECRETS.md` (soft repo encryption + workflow)
- `docs/UI_STYLE_GUIDE__SCC_WORKBENCH.md`（Workbench UI 统一风格与 tokens 规则，供所有 AI 遵循）
- `docs/CONNECTORS.md`（connectors registry + gate）
- `docs/SEMANTIC_CONTEXT.md`（permissioned shared context layer）
- `docs/STATUS.md`（运行状态）
- `docs/WORKLOG.md`（最近快照）
- `docs/adr/README.md`（ADR 模板与门禁）
- `docs/adr/ADR-20260206-factory-control-plane-mvp.md`（SCC control-plane MVP）
- `docs/PROMPTING.md`（deprecated，只读）
- `docs/archive/`（只读）

## Rules
- Executor 只消费 pins / context pack；禁止读取 SSOT。
- 新增文档必须在本页登记。


