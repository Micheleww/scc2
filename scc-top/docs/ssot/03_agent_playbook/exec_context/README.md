# Exec Context (JSON SSOT)

目标：把“阅读”变成“引用”，让 Executor 只消费 **Pins JSON + 最小切片**。

## JSON 载体
- `map.json` / `map.example.json`：模块索引与入口（Planner/Designer 用）
- `pins.schema.json` / `pins.example.json`：Executor 唯一允许的上下文
- `ssot_assumptions.schema.json` / `ssot_assumptions.example.json`：公理化前提
- `designer_state.schema.json` / `designer_state.example.json`：Designer L0/L1/L2

## 入口（网关 18788）
- `GET/POST /task_classes`
- `GET/POST /pins/templates`
- `GET/POST /designer/context_pack`

## Pins 引路员错题本（迭代清单）
常见失败类型：
- `missing_context`（文件列表不足或过宽）
- `non_json_output`（输出非纯 JSON）
- `paths_too_broad`（allowed_paths 过大）
- `no_line_windows`（缺少行窗或符号定位）
- `forbidden_missing`（缺少 forbidden_paths）

改进要求（引路员必须遵守）：
- 只输出 JSON（无前后文）
- `allowed_paths` 精确到文件/小目录
- 必须给 `max_files` / `max_loc`

错题本入口：
- `GET /pins/guide/errors`
