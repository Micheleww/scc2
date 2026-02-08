---
oid: 01KGCV322T8TTJBB1ZB4J6TQD4
layer: CANON
primary_unit: S.CANONICAL_UPDATE
tags: [S.CANONICAL_UPDATE]
status: active
---

# Current State (DoD-B Canonical Set)

## Fill-in rules
- One paragraph summary of today.
- Link evidence paths in `artifacts/...` or `evidence/...`.

## Snapshot
- 本机融合入口（OC×SCC Local Gateway）：`http://127.0.0.1:18788`
  - 任务板：`/board`
  - 资源池/并行：`/pools`
  - 近 6 小时统计：`/executor/debug/metrics?hours=6`
  - 配置入口：`/config`（写入 `tools/oc-scc-local/config/runtime.env`，重启 daemon 生效）
- SCC docker upstream（统一服务器容器）：`http://127.0.0.1:18789`（容器内 18788 → 主机 18789）
- 代码落点：`tools/oc-scc-local/`（gateway + worker + 任务板持久化）；Docker 重建策略：`tools/unified_server/docker/rebuild_if_needed.ps1`
