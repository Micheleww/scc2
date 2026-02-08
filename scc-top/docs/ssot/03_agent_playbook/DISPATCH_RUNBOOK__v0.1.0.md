---
oid: 01KGCV31MQTEK6X4ESZQ6XFEKF
layer: CANON
primary_unit: X.DISPATCH
tags: [A.FACTORY_MANAGER, A.ROUTER, A.EXECUTOR, A.AUDITOR, V.GUARD, V.VERDICT]
status: active
---

# Dispatch Runbook (v0.1.0)

Goal: teach agents to use agents (parallel dispatch) while staying inside SSOT + gate rules.

## 1) Leader chain (group lead / manager)
1. Route the task to a role (deterministic):
   - `python tools/scc/role_router.py --goal "<task goal>"`
2. Create a parent batch config (JSON) describing each parent task.
    - Example: `configs/scc/ssot_autonomy_batches__v0.1.0__20260201.json`
    - Mandatory per-parent fields:
      - `allowed_globs[]`: allowlist of repo-relative paths/globs the worker may touch
      - `isolate_worktree: true`: run inside an isolated git worktree and apply back via patch only
      - `embed_allowlisted_files: true` (recommended): embed deterministic snippet pack (HEAD/TAIL + rg hits) to avoid token-heavy file searching
    - When using `--dangerously-bypass`:
      - every parent MUST provide a non-empty `allowed_globs[]` (server rejects otherwise)
   - Helper (from existing task_tree + contract_ref, safe-by-default):
     - `python tools/scc/ops/dispatch_from_task_tree.py --taskcode <TaskCode> --limit 5 --area control_plane --emit-report`
     - Produces a ready config under `configs/scc/` with per-parent `allowed_globs=[<contract_ref>]` and deterministic embedding.
3. Dispatch via SCC automation runner:
   - Recommended (leader supervision bundled): `powershell -File tools/scc/ops/dispatch_with_watchdog.ps1 -Config <config.json> -Model gpt-5.2 -TimeoutS 1800 -MaxOutstanding 3`
   - Direct runner: `python tools/scc/automation/run_batches.py --config <config.json> --model gpt-5.2 --timeout-s 1800 --max-outstanding 3`
   - Deterministic helper (route + config scaffold): `python tools/scc/ops/dispatch_task.py --goal "<goal>" --parents-file <parents.json> --out-config <config.json>`
   - Note: PowerShell scripts may be blocked by execution policy; in that case prefer the Python runner + `dispatch_watchdog.py`.
4. Audit results:
   - `python tools/scc/ops/delegation_audit.py --automation-run-id <run_id>`
   - Each parent emits `scope_enforcement.json` in its artifacts dir, including allowlist, violations, and apply status.
4.1 Leader Board (mandatory for leader):
   - `python tools/scc/ops/leader_board.py`
   - Output:
     - `docs/REPORT/control_plane/LEADER_BOARD__LATEST.md`
   - Live waterfall (60s, optional):
     - `powershell -File tools/scc/ops/leader_board_stream.ps1 -EveryS 60 -LimitRuns 20`
5. Supervise & stop stuck workers (mandatory for leader):
   - Watch active runs (every 60s): `python tools/scc/ops/dispatch_watchdog.py --base http://127.0.0.1:18788 --poll-s 60 --stuck-after-s 60`
   - Manual cancel: `POST /executor/codex/cancel` with `{run_id, parent_id(optional), reason}`

## OID gate env (required for --run-mvm flows)
If you run any flow that executes `mvm-verdict` / `oid_validator`, set:
- `SCC_OID_PG_DSN` (DSN without password)
- `PGPASSWORD` (password via env only; do not commit)

## Phase4 profile env (recommended)
- `tools/ci/run_phase4_checks.py` supports profiles via `SCC_PHASE4_PROFILE`.
- Default: when `AREA=control_plane`, profile defaults to `control_plane` (scoped: SSOT topology + OID + ATA + SCC smoke).
- Override to full-repo checks with `SCC_PHASE4_PROFILE=repo` only when intentionally validating the entire repository.

## 2) Member chain (executor)
Member executors are CodexCLI workers invoked by `/executor/codex/run`.

Each member MUST:
- obey the scope and stop conditions included in the parent prompt
- keep changes minimal and deterministic
- write outputs into canonical/derived/evidence locations per WorkspaceSpec

## 3) Guard chain (auditor)
Depending on the flow:
- TaskCode/report flow: `python tools/ci/skill_call_guard.py --taskcode <TaskCode> --area <area>`
- SCC run flow: ensure `artifacts/scc_runs/<run_id>/evidence/verdict.json` exists; missing verdict is FAIL (fail-closed).
