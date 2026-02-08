# SCC Agent Envelope Schema (machine-facing)

## Overview
统一五类 `kind`，便于单解析器处理机器可消费内容；人类可读说明放在可选的 `note` 字段。

## Common Envelope
```json
{
  "kind": "TASK|EVENT|SUBMIT|STATUS|NOTE",
  "control": { /* 见各类最小字段 */ },
  "note": "(optional, markdown/plain text for humans)"
}
```

## TASK
- `kind`: "TASK"
- `task_id`: string
- `parent_task_id`: string|null
- `role`: string
- `title`: string
- `goal`: string
- `task_class`: string|null
- `allowed_tests.commands`: array (>=1, 至少一条非 `task_selftest`)
- `patch_scope.allow_paths`: array
- `acceptance`: array
- `pins_spec` 或 `context_pack_id`: object/string

## EVENT
- `kind`: "EVENT"
- `event_type`: string (如 CI_FAILED / PINS_INSUFFICIENT / FLOW_BOTTLENECK)
- `task_id`: string|null
- `timestamp`: ISO string
- `severity`: info|warn|error
- `payload`: object (自由，但可解析)

## SUBMIT
- `kind`: "SUBMIT"
- `task_id`: string
- `status`: DONE|NEED_INPUT|FAILED
- `exit_code`: integer
- `changed_files`: array
- `tests.commands`: array; `tests.passed`: boolean; `tests.summary`: string
- `artifacts`: {report_md, selftest_log, evidence_dir, patch_diff}
- `needs_input`: array<{question, why_needed, suggested_options[]}> (optional)

## STATUS
- `kind`: "STATUS"
- `task_id`: string|null
- `stage`: queued|running|ci|audit|done|failed
- `progress`: number|text
- `metrics`: {duration_ms, context_bytes, model, executor}

## NOTE
- `kind`: "NOTE"
- `text`: string (only for人读/提示，不驱动路由)
- `related_task_id`: string (optional)

## 用法建议
- 机器消费/路由/裁决：放入 `control` 严格 JSON。
- 解释/推理/复盘：放入 `note`，不进入状态机。
- 保证每条消息顶层都有 `kind`，便于单解析器分流。
