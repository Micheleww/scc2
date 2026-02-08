# Conflict Resolution Priority Order

When multiple norms, policies, or contracts conflict, resolve using this strict priority order.

## Priority Stack (Highest → Lowest)

| Priority | Layer | Violation Consequence | Example |
|----------|-------|----------------------|---------|
| 1 | **Constitution** | Immediate task failure + event | Safety invariant breach |
| 2 | **Hard Policies** | Task failure + `POLICY_VIOLATION` | Scope violation, schema failure |
| 3 | **Role Policy** | Task failure + `ROLE_POLICY_VIOLATION` | Using forbidden tool |
| 4 | **Task Contract** | Retry or escalation | Failing allowedTests |
| 5 | **Soft Policies** | Warning logged, no failure | Style guideline deviation |
| 6 | **Best Practices** | Informational note only | Suboptimal decomposition |

## Resolution Rules

### Level 1: Constitution
- **What counts**: Articles 1-5 of the Constitution (safety, correctness, scope, transparency, amendments)
- **Conflict judgment**: If ANY lower-level norm contradicts the Constitution, the Constitution wins absolutely
- **Violation handling**: `ERROR` — immediate task failure, emit `CONSTITUTION_VIOLATION` event
- **Example**: A task contract says "delete all .tmp files" but the files are outside pins → Constitution Article 3 (Scope Discipline) overrides

### Level 2: Hard Policies
- **What counts**: Rules in `factory_policy.json` marked as hard constraints, plus `docs/prompt_os/norms/policies/hard.md`
- **Conflict judgment**: Hard policies cannot be overridden by role policies or task contracts
- **Violation handling**: `ERROR` — task failure with specific error code (e.g., `SCOPE_CONFLICT`, `CI_FAILED`)
- **Example**: WIP limit is 10, task tries to start #11 → Hard policy blocks it even if the task contract says "urgent"

### Level 3: Role Policy
- **What counts**: The `roles/*.json` file for the assigned role — paths, tools, capabilities
- **Conflict judgment**: Role policy restricts what the agent CAN do. A task contract cannot grant permissions beyond the role.
- **Violation handling**: `ERROR` — task failure with `ROLE_POLICY_VIOLATION`
- **Example**: Task says "use network to fetch data" but role `tools.deny` includes "network" → Role policy wins

### Level 4: Task Contract
- **What counts**: The task-level constraints: `pins`, `allowedTests`, `allowedModels`, `assumptions`, `timeoutMs`
- **Conflict judgment**: Task contracts can further restrict (but never expand) what the role allows
- **Violation handling**: `RETRY` or `ESCALATE` depending on the specific breach
- **Example**: Role allows writing to `docs/**` but task pins only allow `docs/api/` → Task contract is more restrictive, agent must respect it

### Level 5: Soft Policies
- **What counts**: Guidelines in `docs/prompt_os/norms/policies/soft.md` — style, documentation, commit messages
- **Conflict judgment**: Soft policies yield to any higher-level norm. They are recommendations, not mandates.
- **Violation handling**: `WARNING` — logged in report.md but task continues
- **Example**: Soft policy says "use conventional commits" but task goal says "use a specific message format" → Task contract (Level 4) wins

### Level 6: Best Practices
- **What counts**: Recommendations in `docs/prompt_os/knowledge/best_practices.md`
- **Conflict judgment**: Best practices are informational. They never override any formal norm.
- **Violation handling**: `IGNORE` — optional mention in report.md
- **Example**: Best practice says "atomic task < 500 lines" but the task legitimately needs 600 → Proceed with a note

## Quick Decision Flowchart

```
Does it violate the Constitution?
  → YES: STOP. Task fails immediately.
  → NO: ↓

Does it violate a Hard Policy?
  → YES: STOP. Task fails with error code.
  → NO: ↓

Does it violate Role Policy?
  → YES: STOP. Task fails with ROLE_POLICY_VIOLATION.
  → NO: ↓

Does it violate Task Contract (pins, tests, timeout)?
  → YES: RETRY or ESCALATE.
  → NO: ↓

Does it violate a Soft Policy?
  → YES: Log WARNING. Continue.
  → NO: ↓

Does it violate a Best Practice?
  → YES: Note in report. Continue.
  → NO: Proceed normally.
```
