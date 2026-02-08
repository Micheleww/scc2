---
oid: 01KGCV31TZPTWGGVJ13RKRZ4F3
layer: CANON
primary_unit: D.TASKTREE
tags: [D.PRIORITIZE, K.CONTRACT_DOC]
status: active
---

# Task Tree (ACTIVE)

本文件是任务树的权威落点（EPIC → CAPABILITY → COMPONENT/JOB → TASK）。

规则：每个 TASK 必须有 `task_id` 与 `contract_ref`（允许占位合同），并最终回填 `touched_oids[]/evidence_oids[]/verdict`。

派生输出：`docs/DERIVED/task_tree.json`（由原始 WebGPT 导出生成）。

再生成命令：

```powershell
python tools/scc/raw_to_task_tree.py
```

同步到任务台账（用于 review/metrics）：

```powershell
python tools/scc/ops/sync_task_tree_to_scc_tasks.py --only-missing --emit-report --taskcode TASKTREE_SYNC_V010 --area control_plane
```

回填执行结果到 task_tree（仅回填已有 verdict 的任务，可选 mint evidence_oids）：

```powershell
python tools/scc/ops/backfill_task_tree_from_scc_tasks.py --only-with-verdict --limit 30 --emit-report --taskcode TASKTREE_BACKFILL_V010 --area control_plane
```
