# Escalation Policy (PromptOS / SCC)

This document defines the escalation chain used when a task cannot be completed under its current Task Contract. Escalation is not a failure by itself; it is a controlled mechanism to preserve correctness, minimize wasted retries, and ensure that constraints such as scope pins, budgets, and policy requirements are respected.

The policy is designed to work with the breach codes defined in the Task Contract specification. It also defines consistent terminal outcomes such as `NEED_INPUT` (human intervention required) and `DLQ` (task aborted and moved to a dead-letter queue).

## Escalation Levels

Escalation proceeds through ordered levels. A System may skip levels when a trigger mandates it (see Triggers section).

| Level | Name | Description | Typical Output |
|---|---|---|---|
| Level 0 | Self-retry | Retry with the same model and role, within `max_attempts`. | Continue as `Active` |
| Level 1 | Model upgrade | Switch to a stronger model to improve reasoning, tool use, or speed. | Continue as `Active` |
| Level 2 | Role escalation | Switch to a higher-privilege role (or broader tool access) while still respecting policy. | Continue as `Active` |
| Level 3 | Human intervention | Explicitly request human input; task cannot proceed safely without it. | `NEED_INPUT` |
| Level 4 | Task abort | Stop attempting; mark task as aborted and route to DLQ for later triage. | `DLQ` |

### Level Definitions (Normative)

1. **Level 0: Self-retry**
   - Allowed only while `attempt < max_attempts`.
   - Requires a concrete change in approach (not repeating the same steps).
   - Must record the error signature that triggered the retry.

2. **Level 1: Model upgrade**
   - Permitted only if the target model is in `allowed_models`.
   - Recommended when failures are due to reasoning depth, long-context synthesis, or complex edits.
   - Should not be used to bypass policy; scope and compliance remain unchanged.

3. **Level 2: Role escalation**
   - Permitted only if the target role is in `allowed_executors` and policy allows it.
   - Recommended when the task is blocked by insufficient permissions, missing tools, or required cross-cutting changes.
   - Requires explicit acknowledgment of the expanded capability boundary.

4. **Level 3: Human intervention**
   - Used when proceeding would require guessing, when policies require consent, or when critical context is missing.
   - Output must be `NEED_INPUT` with a minimal set of concrete questions.
   - The Agent should include the attempted steps and the smallest needed clarification.

5. **Level 4: Task abort**
   - Used when budget is exceeded, when policy forbids continuing, or when repeated attempts indicate low probability of success.
   - Output must be routed to `DLQ` with logs sufficient for offline triage.

## Escalation Triggers

Triggers determine when to escalate, and whether to skip intermediate levels. Trigger evaluation should be deterministic and based on recorded evidence (error codes, logs, counters, and policy signals).

### Common Triggers (Table)

| Trigger | Signal | Default action |
|---|---|---|
| Repeated error | Same error signature occurs N times consecutively. | Escalate one level (0→1, 1→2, etc.). |
| `PINS_INSUFFICIENT` | Required context is unavailable under current pins. | Escalate to Level 3 to request pins/context updates. |
| `SCOPE_CONFLICT` | The task requires changes outside pinned scope. | Escalate to Level 3 to request expanded scope or task split. |
| `CI_FAILED` | Quality gate fails for `allowed_tests`. | Level 0 self-retry if attempts remain; then Level 1 if repeated. |
| `TIMEOUT_EXCEEDED` | Execution hits the contract timeout. | Level 1 or Level 2 depending on root cause; consider task split. |
| `POLICY_VIOLATION` | Policy disallows requested action or content. | Direct Level 3 (human decision required). |
| `BUDGET_EXCEEDED` | Budget or quota is exceeded. | Direct Level 4 (abort to DLQ). |

### Trigger Rules (Normative)

- **Consecutive-repeat rule:** After **N** consecutive occurrences of the same error signature (same breach code + same root cause), escalate one level. The System should define `N` (commonly 2 or 3) to prevent churn.
- **Immediate escalation:** Some signals bypass the normal ladder:
  - `POLICY_VIOLATION` → jump directly to **Level 3**.
  - `BUDGET_EXCEEDED` → jump directly to **Level 4**.
- **Max attempts binding:** `max_attempts` caps Level 0 retries. When the cap is reached, escalation is mandatory.

## Escalation Flow Diagram (ASCII)

The following diagram illustrates the control flow. It shows normal progression, immediate jumps, and terminal states.

```text
                 +---------------------+
                 |   Task Active       |
                 +---------------------+
                           |
                           v
                  +------------------+
                  |  Evaluate error  |
                  +------------------+
                           |
          +----------------+----------------+
          |                                 |
          v                                 v
  +-------------------+            +-------------------+
  | POLICY_VIOLATION   |            | BUDGET_EXCEEDED   |
  +-------------------+            +-------------------+
          |                                 |
          v                                 v
     +----------+                      +----------+
     | Level 3  |                      | Level 4  |
     | NEED_INPUT                      | DLQ      |
     +----------+                      +----------+
          ^
          |
          | (otherwise)
          |
          v
  +-------------------+
  | repeated N times? |
  +-------------------+
     |           |
    no          yes
     |           |
     v           v
 +---------+   +---------+   +---------+
 | Level 0 |-->| Level 1 |-->| Level 2 |
 | retry   |   | model   |   | role    |
 +---------+   +---------+   +---------+
     |
     v
  (success)
     |
     v
 +-----------+
 | Fulfilled |
 +-----------+
```

## Operational Notes

Escalation is most effective when the Agent and System communicate clearly:

1. **Use breach codes as routing keys.** If the contract is breached as `PINS_INSUFFICIENT`, do not attempt workarounds that guess missing context; escalate with concrete needs.
2. **Avoid "retry loops".** A retry must represent a meaningful change (new hypothesis, smaller diff, additional evidence, or simplified approach). Otherwise it consumes attempts without increasing success probability.
3. **Prefer minimal questions at Level 3.** Human intervention should request the smallest set of missing facts. This keeps turnaround short and reduces risk of misinterpretation.
4. **DLQ is a safety valve.** Aborting to DLQ is correct when continuing would be wasteful or non-compliant. The DLQ record should enable later triage: what failed, what was tried, and what information would unblock it.

