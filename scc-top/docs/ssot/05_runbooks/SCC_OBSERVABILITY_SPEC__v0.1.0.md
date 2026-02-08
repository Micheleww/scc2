---
oid: 01KGCV31ZNVTQPC0P28VK1K1D4
layer: CANON
primary_unit: S.CANONICAL_UPDATE
tags: [P.REPORT, V.VERDICT]
status: active
---

# SCC Observability Spec（v0.1.0 / SSOT）

目标：把 SCC 的关键指标“**口径统一** + **采集点明确** + **阈值可告警**”固化成单页 SSOT，支撑规模化压测与持续迭代。

## 0) 原则

- 指标必须能从事实源计算：`artifacts/`、`evidence/`、SQLite、jsonl 事件流。
- 指标口径先统一，再做看板；禁止“同名不同义”。
- 每个指标都有：**定义**、**采集点**、**计算方法**、**阈值**、**常见失败原因**。

## 1) 核心指标（SCC 任务执行）

### `pass_rate`
- 定义：在统计窗口内，`DONE` /（`DONE` + `FAIL`）的比例。
- 采集点：事件流（见 `docs/arch/ops/SCC_EVENT_MODEL__v0.1.0.md`）。
- 阈值：≥ 0.90（本地压测）；≥ 0.97（稳定运行）。

### `mean_retries`
- 定义：每个 task 的平均重试次数（一次 task_id 下的 attempt_count - 1）。
- 采集点：task attempt 事件 + 执行回执（exit_code）。
- 阈值：≤ 0.6（健康）；> 1.0 触发“混乱度治理”检查。

### `time_to_green`
- 定义：从 task 创建到首次 `DONE` 的耗时（秒/分）。
- 采集点：task.created_at 与 done_at（事件时间戳）。
- 阈值：P50 < 10min（本地）；P95 < 45min（含外部依赖除外）。

### `dlq_rate`
- 定义：进入 DLQ 的 task / 总 task。
- 采集点：DLQ 事件或 DLQ 目录落盘记录。
- 阈值：≤ 0.03（连续 3 天）。

## 2) 上下文与成本（可选但推荐）

### `tokens_per_task`
- 定义：每个 task 的总 tokens（prompt+completion），按 attempt 聚合。
- 采集点：LLM 调用日志/回执（若有）。
- 阈值：由预算策略决定；建议先建立基线（baseline）再做优化。

### `context_hit_rate`
- 定义：在注入 context/pins 时，命中“稳定前缀/缓存”的比例或命中数量。
- 采集点：路由器/编排器的注入记录 + 模型回执（若有 cached_tokens）。
- 阈值：随着 pins/map 引入逐步上升，先定目标 ≥ 0.70。

## 3) WebGPT 采集指标（对话/记忆落盘）

### `webgpt_intake_ok_rate`
- 定义：`/scc/webgpt/intake` 请求成功率（2xx / 总）。
- 采集点：`artifacts/webgpt/intake.jsonl` + server access log（如有）。
- 阈值：≥ 0.98（同一会话重复 sync 允许 dedupe，但不算失败）。

### `webgpt_export_skip_rate`
- 定义：导出请求中 `skipped=true` 的比例（表示“无增量变更”而不是失败）。
- 采集点：`/scc/webgpt/export` 响应 + `artifacts/webgpt/export_state.json`。
- 阈值：无硬阈值；用于确认“增量去重”生效。

### `webgpt_backfill_fail_rate`
- 定义：Backfill 的 fail / total（Electron 状态栏 `ok/fail/idx/total`）。
- 采集点：`artifacts/scc_state/browser_commands_ack.jsonl` + browser log。
- 阈值：≤ 0.05；若高于阈值，优先排查 DOM 选择器/登录重定向/网络波动。

### `webgpt_memory_capture_ok_rate`
- 定义：`/scc/webgpt/memory/intake` 成功率。
- 采集点：`artifacts/webgpt/memory.jsonl`
- 阈值：≥ 0.95（页面结构变动时可能短期下降，需要更新选择器）。

## 4) 指标落点（唯一推荐）

- 原始事件/证据：`artifacts/` 与 `evidence/`（append-only）
- 共享阅读入口：`docs/START_HERE.md` → `docs/arch/00_index.md`
- WebGPT 输入入口：`docs/INPUTS/WEBGPT/index.md` + `docs/INPUTS/WEBGPT/memory.md`

## 5) 最小告警规则（建议）

- `pass_rate` 连续 50 个 task < 0.85 → 阻断新任务进入执行池（只允许修复/回归）。
- `webgpt_backfill_fail_rate` > 0.10 → 停止 backfill，改为“手动打开会话 + Sync/Export”并更新选择器。
- `dlq_rate` 连续 7 天 > 0.05 → 开启“混乱度治理”迭代（清理入口/证据/运行态/孤儿文件）。
