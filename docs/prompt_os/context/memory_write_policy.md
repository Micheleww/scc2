# Memory Write Policy

## Short-term Memory
- **Scope**: Within a single task execution
- **Storage**: Thread history (last 3-6 decisions)
- **Lifetime**: Cleared when task reaches terminal state (done/failed/dlq)
- **Access**: Only the current task's agent can read/write
- **Format**: Injected as `<thread>` block in prompt

## Long-term Memory
- **Scope**: Cross-task, persistent knowledge
- **Storage**: Written to `docs/` or `map/` directories
- **Lifetime**: Persists until explicitly updated or deleted
- **Access**: Only `ssot_curator` role may write long-term memory
- **Governance**: Changes must go through standard task lifecycle with tests and review

## Memory Conflict Resolution
1. Newer memory overwrites older if from same source (ssot_curator)
2. If two agents produce conflicting memory simultaneously, the one with higher-priority task wins
3. Conflicts are logged as `MEMORY_CONFLICT` events for human review
4. The ssot_curator role is the arbiter for all long-term memory disputes
