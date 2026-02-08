# Navigation (Gateway 18788)

统一入口：`http://127.0.0.1:18788`  
文档入口：`/docs/INDEX.md`

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

## 1) Navigation
- `/docs`（默认展示 `docs/README.md`）
- `/nav`（本文件 JSON）

## 2) Rules / Control Plane
- `/config` / `/config/set`
- `/models` / `/models/set`
- `/designer/state` / `/designer/freeze`
- `/designer/context_pack`
- `/routes/decisions`
- `/events`

## 3) Maps (JSON)
- `/map` / `/axioms` / `/task_classes`
- `/pins/templates`（Pins 统一入口）
- `/pins/candidates`
- `/pins/guide/errors`
- `/errors/designer`
- `/errors/executor`
- `/errors/router`
- `/errors/verifier`
- `/roles/errors?role=pinser`

## SCC
- `/desktop` `/scc` `/dashboard` `/viewer` `/mcp/*`

## OpenCode
- `/opencode/*`
- `/opencode/global/health`

## Executor
- `POST /executor/jobs/atomic`
- `GET /executor/prompt?task_id=...`
- `GET /executor/leader`
- `GET /executor/debug/summary`
- `GET /executor/debug/failures`
- `GET /executor/workers`

## 无窗口后台运行
- 启动：`C:\scc\oc-scc-local\scripts\daemon-start.vbs`
- 停止：`C:\scc\oc-scc-local\scripts\daemon-stop.vbs`
