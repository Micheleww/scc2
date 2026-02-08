---
oid: 01KGFC6MC4G3812V8S25DY7V5N
layer: ARCH
primary_unit: W.WORKSPACE
tags: [S.NAV_UPDATE, V.GUARD]
status: active
---

# Project Group — SCC Production Projects (v0.1.0)

本文件定义 SCC 的“工作区（workspace）+ 项目组（project group）+ 项目（projects）”最小结构，用于：
- 让任务/合同/执行器能确定落点（避免跨项目误改）。
- 让产物代码与证据能被正确归类（可审计、可回放）。

## 0. Workspace identity (normative)
- workspace_id: `scc-top`
- workspace_root: `<REPO_ROOT>`

> 注意：仓库目录名可变（例如 `<REPO_ROOT>`），但“工作区身份”以 `workspace_id` 为准，不以磁盘路径为准。

## 1. Project group (normative)
- project_group_id: `scc-top-products`
- projects (current):
  - `quantsys` — 量化金融（现有主工程）
  - `yme` — YME 连锁餐饮（产物项目）
  - `math_modeling` — 数模竞赛（产物项目）

## 2. Canonical project catalog (machine-readable)
权威机器索引：
- `docs/ssot/02_architecture/project_catalog.json`

规则（必须）：
- 每个合同（contract）必须声明其 `project_id`（来自 catalog）。
- 每个执行器 parent 必须使用该项目的 allowlist roots 生成 `allowed_globs[]`（scope gate）。
- 若无法确定 `project_id`，必须 STOP 并回到 S2（Task Derivation）补齐归类信息，不得猜测。

