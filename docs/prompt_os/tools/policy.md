# Tool Usage Policy

> Prompt OS — Tools Layer / Policy

## Core Principles

1. **Least Privilege**: Agents receive only the tools needed for their role
2. **Whitelist Model**: All tools denied by default; must be explicitly allowed
3. **Audit Trail**: Every tool invocation is logged with timestamp, role, and arguments
4. **Fail-Safe**: Tool failures must not crash the task; emit appropriate fail code

## Permission Model

```
role.json
└── permissions
    └── tools
        ├── allow: ["git", "rg", "node"]   ← whitelist
        └── deny: ["network", "docker"]     ← explicit deny (overrides allow)
```

### Resolution Order
1. `deny` list checked first — any match → BLOCKED
2. `allow` list checked second — any match → PERMITTED
3. No match → BLOCKED (default deny)

## Usage Rules

### Rule 1: No Side Effects Beyond Scope
- Tools must only modify files listed in `task.files[]`
- Read access follows `permissions.read.allow_paths`
- Write access follows `permissions.write.allow_paths`

### Rule 2: Network Isolation
- Network tools (`curl`, `fetch`, `wget`) are denied by default
- Only connector roles may access network with explicit `"network"` in allow
- All network calls must target pre-approved endpoints

### Rule 3: No Persistent State Mutation
- Tools must not modify global config files (`.gitconfig`, `.npmrc`)
- Environment variables set during execution are scoped to the task
- Temporary files must be cleaned up on task completion

### Rule 4: Timeout Enforcement
- All tool invocations have a maximum timeout (default: 120s)
- Long-running tools (test suites) may have extended timeout (max: 600s)
- Timeout exceeded → `BUDGET_EXCEEDED` event emitted

### Rule 5: Output Capture
- All tool stdout/stderr must be captured for evidence
- Output exceeding 100KB is truncated with a marker
- Binary output is base64-encoded if needed for evidence

## Violation Handling

| Violation | Severity | Action |
|-----------|----------|--------|
| Using denied tool | HIGH | Task fails, `POLICY_VIOLATION` emitted |
| Writing outside scope | HIGH | Task fails, `SCOPE_CONFLICT` emitted |
| Network access without permission | CRITICAL | Task fails, escalate to human |
| Timeout exceeded | MEDIUM | Task retried once, then escalated |
| Tool not found | LOW | Task fails, `EXECUTOR_ERROR` emitted |
