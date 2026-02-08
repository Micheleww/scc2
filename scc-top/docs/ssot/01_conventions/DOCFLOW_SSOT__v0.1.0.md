---
oid: 01KGCV31DYYFG8CWSKY61JC40J
layer: DOCOPS
primary_unit: S.CANONICAL_UPDATE
tags: [S.NAV_UPDATE]
status: active
---

# Docflow SSOT（v0.1.0）

目标：把 **文档流**确立为 SCC 的主干（外部记忆与协议载体），让 AI 工作流与代码流围绕文档流运行，实现：
- **一致性**：命名一致、入口一致、落点一致
- **可发现**：任何人/AI 从固定入口能找到正确文档
- **可审计**：规范与证据分离，证据可追溯
- **可拼装上下文**：本地模型能按“导航→规范→输入→证据”稳定拼装 context

## 1) 唯一入口（不再增加新的入口页）

只允许以下入口作为 SSOT：
- 总入口：`docs/START_HERE.md`
- 架构/运维入口：`docs/arch/00_index.md`
- 项目导航入口：`docs/arch/project_navigation__v0.1.0__ACTIVE__20260115.md`
- 外部输入入口：`docs/INPUTS/README.md`
- WebGPT 输入入口：`docs/INPUTS/WEBGPT/index.md`（对话）+ `docs/INPUTS/WEBGPT/memory.md`（记忆）

其余 README/报告只能**链接**到以上入口，不得成为新的“主入口”。

## 2) 目录分层（落点统一）

### `docs/arch/`（规范 / 设计 / 协议）
- 写“系统应该如何运作”，属于规则与结构。
- 变更频率低，但必须稳定可引用（SSOT）。

### `docs/spec/`（机器可读合约）
- JSON Schema、接口规范、验证器合约等。
- 任何自动化/门禁只认这里与其引用的事实源。

### `docs/INPUTS/`（外部输入 / 需求原文 / 可共享记忆）
- 写“外界提供了什么信息”（网页对话、会议纪要、需求原文）。
- 必须有来源与时间戳；允许增量更新；禁止把推理结果混进原文。

### `artifacts/` 与 `evidence/`（事实源 / 证据）
- 写“系统真实发生了什么”（SQLite、jsonl、logs、回执、状态文件）。
- `docs/` 只做入口与索引，不作为事实源。

## 3) 命名规则（名称一致）

### 规范型文档（强制版本化）
- 形如：`NAME__v0.1.0.md`（或带日期：`__20260201.md`）
- 内容必须包含：目标、范围、入口链接、落点约定、验收/失败模式。

### 报告型文档（可生成）
- 形如：`REPORT__TOPIC__v0.1__YYYYMMDD.md`
- 只能引用规范与证据，不得替代规范。

### 外部输入文档
- 放在 `docs/INPUTS/...`，必须含 `source` / `captured_at` / `page_url`（若适用）。

## 4) 一致性门禁（最低要求）

任何新增/修改规范型文档必须满足：
- 从 `docs/START_HERE.md` 或 `docs/arch/00_index.md` 可到达（可发现）
- 指向明确的事实源（例如 `artifacts/...`、schema、脚本入口）
- 不引入第二个“主入口”页面

建议用 `tools/scc/ops/docflow_audit.ps1` 做快速自检（见下）。

## 5) 与 AI 工作流的绑定（“文档管理一切”）

推荐每个 agent/流程都遵守：
1) 先读入口：`docs/START_HERE.md`
2) 读取 relevant spec：`docs/arch/` + `docs/spec/`
3) 注入外部输入：`docs/INPUTS/...`
4) 执行产生证据：`artifacts/...` / `evidence/...`
5) 回写导航（链接，而不是复制粘贴长文本）

## 6) 现实约束（允许的暂缓）

- 服务器“进程/端口归一化”与管理员权限相关项：允许进入 DLQ（见 `docs/ssot/05_runbooks/SCC_RUNBOOK__v0.1.0.md`）。
