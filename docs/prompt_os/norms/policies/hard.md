# Hard Policies

> Violation of any hard policy results in **immediate task failure**.

## Table of Contents
- [1. File Scope Enforcement](#1-file-scope-enforcement)
- [2. Schema Compliance](#2-schema-compliance)
- [3. Test Gate](#3-test-gate)
- [4. WIP Limits](#4-wip-limits)
- [5. Budget Limits](#5-budget-limits)

---

## 1. File Scope Enforcement

**Rule**: An agent may ONLY modify files within `pins.allowed_paths` and MUST NOT touch files in `pins.forbidden_paths`.

**Violation**: `SCOPE_CONFLICT` event → task status set to `failed`

**Validation**: The verifier compares `submit.changed_files` against the task's pins. Any file outside scope is a breach.

**Example**:
```
pins: { allowed_paths: ["src/utils.mjs"], forbidden_paths: ["src/gateway.mjs"] }
Agent modifies src/gateway.mjs → SCOPE_CONFLICT → task fails
```

## 2. Schema Compliance

**Rule**: `submit.json` MUST pass validation against `contracts/submit/submit.schema.json`. Required fields: `schema_version`, `task_id`, `status`, `changed_files`, `tests`, `artifacts`, `exit_code`.

**Violation**: `SCHEMA_VIOLATION` event → task status set to `failed`

**Example**:
```json
// Missing "tests" field → SCHEMA_VIOLATION
{ "schema_version": "scc.submit.v1", "task_id": "abc", "status": "DONE", "exit_code": 0 }
```

## 3. Test Gate

**Rule**: When declaring `status: "DONE"`, ALL commands in `allowedTests` must have been executed and `tests.passed` must be `true`. At least one non-`task_selftest` test is required for patch-producing roles.

**Violation**: `CI_FAILED` event → task status set to `failed`

**Example**:
```
allowedTests: ["test -s docs/api.md", "grep -q 'API' docs/api.md"]
Agent skips second test → CI_FAILED
```

## 4. WIP Limits

**Rule**: The number of simultaneous `in_progress` tasks must not exceed the `wip_limit` defined in `factory_policy.json`. Per-lane WIP limits also apply.

**Violation**: New task is held in `backlog` until a slot opens. No error event, but dispatch is blocked.

**Example**:
```
factory_policy.wip_limit = 10, currently 10 in_progress
New task created → stays in backlog until one completes
```

## 5. Budget Limits

**Rule**: Each task must complete within its `timeoutMs` and not exceed `budget.max_tokens_per_task` in token consumption.

**Violation**: `BUDGET_EXCEEDED` or `TIMEOUT_EXCEEDED` event → task status set to `failed`

**Example**:
```
timeoutMs: 300000 (5 minutes)
Task runs for 6 minutes → TIMEOUT_EXCEEDED → task fails
```
