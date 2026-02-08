# Task Contract Specification

## Contract Structure

Every task in SCC represents a bilateral contract between the **Agent** (executor) and the **System** (gateway + verifier + judge).

```json
{
  "task_id": "uuid — unique task identifier",
  "goal": "string — natural language task description",
  "role": "string — assigned execution role",
  "pins": { "allowed_paths": ["..."], "forbidden_paths": ["..."] },
  "allowedTests": ["test commands that must pass"],
  "allowedModels": ["models the agent may use"],
  "allowedExecutors": ["opencodecli", "codex"],
  "timeoutMs": "number — maximum execution time",
  "max_attempts": "number — maximum retry count"
}
```

## Obligation Matrix

| Aspect | Agent Obligation | System Obligation |
|--------|-----------------|-------------------|
| **Scope** | Only modify files in `pins.allowed_paths` | Provide access to all pinned files via context pack |
| **Quality** | `tests.passed = true` before declaring DONE | Execute all `allowedTests` and report results |
| **Output** | Produce submit.json + report.md + selftest.log + patch.diff | Store artifacts and make them available for review |
| **Timing** | Complete within `timeoutMs` | Terminate and record timeout if exceeded |
| **Reporting** | Declare all changed files accurately | Verify changed_files against actual diff |
| **Budget** | Stay within token/cost budget | Track and enforce budget limits |
| **Transparency** | Emit events on failure | Route events to appropriate handlers |

## Breach Handling

| Breach | Code | Responsible Party | Consequence |
|--------|------|-------------------|-------------|
| Agent modifies out-of-scope file | `SCOPE_CONFLICT` | Agent | Task fails |
| Agent tests don't pass | `CI_FAILED` | Agent | Retry (up to max_attempts) |
| Agent exceeds timeout | `TIMEOUT_EXCEEDED` | Agent | Task fails, may escalate |
| System fails to provide pinned files | `PINS_INSUFFICIENT` | System | Agent sets NEED_INPUT |
| Agent schema violation | `SCHEMA_VIOLATION` | Agent | Task fails, retry |
| Agent uses forbidden tool | `POLICY_VIOLATION` | Agent | Task fails, escalate to human |

## Contract Lifecycle

```
Created ──→ Active ──→ Fulfilled (DONE)
                  ├──→ Breached (FAILED)
                  ├──→ Suspended (NEED_INPUT)
                  └──→ Terminated (DLQ)
```

- **Created**: Task submitted to board, contract terms set
- **Active**: Agent begins execution, obligations are enforced
- **Fulfilled**: All tests pass, output valid, verdict = DONE
- **Breached**: Agent violated a term, verdict = RETRY or ESCALATE
- **Suspended**: Agent lacks information, awaiting human input
- **Terminated**: Task abandoned after exhausting all options
