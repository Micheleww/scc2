# Navigation (Gateway 18788)

统一入口：http://127.0.0.1:18788
文档入口：/docs/INDEX.md

<!-- MACHINE:PROJECT_MAP_JSON -->
```json
{
  "version": "v1",
  "generated_at": "2026-02-04T00:00:00Z",
  "areas": {
    "gateway": { "path": "oc-scc-local/src/", "owner": "integrator", "stable": true }
  },
  "entry_points": { "gateway": ["gateway.mjs"] },
  "forbidden_paths": ["tools/unified_server/", "artifacts/"]
}
```
<!-- /MACHINE:PROJECT_MAP_JSON -->
## 入口
- `/docs/INDEX.md`
- `/nav`（本文件 JSON）

## Control Plane
- `/config` / `/config/set`
- `/models` / `/models/set`
- `/prompts/registry` / `/prompts/render`
- `/designer/state` / `/designer/freeze`
- `/designer/context_pack`
- `/factory/policy` / `/factory/wip` / `/factory/degradation` / `/factory/health`
- `/factory/routing?event_type=CI_FAILED`
- `/verdict?task_id=...`
- `/routes/decisions`
- `/events`

## Maps (JSON)
- `/map` / `/axioms` / `/task_classes`
- Map v1（结构化索引）：`/map/v1` / `/map/v1/version` / `/map/v1/query?q=...` / `/map/v1/link_report`
- Pins Builder v1（Map-first）：`POST /pins/v1/build`
- Pins Builder v2（Audited Pins：reason/read_only/write_intent）：`POST /pins/v2/build`
- Preflight Gate v1：`POST /preflight/v1/check`
- `/pins/templates`
- `/pins/candidates`
- `/pins/guide/errors`
- `/errors/designer`
- `/errors/executor`
- `/errors/router`
- `/errors/verifier`
- `/roles/errors?role=pinser`

## Upstreams
- SCC: `/desktop` `/scc` `/dashboard` `/viewer` `/mcp/*`
- OpenCode: `/opencode/*` `/opencode/global/health`

## Executor
- `POST /executor/jobs/atomic`
- `GET /executor/prompt?task_id=...`
- `GET /executor/leader`
- `GET /executor/debug/summary`
- `GET /executor/debug/failures`
- `GET /executor/workers`

## CI/门禁
- `C:\scc\scc-top\docs\START_HERE.md`（CI/门禁入口与脚本）
- `C:\scc\scc-top\docs\ssot/02_architecture/SCC_TOP.md`（CI/verdict 门禁要求）
- `C:\scc\tools\scc\gates\run_ci_gates.py`（本仓库最小门禁：Contracts/Hygiene/Secrets/Events/SSOT/SSOT_MAP/DocLink/Map/Schema/Connectors/SemanticContext/Release；会写 verdict.json；`--strict` 可禁用 artifact backfill 以 fail-closed）
- `C:\scc\tools\scc\gates\contracts_gate.py`（硬合同门禁：submit/preflight/pins/replay_bundle 必须存在且过 schema）
- `C:\scc\tools\scc\gates\event_gate.py`（事件门禁：每个任务必须有 `artifacts/<task_id>/events.jsonl`，至少 1 条 `scc.event.v1` SUCCESS/FAIL 事件）
- `C:\scc\tools\scc\gates\secrets_gate.py`（密钥门禁：禁止明文 token/key；禁止触碰 `secrets/**` 明文目录；仅允许 `.scc_secrets/*.secrets.enc.json` 作为加密容器）
- `C:\scc\tools\scc\gates\release_gate.py`（出货门禁：触碰 `releases/**/release.json` 时，release record 必须过 schema 且引用文件存在）
- `C:\scc\tools\scc\gates\connector_gate.py`（连接器门禁：`connectors/registry.json` 必须存在且结构化合法）
- `C:\scc\tools\scc\gates\semantic_context_gate.py`（共享上下文门禁：`semantic_context/index.jsonl` 必须存在且行级结构合法）
- `C:\scc\tools\scc\ops\backfill_events_v1.py`（存量 artifacts 迁移：补齐缺失 `events.jsonl` 以便 strict gates 可回放/可审计）
- `C:\scc\contracts\verdict\verdict.schema.json`（verdict 输出 schema；`run_ci_gates.py` 会写 `artifacts/<task_id>/verdict.json`）
- `C:\scc\docs\SSOT\registry.json`（SSOT facts registry；ssot_map_gate 会输出 `artifacts/<task_id>/ssot_update.json` 建议）
- `C:\scc\tools\scc\ops\ssot_sync.py`（将 `artifacts/<task_id>/ssot_update.json` 可控同步回 `docs/SSOT/registry.json`；支持 dry-run；会写 `artifacts/<task_id>/ssot_update.patch`）
- `C:\scc\tools\scc\ops\pr_bundle_create.py`（将 patch 封装为离线 PR bundle；git 仓库可选 `--apply-git` + `--merge-to <branch>` 自动 commit/merge；仍需 gates+审计）
- `CI gate role routing`（Gateway 自动闭环）：当 CI gate 失败时，优先按失败 gate 路由到专职角色修复（`map_curator`/`auditor`/`ssot_curator`），否则才回退到 `ci_fixup`。可用 env `CI_GATE_ROLE_ROUTING=false` 禁用。
- `C:\scc\factory_policy.json`（WIP/背压/熔断/降级矩阵）
- `C:\scc\artifacts\executor_logs\ci_gate_results.jsonl`（CI 结果证据）
- `C:\scc\artifacts\<task_id>\contracts_backfill.json`（当 gates 在非 strict 模式下补齐缺失 preflight/pins/replay_bundle 时的审计记录）
- `http://127.0.0.1:18788/learned_patterns/summary`（失败模式汇总 → 可触发厂长处理）
- `http://127.0.0.1:18788/replay/task?task_id=...`（单任务回放：改了哪里/测了什么/证据在哪）

## Models（Codex）
- 默认与偏好顺序：`oc-scc-local/config/runtime.env`（`CODEX_MODEL` / `CODEX_MODEL_PREFERRED` / `WORKER_MODELS_CODEX`）

## Role Policy (Fail-Closed)
- SCC 在创建任务与派发任务时都会执行 role policy 校验（read/write allowlist/denylist + skills 矩阵），不满足即拒绝（`role_policy_violation`）。

## Flows（B 模式轻量模板）
- `C:\scc\docs\flows\README.md`
- `C:\scc\docs\flows\flow__feature_patch_v1.md`
- `C:\scc\docs\flows\flow__doc_update_v1.md`
- `C:\scc\docs\flows\flow__ci_fixup_v1.md`

## Daemon
- 启动：`C:\scc\oc-scc-local\scripts\daemon-start.vbs`
- 停止：`C:\scc\oc-scc-local\scripts\daemon-stop.vbs`
