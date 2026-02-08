# Task Contract Specification (PromptOS / SCC)

This document defines the normative "Task Contract" between an executing agent (the "Agent") and the SCC system runtime (the "System"). The goal is to make task execution predictable: the Agent commits to complete the task within an explicitly bounded scope and quality bar; the System commits to provide the necessary context, tools, and enforcement. When either side cannot meet its obligations, the contract provides a small set of breach codes and a clear escalation path.

The Task Contract is intended to be machine-readable enough to validate in CI, but also human-readable enough to guide day-to-day operations. It applies to batch and interactive lanes, to any model, and to any executor, as long as the task is described using the Task Contract fields below.

## Contract Structure

A Task Contract is a structured record:

```text
Task Contract = {
  task_id:           unique identifier
  goal:              task goal (natural language)
  role:              execution role
  pins:              allowed file paths (scope boundary)
  allowed_tests:     tests/commands that must pass
  allowed_models:    list of models that may be used
  allowed_executors: list of executors that may run the task
  timeout:           time limit
  max_attempts:      maximum retry count
}
```

### Field Semantics (Normative)

| Field | Meaning | Validation expectation |
|---|---|---|
| `task_id` | Global unique identifier for audit and traceability. | Must be present and stable across retries. |
| `goal` | The intended outcome, written in natural language. | Must be specific enough to determine completion. |
| `role` | The privilege/behavioral profile used to execute (e.g., executor, reviewer). | Must match an allowed role for the lane. |
| `pins` | The scope boundary: which paths the Agent may read/write. | Enforced by policy; violations are breaches. |
| `allowed_tests` | Commands that define the quality gate. | Must be executed by the System and recorded. |
| `allowed_models` | Permitted model identifiers. | The System must enforce; the Agent must comply. |
| `allowed_executors` | Permitted execution environments/runners. | Prevents accidental drift across toolchains. |
| `timeout` | Maximum wall-clock budget for the contract in Active state. | Enforced by System termination. |
| `max_attempts` | Bound on retries before escalation or abort. | Enforced by System orchestration. |

## Obligation Matrix

The contract is balanced: both parties have obligations. The Agent is responsible for disciplined changes and truthful reporting; the System is responsible for providing the advertised context and enforcing the gate consistently.

| Aspect | Agent Obligations | System Obligations |
|---|---|---|
| Scope | Only modify files within `pins` allowed paths. Do not read or depend on out-of-scope files. | Provide access to the paths declared in `pins` and deny out-of-scope access consistently. |
| Quality | Ensure `tests.passed = true` for the declared `allowed_tests`. Avoid knowingly submitting failing work. | Execute all `allowed_tests` deterministically and store logs/results as artifacts. |
| Reporting | Produce `submit.json` and `report.md` that accurately reflect changes, tests, and outcomes. | Store artifacts and make them retrievable by `task_id`. |
| Timeout | Complete within `timeout`, or explicitly trigger escalation early when blocked. | Terminate execution after `timeout` and mark as breached if incomplete. |

### Reporting Requirements (Recommended Minimum)

Even when a task is simple, reporting should cover:

| Item | Purpose |
|---|---|
| What changed | Human review and audit. |
| Why it changed | Rationale; helps prevent regressions. |
| What was validated | Links to tests/logs; enables trust. |
| What remains unknown | Explicit risk statement; enables escalation decisions. |

## Breach Handling

A "breach" is a contract failure that prevents the task from being considered Fulfilled. Breaches are classified to speed triage and to drive the escalation chain.

### Standard Breach Codes

| Breach code | When it applies | Typical remediation |
|---|---|---|
| `SCOPE_CONFLICT` | Agent reads/writes outside the pinned scope, or introduces dependencies outside the contract. | Reduce change footprint; request updated pins if needed. |
| `CI_FAILED` | Declared tests fail at the quality gate. | Fix defects, add missing files, adjust approach; retry within `max_attempts`. |
| `TIMEOUT_EXCEEDED` | Work not completed before `timeout` expires. | Simplify, split task, or escalate role/model for speed. |
| `PINS_INSUFFICIENT` | System did not provide required pinned context or access that the contract claims is available. | Escalate to update pins/context; do not guess. |

### Breach Principles

1. Breach classification must be deterministic: the same failure should yield the same code.
2. Breaches should be attributable: whether the Agent or System failed is part of the classification.
3. Breaches are not "blame"; they are routing signals to resolve issues quickly.

## Contract Lifecycle

The Task Contract progresses through a small state machine. The System is the source of truth for state transitions, but the Agent should behave consistently with the expected transitions.

### States

| State | Description |
|---|---|
| `Created` | Contract exists; resources may not yet be allocated. |
| `Active` | Execution is underway; Agent can read context and write within scope. |
| `Fulfilled` | Goal achieved and quality gates passed; final artifacts emitted. |
| `Breached` | Contract failed due to a breach code; escalation or abort may follow. |

### Transitions (Normative)

| From → To | Condition |
|---|---|
| `Created` → `Active` | System allocates executor/model and grants pinned access. |
| `Active` → `Fulfilled` | Agent outputs required deliverables; System executes `allowed_tests`; all gates pass; reporting complete. |
| `Active` → `Breached` | Any breach occurs: scope violation, failing tests, missing pins, or timeout. |
| `Breached` → `Active` | Allowed when remediation is possible and attempts remain (e.g., retry). |
| `Breached` → terminal abort | When escalation reaches an abort decision (e.g., budget exceeded or max attempts). |

### Lifecycle Diagram (ASCII)

```text
   +---------+      allocate + pins ok      +--------+
   | Created | ----------------------------> | Active |
   +---------+                               +--------+
        |                                         |
        | (canceled / invalid)                    | (tests pass, deliverables complete)
        v                                         v
    +--------+     retry allowed (attempts left) +-----------+
    | Breach | <------------------------------- | Fulfilled |
    | (code) | -------------------------------->+-----------+
    +--------+   (escalate / abort decision)
```

## Conformance Notes

An implementation conforms to this spec when:

1. Scope enforcement is real (not advisory): `pins` is enforced by the System, and the Agent respects it.
2. Quality is measurable: `allowed_tests` are explicit and executed at the gate.
3. Reporting is complete: artifacts include a machine-readable `submit.json` and a human-readable `report.md`.
4. Breach codes are used consistently so escalation routing remains reliable across teams and time.

