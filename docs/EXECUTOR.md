# Executor (Atomic Only)

This document defines the *fail-closed* execution contract for SCC atomic tasks.

## Hard Constraints (Fail-Closed)
- Executor MUST be pins-first: it may only read paths that are inside the task pins allowlist.
- If pins are missing/insufficient, the task MUST fail with `PINS_INSUFFICIENT`. No guessing, no repo-wide scanning.
- Executor MUST NOT read SSOT directly (SSOT is for control-plane roles only).
- Executor MUST keep the workspace clean: no stray scripts/files outside `artifacts/<task_id>/`.

## Required Outputs (Every Task)
Executor output MUST include these four lines (machine-parsable):
```text
REPORT: <one-line outcome>
SELFTEST.LOG: <commands run or 'none'>
EVIDENCE: <paths or 'none'>
SUBMIT: {"status":"DONE|NEED_INPUT|FAILED","reason_code":"...","touched_files":[...],"tests_run":[...]}
```

Notes:
- `SUBMIT` MUST be strict JSON.
- `touched_files` MUST include any file changed by the patch/diff.
- `tests_run` MUST include at least one non-`task_selftest` command for patch-producing roles (engineer/integrator/qa/doc/...).

## Entry Points
- `POST /executor/jobs/atomic`
- Related control-plane + gates are listed in `docs/NAVIGATION.md`.

