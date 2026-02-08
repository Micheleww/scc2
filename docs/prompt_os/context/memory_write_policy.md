# Memory Write Policy

This document defines how PromptOS records and persists knowledge learned during execution.

## 1) Short-term Memory

**Short-term memory** is the in-task working state used to complete the current task.

- Scope: within a single task execution.
- Contents: intermediate notes, scratchpads, partial summaries, temporary decisions.
- Lifecycle: must be cleared when the task ends.
- Persistence: not written to long-lived documentation locations by default.

Typical short-term memory items:

- temporary parsing results
- unresolved hypotheses
- candidate patch plans

## 2) Long-term Memory

**Long-term memory** is durable knowledge intended for reuse across tasks.

- Scope: cross-task.
- Storage locations: typically `docs/` and/or `map/` (project-defined knowledge bases).
- Quality bar: coherent, source-backed, and conflict-aware.

### Write Permissions

- Only a designated curator role (e.g., `ssot_curator`) may write long-term memory.
- Other roles may propose changes, but must not persist them directly.

### Example: Proposed Memory Record

```json
{
  "kind": "long_term",
  "topic": "pins_glob_resolution",
  "summary": "Forbidden patterns take precedence over allowed patterns; an empty allowed_paths denies all.",
  "source": {
    "task_id": "...",
    "timestamp": "2026-02-08T00:00:00Z"
  },
  "target_path": "docs/prompt_os/context/pins_spec.md"
}
```

## 3) Memory Conflict Resolution

When new memory conflicts with existing memory, resolve conflicts explicitly rather than silently overwriting.

### Conflict Detection

Conflicts include:

- contradictory definitions (same term, different meaning)
- incompatible defaults (same field, different default)
- overlapping authoritative sources (two “SSOT” statements disagree)

### Resolution Rules

1. **Prefer the current SSOT**: if the project designates a single source of truth, that source wins.
2. **Require provenance**: every long-term memory change must cite where it came from.
3. **Deprecate rather than delete** when uncertainty exists:
   - mark old statements as deprecated,
   - add new statements with an effective date and rationale.
4. **Escalate unresolved conflicts** to the curator role for review.

### Example: Deprecation Record

```json
{
  "status": "deprecated",
  "deprecated_at": "2026-02-08",
  "replaced_by": "pins_spec.md (Pins Resolution section)",
  "reason": "Newer definition adopted after review"
}
```
