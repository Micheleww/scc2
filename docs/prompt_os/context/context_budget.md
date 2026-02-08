# Context Budget Management

## Token Budget Allocation

| Component | Target % | Priority (trim order) | Notes |
|-----------|----------|----------------------|-------|
| Task goal | ~15% | Never trimmed | Core instruction, always included |
| Pinned files | ~50% | Trim by relevance | Largest component, trim distant files first |
| Map summary | ~25% | Trim to summary | Can reduce from L2→L1→L0 |
| Output reserve | ~10% | N/A | Reserved for model response |

## Budget Limits by Role

| Role | Max Context (bytes) | Rationale |
|------|-------------------|-----------|
| doc | 50,000 | Only needs goal + reference snippets |
| split / planner | 80,000 | Map summary + task list |
| designer | 80,000 | Architecture-level, not line-level |
| reviewer | 100,000 | Patch diff + surrounding code |
| ssot_curator | 100,000 | Cross-reference checking |
| engineer | 200,000 | Needs broad code context |
| DEFAULT | 220,000 | Fallback for unknown roles |

## Overflow Handling

When assembled context exceeds the budget:
1. Trim `map_summary` from L2 → L1 → L0
2. Remove least-relevant pinned files (furthest from `files[]` targets)
3. Truncate remaining pinned files to line_windows if available
4. Log trimming actions to `context_trim_log` for Token CFO analysis

## Context Pack Assembly

```
1. Resolve pins → file list
2. Read files (respecting line_windows)
3. Add headers: "## {filename} (lines {start}-{end})"
4. Check total bytes against role budget
5. Trim if over budget (following priority order)
6. Store as contextpacks/{id}.md
7. Inject into prompt as <context_pack>
```
