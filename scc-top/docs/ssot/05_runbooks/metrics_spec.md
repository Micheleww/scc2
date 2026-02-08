---
oid: 01KGCV31X238VFWBCQ7FYF9SW5
layer: CANON
primary_unit: P.DELTA
tags: [V.VERDICT, N.EVENTS, P.REPORT]
status: active
---

# Metrics Spec (v0.1.0)

## 0. Purpose
Define minimum metrics required to claim “factory progress”.

## 1. Minimum metrics (mandatory)
- pass_rate: % tasks passing without manual intervention
- mean_retries: average retries per task
- time_to_green: queued → passed duration (p50/p95)
- top_fail_codes: distribution of failure classes
- oid_coverage: % objects in mandatory trees with embedded oid + registry entries
- ingestion_lag: raw captured → task derived latency

## 2. Measurement sources (normative)
- task metadata: `artifacts/scc_tasks/**/task.json`
- task events: `artifacts/scc_tasks/**/events.jsonl`
- run metadata: `artifacts/scc_runs/**/evidence/run_meta.json`
- review outputs: `docs/CANONICAL/PROGRESS.md`, `docs/INPUTS/raw-b/`

## 3. Calculation notes (normative)
- pass_rate: PASS verdicts / total verdicts present in `task.json`
- mean_retries: average of (executor_completed events per task - 1), floor at 0
- time_to_green: `updated_utc - created_utc` for PASS tasks (p50/p95)
- top_fail_codes: reason_code from failed executor events; fallback to non-zero exit_code
- oid_coverage: report as n/a unless registry artifacts are present in artifacts inputs
- ingestion_lag: `task_submitted ts_utc - created_utc` (p50/p95), fallback to earliest event

## 4. Reporting cadence
Reported at each Review cycle (see review_progress.md).

## 5. Changelog
- v0.1.0: initial
- v0.1.1: add artifacts-based measurement notes
