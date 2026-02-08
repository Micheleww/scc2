# Data Classification Rules

> Prompt OS — Tools Layer / Data Rules

## Classification Levels

| Level | Label | Examples | Handling |
|-------|-------|----------|----------|
| **L0** | Public | Source code, docs, configs | No restrictions on reading/writing |
| **L1** | Internal | Task state, board data, logs | Read within role scope only |
| **L2** | Sensitive | API keys, tokens, credentials | Never read/write/log; deny_paths enforced |
| **L3** | Restricted | User PII, auth secrets | Never process; escalate if encountered |

## Rules by Classification

### L0 — Public
- May be included in context packs
- May be written to artifacts
- May appear in commit messages and PR descriptions
- May be logged in full

### L1 — Internal
- May be included in context packs for authorized roles
- Must not appear in commit messages or PR descriptions
- May be logged with redaction of large payloads (>1KB summarized)
- Task IDs, status, and metadata are L1

### L2 — Sensitive
- Must NEVER be included in context packs or prompts
- Must NEVER be written to artifacts, logs, or evidence
- Enforced via `deny_paths: ["**/secrets/**"]` in all roles
- If accidentally encountered, emit `POLICY_VIOLATION` and halt
- Examples: `.env` files, `credentials.json`, API key strings

### L3 — Restricted
- Must NEVER be processed by any AI agent
- If detected in task input, reject task immediately
- Escalate to human operator
- No logging of content (log only the event occurrence)

## Path-Based Enforcement

```
deny_paths patterns for sensitive data:
  **/secrets/**
  **/.env
  **/.env.*
  **/credentials*
  **/private_key*
  **/*.pem
  **/*.key
```

## Data Flow Rules

1. **Input Sanitization**: All task inputs must be validated against schema before processing
2. **Output Filtering**: Submit artifacts must not contain L2/L3 data
3. **Log Redaction**: Automated redaction of patterns matching API keys, tokens, passwords
4. **Evidence Retention**: L0/L1 evidence retained for 30 days; L2/L3 evidence never created
5. **Context Pack Assembly**: Only L0/L1 data may enter context packs; L2 paths excluded at assembly time

## Violation Response

| Detection | Action |
|-----------|--------|
| L2 data in context pack | Strip and log warning |
| L2 data in artifact | Reject submission |
| L3 data in task input | Reject task, escalate |
| L2/L3 data in log output | Redact retroactively |
