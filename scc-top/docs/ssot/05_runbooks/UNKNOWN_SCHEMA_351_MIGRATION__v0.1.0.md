---
oid: 01KGDVHWEVRP06ZH4HM99JVE8K
layer: DOCOPS
primary_unit: P.TRIGGER
tags: [D.TASKTREE, F.FEEDBACK]
status: active
---

# Unknown Schema (count=351) — Migration + DLQ Policy (v0.1.0)

## Purpose
Handle `unknown_schema` task ledger records **without inventing goals** (“不可虚构”).

In v0.1.0, `unknown_schema` means:
- `artifacts/scc_tasks/<task_id>/task.json` has neither `request.contract_ref` nor `request.task.goal`.

## Normative rules
- DO NOT contractize unknown_schema tasks (no virtual `goal`, no fabricated `acceptance`).
- Unknown_schema tasks MUST be routed to DLQ and re-intake pipeline.
- Re-intake MUST be additive (append-only): create a new Goal Brief / Feedback Package; do not mutate raw inputs.

## DLQ strategy (v0.1.0)
1) Audit & queue (deterministic):
   - Run: `python tools/scc/ops/unknown_schema_351_migration.py --emit-report`
   - Output queue: `docs/DERIVED/dlq/unknown_schema_tasks__v0.1.0.jsonl`
2) Secretary stage (human intent compilation):
   - Read raw evidence referenced by each task record.
   - Produce/refresh `docs/DERIVED/secretary/GOAL_BRIEF__LATEST.md` and/or per-item Goal Briefs under `docs/INPUTS/`.
3) Derive → TaskTree:
   - Re-derive tasks from Goal Brief into `docs/DERIVED/task_tree.json` (append new tasks, do not rewrite history).
4) Contractize:
   - Contractize only tasks with executable `goal` → `docs/ssot/04_contracts/generated/*.json`

## Stop condition
If a task cannot be recovered into a non-fabricated goal (insufficient evidence), it stays in DLQ with reason `missing_goal`.

## References
- Task ledger audit: `python tools/scc/ops/task_ledger_audit.py`
- Secretary Goal Brief generator: `python tools/scc/ops/secretary_goal_brief_from_webgpt.py`

