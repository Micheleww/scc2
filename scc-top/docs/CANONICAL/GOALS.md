---
oid: 01KGCV323VZYA701QZAZ608FHD
layer: CANON
primary_unit: S.CANONICAL_UPDATE
tags: [S.CANONICAL_UPDATE]
status: active
---

# Goals (DoD-B Canonical Set)

## Fill-in rules
- Keep goals short and testable.
- Link to input source(s) in `docs/INPUTS/...`.
- If evidence exists, link the path in `artifacts/...`.

## Current goals
- 让 SCC 以“像 OpenCode 官方原生加功能”的方式深度融合进 OpenCode（本地使用、尽量保护 OpenCode 源码结构）。
- 统一入口端口：`18788`（gateway），并保持 SCC docker upstream 与本地代码同步可量化。
- 将 SCC 独有能力（任务分解/分配、模型路由、CLI 执行器、文档+Git 管理）以可配置模块接入 OpenCode 服务器启动链路。
- 建立可持续的“队长可观测性”与失败归因：成功率/失败码/耗时/模型对比，持续改进提示词与任务粒度。
