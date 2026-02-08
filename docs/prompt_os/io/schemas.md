# PromptOS IO Layer — Schemas

This document defines the standard **input/output data formats** used by SCC PromptOS agents and the executor.

The IO layer exists to make tasks:

- machine-validated (schema-first)
- reproducible (evidence + logs)
- auditable (explicit scope via pins)

---

## 1) Task Input Schema

### Canonical JSON shape

```json
{
  "task_id": "uuid",
  "goal": "string — natural language task description",
  "role": "string — role name",
  "pins": {
    "allowed_paths": ["string[]"],
    "forbidden_paths": ["string[]"]
  },
  "files": ["string[] — files the agent is expected to touch"],
  "context": {
    "map": "object — repository structure map",
    "docs": "object — relevant documentation references",
    "history": "object — task history"
  }
}
```

### Field semantics

- `task_id` (required): Stable UUID for correlating all artifacts.
- `goal` (required): What the agent should accomplish (human readable).
- `role` (required): Execution policy profile (e.g., "executor", "reviewer").
- `pins` (required): Scope guardrails.
  - `allowed_paths`: The only paths the agent may read/write.
  - `forbidden_paths`: Paths explicitly disallowed even if they match `allowed_paths`.
- `files` (optional): A hint list of expected file touches; used for preflight and review.
- `context` (optional): Structured helper data.
  - `map`: A precomputed repo map (when available).
  - `docs`: Links/IDs to internal docs or prior decisions.
  - `history`: Prior attempts, failures, or important constraints.

### Validation rules (recommended)

- `task_id` MUST be a UUID string.
- `pins.allowed_paths` MUST be non-empty.
- No path MAY appear in both `allowed_paths` and `forbidden_paths`.
- If `files` is present, every entry SHOULD be within `pins.allowed_paths`.

### Example

```json
{
  "task_id": "72c84e9c-0975-4c1a-b9a5-864c2725dc8a",
  "goal": "Create IO layer documentation for schemas, fail codes, and evidence.",
  "role": "executor",
  "pins": {
    "allowed_paths": ["docs/prompt_os/io/"],
    "forbidden_paths": []
  },
  "files": [
    "docs/prompt_os/io/schemas.md",
    "docs/prompt_os/io/fail_codes.md",
    "docs/prompt_os/io/evidence_spec.md"
  },
  "context": {
    "map": {},
    "docs": {},
    "history": {}
  }
}
```

---

## 2) Task Output Schema (`submit.json`)

The executor MUST emit a `submit.json` that can be validated without reading free-form text.

### Canonical JSON shape

```json
{
  "schema_version": "scc.submit.v1",
  "task_id": "string",
  "status": "DONE | NEED_INPUT | FAILED",
  "reason_code": "string (optional)",
  "changed_files": ["string[]"],
  "new_files": ["string[]"],
  "tests": {
    "commands": ["string[]"],
    "passed": "boolean",
    "summary": "string"
  },
  "artifacts": {
    "report_md": "path",
    "selftest_log": "path",
    "evidence_dir": "path",
    "patch_diff": "path",
    "submit_json": "path"
  },
  "exit_code": "integer",
  "needs_input": ["string[]"]
}
```

### Field semantics

- `schema_version` (required): Output contract identifier. MUST be `scc.submit.v1`.
- `task_id` (required): Must match the input `task_id`.
- `status` (required):
  - `DONE`: Work completed successfully.
  - `NEED_INPUT`: Blocked; requires user/system input to proceed.
  - `FAILED`: Attempt completed but unsuccessful.
- `reason_code` (optional): Machine-actionable failure reason (see `fail_codes.md`).
- `changed_files` / `new_files` (required): Paths changed/created **within the allowed scope**.
- `tests` (required): What was executed and the outcome.
  - `commands`: A list of commands (strings) intended to be runnable by the gateway.
  - `passed`: Boolean test verdict.
  - `summary`: Human readable summary.
- `artifacts` (required): Paths to evidence files produced for this task.
- `exit_code` (required): Integer exit code representing overall executor status.
- `needs_input` (required): List of concrete questions/requests when `status=NEED_INPUT`.

### Validation rules (recommended)

- `status=DONE` implies `exit_code=0`.
- If `tests.passed=false`, `status` SHOULD be `FAILED` and `reason_code` SHOULD be `CI_FAILED`.
- Every path in `changed_files` and `new_files` MUST be under `pins.allowed_paths` and not under `pins.forbidden_paths`.
- All `artifacts.*` paths MUST exist and be readable by the gateway.

---

## 3) Verdict Schema (system evaluation result)

After the gateway validates artifacts and policies, it may produce a *verdict object*.

### Canonical JSON shape

```json
{
  "schema_version": "scc.verdict.v1",
  "task_id": "string",
  "verdict": "PASS | FAIL",
  "reason_code": "string (optional)",
  "messages": ["string[]"],
  "checks": {
    "schema_valid": "boolean",
    "scope_valid": "boolean",
    "tests_passed": "boolean",
    "evidence_present": "boolean"
  },
  "timestamps": {
    "submitted_at": "RFC3339 string",
    "evaluated_at": "RFC3339 string"
  },
  "links": {
    "submit_json": "path",
    "report_md": "path",
    "selftest_log": "path",
    "patch_diff": "path",
    "evidence_dir": "path"
  }
}
```

### Notes

- `reason_code` SHOULD map to a code in `docs/prompt_os/io/fail_codes.md`.
- `checks` allows dashboards to show *what failed* without parsing free text.

