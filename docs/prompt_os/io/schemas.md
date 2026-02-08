# IO Schemas

## Task Input Schema

```json
{
  "task_id": "string (uuid)",
  "goal": "string (natural language task description)",
  "role": "string (planner|splitter|engineer|reviewer|doc|ssot_curator|designer)",
  "pins": {
    "allowed_paths": ["string[] — glob patterns for accessible files"],
    "forbidden_paths": ["string[] — glob patterns for blocked files"]
  },
  "files": ["string[] — repo-relative target file paths"],
  "allowedTests": ["string[] — test commands to verify output"],
  "allowedModels": ["string[] — permitted model IDs"],
  "allowedExecutors": ["string[] — opencodecli|codex"],
  "context": {
    "context_pack": "string (markdown — assembled pinned file contents)",
    "thread_history": ["string[] — recent decisions from prior attempts"],
    "map_summary": "object (code structure index)"
  },
  "timeoutMs": "number (max execution time in ms)",
  "assumptions": ["string[] — constraints and context notes"]
}
```

## Task Output Schema (submit.json)

Schema: `contracts/submit/submit.schema.json`, version `scc.submit.v1`

```json
{
  "schema_version": "scc.submit.v1",
  "task_id": "string (must match input task_id)",
  "status": "DONE | NEED_INPUT | FAILED",
  "reason_code": "string (ok | ci_failed | scope_conflict | ...)",
  "changed_files": ["string[] — all files modified"],
  "new_files": ["string[] — all files created"],
  "tests": {
    "commands": ["string[] — test commands executed"],
    "passed": "boolean",
    "summary": "string (human-readable test summary)"
  },
  "artifacts": {
    "report_md": "string (path to report.md)",
    "selftest_log": "string (path to selftest.log)",
    "evidence_dir": "string (path to evidence/)",
    "patch_diff": "string (path to patch.diff)",
    "submit_json": "string (path to submit.json)"
  },
  "exit_code": "integer (0 = success)",
  "needs_input": ["string[] (required if status=NEED_INPUT, describes what's missing)"]
}
```

## Verdict Schema

The system produces a verdict after validating submit.json:

```json
{
  "task_id": "string",
  "verdict": "DONE | RETRY | ESCALATE | REJECT",
  "reason": "string (explanation)",
  "checks": {
    "schema_valid": "boolean",
    "scope_clean": "boolean",
    "tests_passed": "boolean",
    "artifacts_complete": "boolean",
    "changed_files_match": "boolean"
  },
  "next_action": "none | retry | model_upgrade | role_escalation | human | dlq"
}
```

| Verdict | Meaning | Trigger |
|---------|---------|---------|
| DONE | Task completed successfully | All checks pass |
| RETRY | Task needs another attempt | tests_passed=false, attempts remaining |
| ESCALATE | Task needs upgrade | Repeated failures, capability gap |
| REJECT | Task output violates policy | scope_clean=false or schema_valid=false |
