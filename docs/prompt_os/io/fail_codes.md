# Fail Codes Directory

| Code | Severity | Meaning | Trigger | Recommended Action |
|------|----------|---------|---------|-------------------|
| `SCOPE_CONFLICT` | CRITICAL | Modified files outside allowed scope | `changed_files` not in `pins.allowed_paths` | Remove out-of-scope changes, re-submit |
| `CI_FAILED` | HIGH | Tests did not pass | `tests.passed = false` | Read selftest.log, fix issue, re-run |
| `SCHEMA_VIOLATION` | HIGH | submit.json format invalid | Failed JSON schema validation | Fix required fields and types |
| `PINS_INSUFFICIENT` | HIGH | Needed files not in pins | Agent cannot access required context | Set NEED_INPUT, request additional pins |
| `POLICY_VIOLATION` | CRITICAL | Used forbidden tool or path | Tool in `tools.deny` or path in `deny_paths` | Escalate to human (Level 3) |
| `BUDGET_EXCEEDED` | HIGH | Token or cost limit exceeded | Usage > `max_tokens_per_task` | Abort or split into smaller tasks |
| `TIMEOUT_EXCEEDED` | HIGH | Execution timed out | Runtime > `timeoutMs` | Reduce scope or increase timeout |
| `EXECUTOR_ERROR` | MEDIUM | Model API or runtime failure | Network error, model unavailable, crash | Auto-retry 3x with exponential backoff |
| `PREFLIGHT_FAILED` | HIGH | Pre-execution validation failed | Pins/role/test configuration invalid | Fix task configuration |
| `ci_skipped` | MEDIUM | No test commands provided | Empty `allowedTests` | Add at least one test command |
| `tests_only_task_selftest` | MEDIUM | Only selftest, no real tests | Patch-producing role without real tests | Add non-selftest test commands |
| `MAX_ATTEMPTS_EXCEEDED` | HIGH | All retry attempts exhausted | `attempts >= max_attempts` | Escalate (model upgrade or human) |
| `SPLIT_REQUIRED` | MEDIUM | Task too large for single execution | Complexity exceeds single-task capacity | Decompose via splitter role |
| `NEED_INPUT_REQUIRED` | MEDIUM | Cannot proceed without information | Missing context, ambiguous goal | Set NEED_INPUT with description |
| `MODEL_UNAVAILABLE` | MEDIUM | Requested model not accessible | API error, rate limit, model deprecated | Fall back to next tier model |
| `CONSTITUTION_VIOLATION` | CRITICAL | Violated constitutional safety rule | Any Article 1-4 breach | Immediate abort, no retry |
| `ROLE_POLICY_VIOLATION` | HIGH | Action outside role capabilities | Attempted write to denied path | Reassign to appropriate role |
| `ARTIFACT_MISSING` | MEDIUM | Required output artifact not produced | Missing report.md, selftest.log, etc. | Produce missing artifacts, re-submit |
| `DUPLICATE_DISPATCH` | LOW | Task already has an active job | Idempotency check failed | No action needed, skip |
| `MAX_CHILDREN_EXCEEDED` | MEDIUM | Parent task has too many children | Children count > `budgets.max_children` | Consolidate or restructure task tree |
