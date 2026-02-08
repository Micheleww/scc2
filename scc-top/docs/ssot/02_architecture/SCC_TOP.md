---
oid: 01KGCV31J4D83WP3REZ575RJC3
layer: ARCH
primary_unit: S.CANONICAL_UPDATE
tags: [S.NAV_UPDATE]
status: active
---

# SCC_TOP — Autonomous Code Factory Constitution (v0.1.0)

## 0. Status
- status: active
- version: v0.1.0
- scope: top-level governance only

## 0.1 SSOT Authority (mandatory)
Authoritative navigation chain:
- `docs/START_HERE.md`
- `docs/ssot/00_index.md`
- `docs/ssot/_registry.json`

## 1. What belongs here (and what MUST NOT)

### 1.1 Allowed in TOP
TOP may contain only:
1) North Star (system goal)
2) Global structure / registries (coordinate systems, required invariants)
3) Update & demotion protocol (how TOP stays TOP)
4) Changelog (explicit add/change/move/remove)

### 1.2 Forbidden in TOP (must be demoted to leaf docs)
- Detailed procedures, long templates, or constant blocks
- Full schemas (only links)
- Runbooks beyond 1-paragraph summary

### 1.3 Demotion rule (mandatory)
If any TOP section exceeds 80 lines OR ~800 chars:
- Move the full content to an appropriate leaf doc under `docs/ssot/`
- Replace in TOP with 1-sentence summary + link
- Record in Changelog under “Moved/Demoted” including what was removed from TOP and where it was moved

## 2. North Star
SCC is a fully automated code factory driven by document flow:
Goal Intake → Task Derivation → Contract → Execute+Verify → Review → Synthesize Canonical → Feedback to Raw.

Human-in-the-loop:
- Web chat is the highest-priority goal input source (latest intent).
Self-driven:
- Allowed only within existing contracts/backlog; must not overwrite human goals.

## 3. Closed-loop stages (S1..S7)
- S1 Raw Intake
- S2 Task Derivation
- S3 Contract
- S4 Execute + Verify
- S5 Review / Audit
- S6 Synthesize Canonical
- S7 Feedback to Raw

Note: detailed procedures are defined in DOCOPS leaf docs; TOP only defines the stage names and governance.

### 3.1 SSOT authority chain (single canonical trunk)
SSOT Trunk is the only canonical carrier for governance docs (conventions/architecture/playbook/contracts/runbooks/index).
All new governance content MUST land under docs/ssot/ and be reachable via its START_HERE + registry.json.
Hard gate: verdict/CI MUST run `top_validator` and fail-closed if SSOT topology breaks.
Refs:
- docs/ssot/START_HERE.md
- docs/ssot/00_index.md
- docs/ssot/registry.json

### 3.2 Canonical truth set & conflict priority
Only the Canonical Set is considered “current truth”; raw inputs are evidence only.
Priority on conflict: Human Goal Input (web chat) > Contract backlog > Self-driven improvements.
Ref:
- docs/ssot/02_architecture/canonical_truth.md

### 3.3 Task model & codes (how every task locates its level)
All work MUST locate itself in the hierarchy: EPIC → CAPABILITY → COMPONENT/JOB → TASK.
Every executable TASK MUST have a contract_ref and MUST report touched_oids + evidence_oids.
Ref:
- docs/ssot/04_contracts/task_model.md

### 3.4 Contract minimum spec (machine-executable)
Any executable TASK MUST be contractized with at least:
goal / scope_allow / constraints / acceptance / stop_condition / commands_hint.
Verifier MUST judge only by acceptance outcomes.
Ref:
- docs/ssot/04_contracts/contract_min_spec.md

### 3.5 Executor / Verifier interfaces (deterministic boundaries)
Executor input: contract + pins/map; output: diff/log/exit_code + evidence_oids.
Verifier input: workspace + acceptance; output: verdict(pass/fail + class) + evidence_oids.
Ref:
- docs/ssot/05_runbooks/execution_verification_interfaces.md

### 3.6 Review cadence & outputs (OR-trigger)
Review MUST run when ANY holds: 30 tasks | 48h | milestone | anomaly.
Outputs MUST include: Progress Report (canonical) + Feedback Package (raw-b).
Ref:
- docs/ssot/05_runbooks/review_progress.md

### 3.7 Metrics & factory acceptance (minimum)
Factory health MUST be measurable. Minimum metrics:
pass_rate, mean_retries, time_to_green, top_fail_codes, oid_coverage, ingestion_lag.
Ref:
- docs/ssot/05_runbooks/metrics_spec.md

## 4. Object Identity (OID) — Mandatory (v0.1.0)
All durable objects MUST have a stable `oid` (ULID). This applies to:
- governance docs under `docs/ssot/**`, `docs/DOCOPS/**`, `docs/CANONICAL/**`, `docs/ARCH/contracts/**`
- raw captures, derived artifacts, and any file materialized as part of SCC workflows

### 4.1 Requirements
- OID type: ULID (canonical).
- Issuance: OIDs MUST be minted only by SCC OID Generator (single source of issuance).
- Embedding: OID MUST be embedded inline in file headers for:
  - `docs/ssot/**`
  - `docs/DOCOPS/**`
  - `docs/CANONICAL/**`
  - `docs/ARCH/contracts/**`
  - (docs/REPORT/** is index-only in v0.1.0; no inline requirement)
  - NOTE: `docs/ARCH/**` (outside `docs/ARCH/contracts/**`) is treated as legacy / demotion-in-progress in v0.1.0; do not enforce inline OID there until migrated into SSOT.
- Stability: `oid` MUST NOT change across rename/move/refactor.
- Classification: each object MUST have exactly one `primary_unit` (mutually exclusive) and MAY have `tags[]` (multi-select).
- Migration: any rename/move or classification change MUST use Unified Migration Protocol via SCC OID Generator; `oid` remains unchanged.

### 4.2 Authority and gate
- PostgreSQL is the authoritative registry (object_index).
- Inline metadata MUST match PostgreSQL records; PostgreSQL is source of truth.
- CI/verdict MUST run `oid_validator`; failures MUST block merge/push.

References:
- `docs/ssot/01_conventions/OID_SPEC__v0.1.0.md`
- `docs/ssot/01_conventions/UNIT_REGISTRY__v0.1.0.md`

## 5. Top Checklist (titles only)
- Canonical Truth Set & Priority: `docs/ssot/02_architecture/canonical_truth.md`
- Task Model & Codes: `docs/ssot/04_contracts/task_model.md`
- Contract Minimum Spec: `docs/ssot/04_contracts/contract_min_spec.md`
- Executor/Verifier Interfaces: `docs/ssot/05_runbooks/execution_verification_interfaces.md`
- Review / Progress Runbook: `docs/ssot/05_runbooks/review_progress.md`
- Metrics Spec: `docs/ssot/05_runbooks/metrics_spec.md`

## 6. Changelog

### v0.1.0
Added:
- OID governance (ULID, Postgres authority, inline embedding for key doc trees, migrate-required, validator gate).
Changed:
- N/A
Moved/Demoted:
- N/A
Removed/Deprecated:
- N/A
Rationale:
- Ensure object-level traceability and fail-closed governance for a document-driven code factory.
