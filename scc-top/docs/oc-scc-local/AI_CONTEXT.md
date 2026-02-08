# AI 阅读指南（让模型顺畅工作）

## 总原则

1) **不要给模型“全仓库”**：优先给 3–8 个关键文件 + 明确目标。
2) **避免大文件**：大于 1–2MB 的日志/锁文件/构建产物不要进上下文包。
3) **原子任务优先**：用 `/executor/jobs/atomic` 自动生成 context pack，并带 “10 分钟可完成”的约束。

## 推荐上下文入口（融合项目）

### 网关（oc-scc-local）

- `C:\scc\oc-scc-local\src\gateway.mjs`
- `C:\scc\oc-scc-local\scripts\start-all.ps1`
- `C:\scc\oc-scc-local\scripts\stop-all.ps1`

### OpenCode 源码（opencode-dev）

- Server mount：`C:\scc\opencode-dev\packages\opencode\src\server\server.ts`
- SCC routes：`C:\scc\opencode-dev\packages\opencode\src\server\routes\scc.ts`
- SCC modules：`C:\scc\opencode-dev\packages\opencode\src\scc\*`
- Tools registry：`C:\scc\opencode-dev\packages\opencode\src\tool\registry.ts`

### SCC 源码参考（scc-top）

- 模型路由参考：`C:\scc\scc-top\tools\scc\task_queue.py`

## 明确要避开的“大文件”

- `C:\scc\scc-top_extract_errors_last.log`（约 602MB）：不适合给模型阅读，也不应进 context pack。

## 推荐的“上下文包”做法

1) 先列出最可能需要的 3–10 个文件（不要给目录）。
2) 用 `POST /executor/contextpacks` 或 `/executor/jobs/atomic` 生成 pack。
3) 如果任务被阻塞，再追加 **最多 3 个文件**。

<!-- MACHINE:SSOT_AXIOMS_JSON -->
```json
{
  "ssot_hash": "sha256:TODO",
  "axioms": [
    "Executor never reads SSOT directly",
    "All tasks must use pins-first constraints"
  ]
}
```
<!-- /MACHINE:SSOT_AXIOMS_JSON -->

<!-- MACHINE:TASK_CLASS_LIBRARY_JSON -->
```json
{
  "version": "v1",
  "classes": [
    {
      "id": "schema_add_field_v1",
      "pins_template": "db/schema_core_v1",
      "allowlist_tests": ["db:migrate:smoke"],
      "acceptance_template": "Field added to schema without breaking existing migrations.",
      "stop_codes": ["pins_insufficient", "needs_split", "needs_upgrade"]
    },
    {
      "id": "scc_api_add_endpoint_v1",
      "pins_template": "scc_api_routes_v1",
      "allowlist_tests": ["scc:routes:smoke"],
      "acceptance_template": "New SCC endpoint added with schema and OpenAPI updated.",
      "stop_codes": ["pins_insufficient", "needs_split"]
    },
    {
      "id": "scc_task_store_update_v1",
      "pins_template": "scc_task_store_v1",
      "allowlist_tests": ["scc:tasks:smoke"],
      "acceptance_template": "Task store logic updated with backward compatibility preserved.",
      "stop_codes": ["pins_insufficient", "needs_upgrade"]
    },
    {
      "id": "scc_claim_lease_v1",
      "pins_template": "scc_claiming_v1",
      "allowlist_tests": ["scc:claim:smoke"],
      "acceptance_template": "Claim/release/lease endpoints and task semantics consistent.",
      "stop_codes": ["pins_insufficient", "needs_split"]
    },
    {
      "id": "model_router_rule_update_v1",
      "pins_template": "model_router_v1",
      "allowlist_tests": ["router:smoke"],
      "acceptance_template": "Routing logic updated and backward compatible.",
      "stop_codes": ["pins_insufficient", "needs_upgrade"]
    },
    {
      "id": "tool_registry_add_v1",
      "pins_template": "tool_registry_v1",
      "allowlist_tests": ["tool:registry:smoke"],
      "acceptance_template": "Tool registry updated with proper gating.",
      "stop_codes": ["pins_insufficient", "needs_split"]
    },
    {
      "id": "config_flag_add_v1",
      "pins_template": "config_flag_v1",
      "allowlist_tests": ["config:smoke"],
      "acceptance_template": "Config/flag added with defaults and documented behavior.",
      "stop_codes": ["pins_insufficient", "needs_split"]
    },
    {
      "id": "desktop_panel_update_v1",
      "pins_template": "desktop_panel_v1",
      "allowlist_tests": ["desktop:smoke"],
      "acceptance_template": "Desktop panel update compiles and routes correctly.",
      "stop_codes": ["pins_insufficient", "needs_split"]
    },
    {
      "id": "desktop_menu_update_v1",
      "pins_template": "desktop_menu_v1",
      "allowlist_tests": ["desktop:smoke"],
      "acceptance_template": "Desktop menu update compiles and matches UX rules.",
      "stop_codes": ["pins_insufficient", "needs_split"]
    },
    {
      "id": "app_scc_machine_update_v1",
      "pins_template": "app_scc_machine_v1",
      "allowlist_tests": ["app:scc:smoke"],
      "acceptance_template": "SCC machine state transitions updated safely.",
      "stop_codes": ["pins_insufficient", "needs_split"]
    },
    {
      "id": "toolbox_permissions_update_v1",
      "pins_template": "toolbox_permissions_v1",
      "allowlist_tests": ["toolbox:smoke"],
      "acceptance_template": "Toolbox permissions doc updated with precedence rules.",
      "stop_codes": ["pins_insufficient"]
    }
  ]
}
```
<!-- /MACHINE:TASK_CLASS_LIBRARY_JSON -->

