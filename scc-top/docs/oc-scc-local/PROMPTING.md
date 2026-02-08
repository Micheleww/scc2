# 给 CLI 的任务拆分与提示词规范（队长规则）

目标：保证单个 CLI 子任务 **不太大、不太小**，可在 10 分钟左右完成，并且输出可直接用于合并（diff/patch/命令）。

## 任务大小定义

### 太大（禁止）

任何满足下列之一都算“太大”：
- “深度阅读整个仓库/全量去重/全量重构”
- 一次要求跨多个包（例如 server + desktop + toolchain）同时落地
- 没有明确交付物（只是“研究一下/给计划”）

处理方式：拆成 3–7 个原子任务（每个任务只涉及 1 个主题 + 最多 5 个文件）。

### 太小（不推荐）

任何满足下列之一都算“太小”：
- 只有一句“看看能不能/解释一下”但不产出文件变更、命令或结论
- 让 CLI 输出“我建议…”但没有落地项

处理方式：把交付物写清楚，例如“输出 patch blocks”“给出 3 个函数签名”“给出 endpoints 列表 + 示例请求”等。

## 原子任务模板（推荐用于 `/executor/jobs/atomic`）

### Goal（必须）

- 一句话描述 + 完整交付物列表
- 以“可验证”为导向（改哪些文件、增加哪些 endpoint、输出哪些 diff）

### Constraints（必须）

- “禁止扫仓库/禁止 broad search”
- “最多打开 3 个额外文件”
- “只输出 patch blocks（`*** Begin Patch`）或精确命令”

### Scope（建议）

给出最多 3–6 个文件路径作为上下文包（不要给目录、不要给 100+ 文件）。

## 队长验收规则（fail-closed）

满足任意条件即判失败并重跑：
- 输出没有 diff/patch/命令/文件清单（只有摘要）
- 输出包含大范围扫描建议（`rg -g*`、全仓库遍历等）
- 输出没有可执行性（缺少路径/缺少接口/缺少参数）

## occli（OpenCode CLI）额外规则

- 默认不给它“读仓库任务”，只做 **文档/UX/接口草案**（并且要给足上下文包）
- 若出现 bun 插件安装失败（`BunInstallFailedError`），优先走执行器内置的“禁用项目配置”路径

## Designer Split 模板（父任务拆解）
目标：把父任务拆成 ≤10 分钟可执行的子任务，并为每个子任务补齐**岗位 skills + 文档/规则/地图引脚**，避免 worker 扫仓库。

要求（强制）：
- 输出必须是 JSON 数组（禁止任何 JSON 之外的 prose）
- 每个子任务必须包含字段：`title`, `goal`, `role`, `skills`, `pointers`, `allowedExecutors`, `allowedModels`, `files`, `runner`, `status`
- `pointers` 建议默认：
  - docs：`http://127.0.0.1:18788/docs/NAVIGATION.md`, `http://127.0.0.1:18788/docs/AI_CONTEXT.md`
  - rules：`http://127.0.0.1:18788/docs/PROMPTING.md`, `http://127.0.0.1:18788/docs/EXECUTOR.md`
  - status：`http://127.0.0.1:18788/docs/STATUS.md`

提示词骨架（给 designer CLI）：
```
You are a DESIGNER role. Decompose the parent goal into atomic subtasks.
Output MUST be a JSON array. No prose outside JSON.
Each subtask must be completable in <= 10 minutes by a CLI worker.
Do NOT scan the repo. Use ONLY provided context + pointers.
For each subtask include: role + skills + pointers(docs/rules/maps).
```
