# Escalation Chain

## Escalation Levels

| Level | Name | Trigger | Action |
|-------|------|---------|--------|
| 0 | Self-Retry | Test failure, minor error | Same model retries (within max_attempts) |
| 1 | Model Upgrade | Repeated failures at current tier | Switch to stronger model (Tier 3→2→1) |
| 2 | Role Escalation | Capability limitation | Switch to higher-permission role |
| 3 | Human Intervention | Policy violation, ambiguity | status=NEED_INPUT, await human |
| 4 | Task Abort | Unresolvable, budget exceeded | Task → DLQ (Dead Letter Queue) |

## Escalation Flow

```
Task fails
    │
    ▼
[attempts < max_attempts?]──YES──→ Level 0: Self-Retry
    │ NO                                    │
    ▼                                  [passes?]──YES──→ DONE ✓
[model upgrade available?]──YES──→ Level 1: Model Upgrade
    │ NO                                    │
    ▼                                  [passes?]──YES──→ DONE ✓
[higher role available?]──YES──→ Level 2: Role Escalation
    │ NO                                    │
    ▼                                  [passes?]──YES──→ DONE ✓
[POLICY_VIOLATION?]──YES──→ Level 3: Human Intervention
    │ NO                           │
    ▼                         [resolved?]──YES──→ Re-enter at Level 0
Level 4: Task Abort ──→ DLQ      │ NO
                                  ▼
                             Level 4: Task Abort ──→ DLQ
```

## Fast-Track Rules

| Condition | Skip To |
|-----------|---------|
| `POLICY_VIOLATION` | Level 3 (human) immediately |
| `BUDGET_EXCEEDED` | Level 4 (abort) immediately |
| `CONSTITUTION_VIOLATION` | Level 4 (abort) immediately |
| `PINS_INSUFFICIENT` | Level 3 (human) — agent cannot fix missing pins |

## Level Details

### Level 0: Self-Retry
- Same model, same role, same pins
- Agent receives previous error context in thread history
- Max retries defined by `role.gates.max_attempts` (typically 2)

### Level 1: Model Upgrade
- Tier 3 (glm-4.7, kimi-k2.5) → Tier 2 (claude-sonnet, gpt-4o-mini) → Tier 1 (claude-opus, gpt-4o)
- Same task, same role, stronger model
- Only if `allowedModels` includes higher-tier options

### Level 2: Role Escalation
- Current role lacks capability (e.g., doc role needs code changes)
- Planner reassigns to appropriate role
- New role must have superset of required capabilities

### Level 3: Human Intervention
- Agent sets `status: "NEED_INPUT"` with `needs_input[]` describing what's needed
- Task enters `blocked` state on the board
- Human reviews and either provides input or aborts

### Level 4: Task Abort
- Task moved to DLQ (Dead Letter Queue)
- All artifacts preserved for post-mortem
- `TASK_ABORTED` event emitted
