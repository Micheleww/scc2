# Evidence Specification

## Evidence Types

| Type | Format | Purpose | Required |
|------|--------|---------|----------|
| `report.md` | Markdown | Explain what was done and why | Yes |
| `selftest.log` | Plain text | Full test execution output | Yes |
| `patch.diff` | Unified diff | All file changes | Yes |
| `submit.json` | JSON | Structured task completion data | Yes |
| `evidence/` | Directory | Additional supporting evidence | Optional |

## Directory Structure

```
artifacts/<task_id>/
├── report.md          — Human-readable execution report
├── selftest.log       — Test command output (stdout + stderr)
├── patch.diff         — git diff of all changes
├── submit.json        — Structured submission (scc.submit.v1)
└── evidence/          — Optional additional evidence
    ├── pre_state.json — System state before execution
    ├── post_state.json— System state after execution
    └── screenshots/   — Visual evidence (if applicable)
```

## Validation Rules

| Artifact | Validation |
|----------|-----------|
| report.md | Must exist, size > 0 bytes, must contain description of actions taken |
| selftest.log | Must exist, must contain output of all `allowedTests` commands |
| patch.diff | Must exist if `changed_files` is non-empty; diff paths must match `changed_files` |
| submit.json | Must pass `contracts/submit/submit.schema.json` validation |
| evidence/ | Optional; if present, files must be readable |

## Retention Policy

- **Active tasks**: All artifacts retained indefinitely
- **Completed tasks (done)**: Artifacts retained for 30 days, then archived
- **Failed tasks**: Artifacts retained for 90 days for post-mortem analysis
- **DLQ tasks**: Artifacts retained permanently until manual cleanup
