# SCC Domain Knowledge Base

This knowledge base summarizes the SCC / Prompt OS domain concepts that agents, executors, and verifiers rely on.

## 1. SCC Architecture Overview

SCC is organized as cooperating components with clear responsibilities:

- **Gateway**: The HTTP API server and core orchestrator. It accepts requests, dispatches work, and coordinates other components.
- **Board**: Task state management. It stores tasks and manages lifecycle transitions.
- **Executor**: The task execution engine (e.g., `opencodecli`, `codex`) that performs changes and produces artifacts.
- **Verifier**: Validates that outputs meet constraints and acceptance tests (pins, formatting, required artifacts).
- **Judge**: Issues the final outcome based on verifier results and policy (DONE/RETRY/ESCALATE).

## 2. Task Lifecycle

Canonical lifecycle states and transitions:

```
backlog → ready → in_progress → [done | failed | blocked]
                                     ↓
                                 [retry → in_progress]
                                     ↓
                                 [escalate → quarantine/dlq]
```

Practical notes:

- **backlog**: captured work; may be missing prerequisites.
- **ready**: all prerequisites satisfied; eligible for scheduling.
- **in_progress**: actively being executed by an agent/executor.
- **done**: accepted by verifier/judge.
- **failed**: execution failed; may be retried if fixable.
- **blocked**: cannot proceed due to missing scope, missing inputs, or external dependency.

## 3. Role System

SCC typically defines multiple roles so that permissions and expectations stay explicit.
Below is a concise description of **7 core roles** (names may vary by deployment, but the separation of concerns remains consistent).

1. **Requester**: Submits goals, constraints, and acceptance criteria.
2. **Planner**: Decomposes goals into atomic tasks and defines gates/tests.
3. **Executor**: Implements changes within scope and produces artifacts.
4. **Reviewer**: Performs human-style reasoning checks (logic, clarity, completeness).
5. **Verifier**: Runs automated checks against artifacts and constraints.
6. **Judge**: Produces final verdict (DONE/RETRY/ESCALATE) and reason codes.
7. **Operator**: Maintains platform health (circuit breakers, degradation strategies, queue management).

### Permission Matrix (Example)

| Role | Create Tasks | Modify Repo | Run Tests | Change Pins | Issue Verdict |
| --- | --- | --- | --- | --- | --- |
| Requester | Yes | No | No | No | No |
| Planner | Yes | No | No | No | No |
| Executor | No | Yes (within scope) | Yes (allowed) | No | No |
| Reviewer | No | No | No | No | No |
| Verifier | No | No | Yes | No | No |
| Judge | No | No | No | No | Yes |
| Operator | Yes | Yes (ops-only) | Yes | Yes (policy) | No |

Notes:

- "Modify Repo" is always constrained by **pins/scope** for normal execution.
- "Change Pins" is typically a controlled operation (policy/operator), not part of a normal task.

## 4. Event System

SCC uses events to connect lifecycle transitions, automation, and observability.

### Common Event Types

- **TASK_CREATED**: A new task is added to the board/backlog.
- **TASK_READY**: Task prerequisites satisfied; eligible for dispatch.
- **TASK_STARTED**: Executor begins work; transitions to `in_progress`.
- **TASK_PROGRESS**: Periodic updates (optional) during execution.
- **TASK_BLOCKED**: Execution cannot continue (missing input/scope/tooling).
- **TASK_FAILED**: Execution failed; includes reason code and evidence pointers.
- **TASK_RETRIED**: A retry attempt is scheduled or started.
- **TASK_ESCALATED**: Task moved to escalation path (quarantine/DLQ).
- **TASK_COMPLETED**: Submission produced; awaiting verification/judgment.
- **VERIFICATION_PASSED**: All required checks passed.
- **VERIFICATION_FAILED**: At least one check failed.
- **VERDICT_ISSUED**: Judge emits DONE/RETRY/ESCALATE.

### Typical Triggers

- State transitions on the **Board** emit lifecycle events.
- Gate outcomes (preflight/hygiene) emit pass/fail events.
- Circuit breaker trips emit a system-level event that affects dispatch.

