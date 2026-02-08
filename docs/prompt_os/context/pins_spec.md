# Pins Specification

## 1) What are Pins?

**Pins** are a task-scoped file access control declaration.

- Pins declare which repo paths an agent is allowed to read/write during task execution.
- Each task carries two lists:
  - `allowed_paths`: paths/globs that are allowed.
  - `forbidden_paths`: paths/globs that are explicitly denied.
- Pins are assigned by an upstream planner/splitter when the task is created.

Pins are evaluated as an *execution-time guardrail* for tools that touch the filesystem.

## 2) Pins Structure

Pins are represented as a JSON object:

```json
{
  "allowed_paths": ["src/gateway.mjs", "src/utils/*.mjs", "docs/**"],
  "forbidden_paths": ["**/secrets/**", "node_modules/**"]
}
```

### Field Semantics

- `allowed_paths`: a list of path patterns that grant access.
- `forbidden_paths`: a list of path patterns that deny access.
- If `allowed_paths` is empty, **no files are accessible**, regardless of `forbidden_paths`.

## 3) Pins Resolution (Resolution Rules)

### Glob Syntax

- `*` matches within a single directory segment.
  - Example: `src/*.ts` matches `src/a.ts` but not `src/x/a.ts`.
- `**` matches across multiple directory segments.
  - Example: `docs/**` matches `docs/a.md` and `docs/x/a.md`.

### Evaluation Order

Pins resolution for a candidate path `P` is:

1. If `allowed_paths` is empty: **deny**.
2. If `P` matches any entry in `forbidden_paths`: **deny**.
3. If `P` matches any entry in `allowed_paths`: **allow**.
4. Otherwise: **deny**.

In other words, **forbidden has higher priority than allowed**.

### Matching Notes

- Patterns are interpreted relative to the repository root.
- Access checks should be performed on *normalized paths* (e.g., resolving `.` and `..`).
- Implementations should avoid allowing directory traversal that escapes the repo root.

## 4) Pins Inheritance (Inheritance Rules)

Pins are inherited down the task tree.

- A child task’s pins must be a subset of the parent task’s pins:
  - `child.allowed_paths` must not grant access outside the parent’s allowed set.
  - `child.forbidden_paths` may be the same as the parent’s or stricter.
- A child task **cannot** widen access compared to its parent.

This ensures the planner can safely split work without increasing privileges.

## 5) Pins Validation (Validation Rules)

Pins should be validated during a **preflight** phase before execution.

### Compatibility Checks

- Validate pins syntax:
  - JSON must parse.
  - `allowed_paths` and `forbidden_paths` must be arrays of strings.
- Validate role compatibility:
  - If a role has `pins_required = true`, then `allowed_paths` must be **non-empty**.
- Validate inheritance:
  - For child tasks, check that the pins are within the parent’s authorization.

### Example Preflight Result

```json
{
  "pins_valid": true,
  "pins_required": true,
  "allowed_paths_count": 3,
  "forbidden_paths_count": 2,
  "notes": ["forbidden precedence confirmed", "inheritance constraints satisfied"]
}
```
