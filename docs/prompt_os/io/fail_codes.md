# PromptOS IO Layer — Failure Codes

This catalog defines standardized `reason_code` values used by `submit.json` and by the gateway verdict.

Conventions:

- Codes are `SCREAMING_SNAKE_CASE`.
- A code MUST be actionable: the handler should know what to do next.
- When multiple issues exist, prefer the *first blocking* root cause.

| Code | Meaning | Trigger | Action |
|------|---------|---------|--------|
| SCOPE_CONFLICT | Modified disallowed files | `changed_files` or `new_files` include paths outside `pins.allowed_paths` or inside `pins.forbidden_paths` | Restrict edits to allowed scope; re-run with corrected pins |
| CI_FAILED | Tests failed | `tests.passed=false` or gateway test execution returns non-zero | Fix failures; attach logs; retry |
| SCHEMA_VIOLATION | Output schema invalid | `submit.json` missing required fields / wrong types / unknown enum | Regenerate `submit.json` to match schema; retry |
| PINS_INSUFFICIENT | Context pins insufficient | Required inputs are not pinned / cannot be read under allowlist | Request additional pins or move required info into pinned scope |
| POLICY_VIOLATION | Role policy violated | Forbidden tools/actions used; disallowed network access; prohibited behavior | Stop; escalate to policy owner; retry with compliant approach |
| BUDGET_EXCEEDED | Budget exceeded | Token/time/compute budget exceeded | Reduce scope; split task; retry |
| TIMEOUT_EXCEEDED | Execution timeout | Execution exceeds configured timeout | Split task; optimize steps; retry |
| EXECUTOR_ERROR | Executor internal failure | Runtime error, model API error, tool crash | Retry; include stack trace hash or reproduction steps |
| PREFLIGHT_FAILED | Preflight validation failed | Role/pins/task metadata validation fails before execution | Fix config and rerun preflight |
| FILE_NOT_FOUND | Required file missing | A pinned file referenced by `files` does not exist | Add/restore the file or correct the path |
| PERMISSION_DENIED | Permission blocked | OS/filesystem permissions prevent read/write within allowed scope | Adjust permissions; change location; retry |
| MERGE_CONFLICT | Patch cannot apply cleanly | Patch application fails due to divergent base | Rebase/update; regenerate patch; retry |
| DEPENDENCY_MISSING | Required dependency absent | A command/tool expected by the task is not installed | Install dependency (with approval) or use a built-in alternative |
| FORMAT_VIOLATION | Output formatting requirements not met | Docs not in English, table missing, minimum counts not met | Fix formatting; rerun validations |
| EVIDENCE_MISSING | Evidence incomplete | Required artifacts absent (e.g., `patch.diff`, `report.md`, `selftest.log`) | Recreate missing evidence; ensure paths are correct |
| EVIDENCE_INVALID | Evidence fails validation | Logs truncated, diff not parseable, mismatched file lists | Regenerate evidence; ensure consistency across artifacts |
| NEEDS_CLARIFICATION | Task ambiguity | Goal unclear or contradictory requirements | Ask targeted questions; proceed after clarification |
| UPSTREAM_CHANGED | Upstream moved | Docs/APIs changed during execution affecting assumptions | Refresh context; re-validate; retry |

Notes:

- `SCOPE_CONFLICT`, `SCHEMA_VIOLATION`, and `EVIDENCE_MISSING` are typically *non-retryable until corrected*.
- `CI_FAILED` is retryable after fixing the failing causes.

