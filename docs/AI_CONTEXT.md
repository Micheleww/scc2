# AI Context (Pins-first)

目标：让模型只读最小上下文，降低读仓成本，提升并行吞吐。

## 核心规则
1) 只给 3-10 个关键文件（不提供目录）
2) 大文件/日志不要进入 context pack
3) Executor 必须 pins-first，缺 pins 直接失败

## 入口
- 端点与控制面板：见 `docs/NAVIGATION.md`
- L0 原文仅 Designer 读取：`docs/SSOT.md`

## 推荐定位文件
- Gateway：`C:\scc\oc-scc-local\src\gateway.mjs`
- OpenCode：`C:\scc\opencode-dev\packages\opencode\src\server\server.ts`
- SCC routes：`C:\scc\opencode-dev\packages\opencode\src\server\routes\scc.ts`
- SCC modules：`C:\scc\opencode-dev\packages\opencode\src\scc\*`
- Tools registry：`C:\scc\opencode-dev\packages\opencode\src\tool\registry.ts`
- SCC router 参考：`C:\scc\scc-top\tools\scc\task_queue.py`

## 避免大文件
- `C:\scc\scc-top_extract_errors_last.log`（600MB，禁止进入上下文）
<!-- MACHINE:SSOT_AXIOMS_JSON -->
```json
{
  "ssot_hash": "sha256:TODO",
  "axioms": [
    "Executor never reads SSOT directly",
    "All tasks must use pins-first constraints"
  ],
  "ci_handbook": {
    "title": "CI 通过手册（必读）",
    "steps": [
      "确认改动文件都在 pins.allowed_paths 内，且未触碰 forbidden_paths。",
      "运行 allowedTests 中的自测命令（代码任务必须包含至少一条非 task_selftest 的真实测试）。",
      "在输出中追加 SUBMIT JSON：SUBMIT: {\"status\":\"pass\",\"reason_code\":\"...\",\"touched_files\":[\"file1\",\"file2\"],\"tests_run\":[\"your test cmd\"]}",
      "证据可裁决：exit_code=0，SUBMIT.touched_files 与实际改动一致，日志/补丁齐全。",
      "本地预检查：python scc-top/tools/scc/ops/task_selftest.py --task-id <task_id> 确认返回码 0。"
    ],
    "error_codes": [
      { "code": "ci_failed", "meaning": "测试命令执行失败或 exit_code!=0，先复现再补证据。" },
      { "code": "ci_skipped", "meaning": "缺少可执行测试命令；添加至少一条非 task_selftest 的 allowedTests。" },
      { "code": "tests_only_task_selftest", "meaning": "仅给了 task_selftest；补充真实测试命令后重试。" }
    ]
  }
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
      "allowed_paths": [
        "packages/opencode/src/scc/tasks.ts",
        "packages/opencode/src/server/routes/scc.ts"
      ],
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
      "allowed_paths": [
        "packages/opencode/src/config/config.ts",
        "packages/opencode/src/flag/flag.ts"
      ],
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
      "allowed_paths": [
        "docs/toolbox/PERMISSIONS.md",
        "docs/toolbox/ROADMAP.md"
      ],
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


