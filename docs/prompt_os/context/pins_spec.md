# Pins Specification

## What Are Pins

Pins are **task-level file access control declarations**. Every task has a pins object that defines which files the agent can read and write. Pins are the primary mechanism for enforcing the principle of least privilege.

## Structure

```json
{
  "allowed_paths": ["src/gateway.mjs", "docs/**", "tests/unit/*.test.js"],
  "forbidden_paths": ["**/secrets/**", "node_modules/**", ".env"]
}
```

## Resolution Rules

1. **Glob syntax**: `**` matches any number of directories, `*` matches within a single directory
2. **Forbidden overrides allowed**: If a path matches both lists, it is FORBIDDEN
3. **Empty allowed = no access**: An empty `allowed_paths` array means the agent cannot access any files
4. **Explicit is better**: Prefer exact file paths over broad globs for token efficiency

## Inheritance

- Child task pins MUST be a subset of parent task pins: `child.pins ⊆ parent.pins`
- A child cannot access files that its parent cannot access
- The gateway validates this constraint at task creation time

## Validation

- If `role.permissions.read.pins_required = true`, the task MUST have non-empty `allowed_paths`
- Preflight gate checks pins against role read/write policies
- The effective scope is the intersection: `pins.allowed_paths ∩ role.permissions.write.allow_paths`

## Optimal Usage

```
❌ BAD:  { "allowed_paths": ["src/**"] }           → 200KB+ context, wastes tokens
✅ GOOD: { "allowed_paths": ["src/gateway.mjs"] }  → single file, precise
✅ BEST: Use line_windows to pin specific line ranges → 5-10KB context
```
