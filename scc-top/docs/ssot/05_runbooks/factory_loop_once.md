---
oid: 01KGDDVYMH47M60KA7PVBH17FN
layer: DOCOPS
primary_unit: X.DISPATCH
tags: [V.VERDICT, P.REPORT, F.FEEDBACK_PACKAGE]
status: active
---

# Factory Loop Once (v0.1.0)

Goal: run one autonomous factory iteration:
`task_tree → contractize → scope_harden → execute+verify → review → feedback(raw-b) → DoD audit`.

## Command (recommended)
- `python tools/scc/ops/factory_loop_once.py --area control_plane --taskcode FACTORY_LOOP_ONCE_V010 --base http://127.0.0.1:18788 --model gpt-5.2 --poll-s 60 --stuck-after-s 60 --retries 3 --scope-harden-mode deterministic --run-secretary --regen-task-tree`

## Inputs
- Goal Brief (Secretary output, read-only): `docs/DERIVED/secretary/GOAL_BRIEF__LATEST.md`
- WebGPT raw exports: `docs/INPUTS/WEBGPT/`
- Derived task tree: `docs/DERIVED/task_tree.json`

## Outputs (must)
- Leader waterfall: `docs/REPORT/control_plane/LEADER_BOARD__LATEST.md`
- Factory loop summary: `docs/REPORT/control_plane/artifacts/FACTORY_LOOP_ONCE_V010/factory_loop_summary.json`
- Review feedback package: `docs/INPUTS/raw-b/review_feedback_<ts>.md`
- Canonical progress updated: `docs/CANONICAL/PROGRESS.md`
