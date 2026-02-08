---
oid: 01KGEJFSP1YPV36VREP02TV54A
layer: DOCOPS
primary_unit: V.GUARD
tags: [S.NAV_UPDATE]
status: active
---

# Doc Registry（v0.1.0）

本文件定义 SCC 文档系统的“机器可读索引”入口，用于让本地模型/agent 稳定拼装上下文，并确保“权威路径唯一”。

## 1) 权威索引文件（机器可读）

- `docs/ssot/registry.json`（alias：`docs/ssot/_registry.json`）

## 2) 使用方式（AI 拼装上下文）

1) 固定先读：`docs/START_HERE.md`
2) 再读顶层治理：`docs/ssot/02_architecture/SCC_TOP.md`
3) 再读 Docflow 规则：`docs/ssot/01_conventions/DOCFLOW_SSOT__v0.1.0.md`
4) 按 `_registry.json` 选择相关 leaf docs（按 EPIC/CAPABILITY/COMPONENT/JOB/TASK）
5) 注入输入：`docs/INPUTS/...`
6) 证据只从：`artifacts/...` / `evidence/...` 读取与引用

## 3) 维护规则（最小）

- `_registry.json` 只记录“权威路径”和“拼装顺序”，不复制长文内容。
- 任意新增规范/作业手册，必须：
  - 放入 `docs/ssot/` 的对应分区（canonical）
  - 在 `_registry.json` 登记 doc_id 与 canonical_path
  - 从 `docs/START_HERE.md` 可达（直接或经分区索引）
