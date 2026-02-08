---
oid: 01KGCV31Y49D1KZYEP5F3DX140
layer: CANON
primary_unit: P.REPORT
tags: [P.TRIGGER, F.FEEDBACK_PACKAGE, S.CANONICAL_UPDATE]
status: active
---

# Review / Progress Runbook (v0.1.0)

## 0. Purpose
Make progress measurable and feed it back into the loop.

## 1. OR-trigger (mandatory)
Review MUST run when ANY holds:
- 30 tasks attempted/completed
- 48 hours elapsed
- milestone achieved
- anomaly detected (failure spike, repeated fail codes, health degradation)

## 2. Outputs (mandatory)
A) Progress Report (canonical)
- coverage: which goals/epics
- done/doing/blocked summary
- delta_to_goal (quantified)
- risks & blockers
- next priorities (ranked)
- evidence refs (oids/paths)

B) Feedback Package (raw-b)
- what changed since last cycle
- next task queue proposal
- questions requiring human decision (if any)

C) Metrics Summary
- pass_rate
- mean_retries
- time_to_green (p50/p95)
- top_fail_codes
- oid_coverage
- ingestion_lag

## 3. Storage rule
Progress Report goes to Canonical set.
Feedback Package is append-only raw-b.
Metrics Summary is included in both Progress Report and Feedback Package.

## 4. Review job (implementation)
Run `tools/scc/review_job.py` to compute metrics and write outputs:
- appends progress update to `docs/CANONICAL/PROGRESS.md`
- creates feedback package in `docs/INPUTS/raw-b/`
- uses artifacts from `artifacts/scc_tasks/` and `artifacts/scc_runs/` only

Wrapper (emits TaskCode report + runs verdict gate):
- `python tools/scc/ops/review_job_run.py --taskcode REVIEW_JOB_V010 --area control_plane --run-mvm`

## 5. Changelog
- v0.1.0: initial
- v0.1.1: add metrics summary + review job implementation notes
