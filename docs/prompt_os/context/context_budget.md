# Context Budget Management

This document defines how PromptOS manages and trims context to stay within a token budget while preserving correctness.

## 1) Token Budget

### `max_context_tokens`

- `max_context_tokens`: the maximum tokens permitted for the input context of a single model call.
- The composed context (goal + pinned file excerpts + summaries + history + system scaffolding) must stay under this limit.

### `context_priority`

When the budget is insufficient, trim context using this priority order (highest priority first):

1. **Task goal** (must not be trimmed)
2. **Pins content** (trim by relevance; keep the most relevant pinned content)
3. **Map / context summary** (can be shortened into higher-level summaries)
4. **History** (may be fully omitted)

Notes:

- “Pins content” means the *content imported due to pins*, not the pins declaration itself.
- Prefer progressive trimming (shorten) before dropping whole blocks.

## 2) Budget Allocation Strategy

Default allocation heuristic (tunable per system):

- Goal: **~15%**
- Pinned files: **~50%**
- Map/context: **~25%**
- Reserved for output: **~10%**

Reserving output budget avoids forced truncation of the model’s response.

### Example Configuration

```json
{
  "max_context_tokens": 120000,
  "allocation": {
    "goal_pct": 0.15,
    "pinned_files_pct": 0.50,
    "map_pct": 0.25,
    "reserved_for_output_pct": 0.10
  },
  "context_priority": [
    "goal",
    "pinned_files_by_relevance",
    "map_summary",
    "history"
  ]
}
```

## 3) Overflow Handling

When the composed context would exceed `max_context_tokens`:

- Trim according to `context_priority`.
- Keep a durable record of trimming actions in `context_trim_log`.

### `context_trim_log`

`context_trim_log` is a structured record capturing what was trimmed, why, and by how much.

```json
{
  "max_context_tokens": 120000,
  "estimated_tokens_before": 142300,
  "estimated_tokens_after": 118900,
  "actions": [
    {
      "kind": "pinned_trim",
      "target": "docs/architecture.md",
      "reason": "low relevance to current goal",
      "tokens_removed_est": 9000
    },
    {
      "kind": "history_drop",
      "target": "conversation_history",
      "reason": "lowest priority",
      "tokens_removed_est": 14400
    }
  ]
}
```
