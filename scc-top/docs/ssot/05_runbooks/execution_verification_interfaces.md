---
oid: 01KGCV31W0C42YQHMVAT6FSR1H
layer: CANON
primary_unit: X.DISPATCH
tags: [X.EXEC_CODEXCLI, X.EXEC_VSCODE, V.TESTS, V.VERDICT]
status: active
---

# Executor / Verifier Interfaces (v0.1.0)

## 0. Purpose
Freeze deterministic boundaries between execution and verification.

## 1. Executor interface (mandatory)
Input:
- contract_ref (contract content)
- pins/map refs (scoped context)
- workspace_ref (repo + commit)

Output (must produce):
- diff/patch (or commit ref)
- stdout/stderr logs
- exit_code
- evidence_oids (logs/diffs/reports)
- touched_oids

## 2. Verifier interface (mandatory)
Input:
- workspace_ref
- acceptance (from contract)

Output (must produce):
- verdict: pass | fail
- fail_class (optional but recommended)
- evidence_oids (test logs)
- exit_code

SCC run verifier JSON (stable artifact):
- Write `evidence/verdict.json` under the run output dir (e.g. `artifacts/scc_runs/<run_id>/evidence/verdict.json`).
- Schema (required fields):
  - verdict: PASS | FAIL
  - fail_class: string | null
  - exit_code: int
  - evidence_paths: array of relative paths (relative to run output dir)
  - generated_utc: ISO-8601 UTC timestamp
- Fail-closed rule: if `verdict.json` is missing, treat the run as FAIL.
- fail_class taxonomy (<=10):
  - command_failed
  - command_denied
  - timeout
  - verifier_error
  - artifact_missing
  - verdict_missing
  - unknown

Schema (machine-readable, SSOT canonical):
- `docs/ssot/05_runbooks/verdict.schema.json`

Verifier runner (reference implementation):
- `python tools/scc/ops/contract_runner.py --contract <contract.json> --area <area> --taskcode <TaskCode>`

Stable per-task verdict pointer (verifier-owned, v0.1.0):
- `docs/REPORT/<area>/artifacts/<task_id>/verdict.json`
- Executor MUST NOT write under `docs/REPORT/**`.

## 3. Evidence rule
All outputs must be materialized as files and registered by OID (or at least index-only for reports).

## 3.1 Fail-closed gate (mandatory)
CI/verdict MUST run:
- `python tools/ci/run_phase4_checks.py` (includes `oid-validator`)
- `python tools/ci/mvm-verdict.py --case basic` (guard + triplet enforcement)

## 4. Changelog
- v0.1.0: initial
