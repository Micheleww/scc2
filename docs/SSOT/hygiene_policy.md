# SCC Hygiene Policy (最低门槛)

目标：将“整洁”变成机器可判定的门禁，降低复杂度与后期维护成本。

## 产物与目录
- 运行产物仅允许落在 `artifacts/<task_id>/...`，默认 gitignore。
- 必备产物：`report.md`, `selftest.log`, `evidence/`, `patch.diff`, `submit.json`。
- 禁止在仓库根/源码目录生成：`tmp/`, `*.bak`, `*copy*`, `debug*`, 临时脚本等。
- TTL：产物默认保留 30 天，可归档/清理。

## 改动半径
- 每个任务必须声明 `write_allow_paths` / `read_allow_paths`（pins + contract）。
- CI 校验：改动超出 allowlist → 失败；新增文件必须有归属（manifest/submit.changed_files）。

## 协议与版本
- 控制面统一使用 JSON 信封，集中在 `contracts/`，带 `schema_version` 和 `kind`。
- 破坏性变更必须新版本，旧版兼容（只增不删字段）。

## 依赖与 ADR
- 新增依赖/目录/协议变更必须写 ADR（`docs/adr/ADR-YYYYMMDD-<slug>.md`，6 行：Context/Decision/Alternatives/Consequences/Migration/Owner）。

## 清洁检查（CI/Preflight）
- `workspace_clean_check`: git 状态需干净（仅允许本任务改动），无垃圾文件。
- `hygiene_validator`: 校验产物路径、allowlist 越界、临时文件、ADR 触发条件。

## 执行器合同补充
- 必须回传：`submit_json`（status/changed_files/tests/artifacts/exit_code/needs_input）。
- 必须提供 changed_files、新增文件列表；无测试或仅 task_selftest 直接 fail-close。

## 触发 hook
- 事件：`PINS_INSUFFICIENT` / `CI_FAILED` / `PREFLIGHT_FAILED` / `RETRY_EXHAUSTED` 必须写入事件总线，用于归因与 playbook。

遵循以上规则，默认进入 CI 门禁；不满足即 fail-close。