<!-- MACHINE:PINS_TEMPLATES_JSON -->
```json
{
  "version": "v1",
  "templates": [
    {
      "id": "db/schema_core_v1",
      "allowed_paths": ["src/db/schema.sql"],
      "forbidden_paths": ["infra/"],
      "symbols": [],
      "line_windows": {},
      "max_files": 2,
      "max_loc": 200
    },
    {
      "id": "scc_api_routes_v1",
      "allowed_paths": ["packages/opencode/src/server/routes/scc.ts"],
      "forbidden_paths": [],
      "symbols": [],
      "line_windows": {},
      "max_files": 2,
      "max_loc": 220
    },
    {
      "id": "scc_task_store_v1",
      "allowed_paths": ["packages/opencode/src/scc/tasks.ts"],
      "forbidden_paths": [],
      "symbols": [],
      "line_windows": {},
      "max_files": 2,
      "max_loc": 220
    },
    {
      "id": "scc_claiming_v1",
      "allowed_paths": ["packages/opencode/src/scc/tasks.ts", "packages/opencode/src/server/routes/scc.ts"],
      "forbidden_paths": [],
      "symbols": [],
      "line_windows": {},
      "max_files": 3,
      "max_loc": 260
    },
    {
      "id": "model_router_v1",
      "allowed_paths": ["packages/opencode/src/scc/model-router.ts"],
      "forbidden_paths": [],
      "symbols": [],
      "line_windows": {},
      "max_files": 2,
      "max_loc": 220
    },
    {
      "id": "tool_registry_v1",
      "allowed_paths": ["packages/opencode/src/tool/registry.ts"],
      "forbidden_paths": [],
      "symbols": [],
      "line_windows": {},
      "max_files": 2,
      "max_loc": 220
    },
    {
      "id": "config_flag_v1",
      "allowed_paths": ["packages/opencode/src/config/config.ts", "packages/opencode/src/flag/flag.ts"],
      "forbidden_paths": [],
      "symbols": [],
      "line_windows": {},
      "max_files": 3,
      "max_loc": 240
    },
    {
      "id": "desktop_panel_v1",
      "allowed_paths": ["packages/desktop/src/index.tsx"],
      "forbidden_paths": [],
      "symbols": [],
      "line_windows": {},
      "max_files": 2,
      "max_loc": 240
    },
    {
      "id": "desktop_menu_v1",
      "allowed_paths": ["packages/desktop/src/menu.ts"],
      "forbidden_paths": [],
      "symbols": [],
      "line_windows": {},
      "max_files": 2,
      "max_loc": 220
    },
    {
      "id": "app_scc_machine_v1",
      "allowed_paths": ["packages/app/src/scc/machine.ts"],
      "forbidden_paths": [],
      "symbols": [],
      "line_windows": {},
      "max_files": 2,
      "max_loc": 240
    },
    {
      "id": "toolbox_permissions_v1",
      "allowed_paths": ["docs/toolbox/PERMISSIONS.md", "docs/toolbox/ROADMAP.md"],
      "forbidden_paths": [],
      "symbols": [],
      "line_windows": {},
      "max_files": 2,
      "max_loc": 180
    }
  ]
}
```
<!-- /MACHINE:PINS_TEMPLATES_JSON -->
## Pins 引路员错题本（Guide Memory）
常见失败类型（引路员应规避）：
- `missing_context`：给定 files 不足以定位 pins（需补文件列表）
- `pins_missing`：输出非 pins JSON（必须输出 pins 或 error）
- `line_windows_empty`：未给任何行窗/符号且 allowed_paths 过大
- `forbidden_paths_missing`：未写 forbidden_paths（默认应填空数组）

错题本入口：
- `GET /pins/guide/errors`
