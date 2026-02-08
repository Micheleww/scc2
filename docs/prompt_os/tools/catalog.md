# Tool Catalog

> Prompt OS — Tools Layer / Catalog

## Available Tools

| Tool | Type | Description | Auth Required | Rate Limit |
|------|------|-------------|---------------|------------|
| `git` | VCS | Version control operations (add, commit, diff, log) | No | None |
| `rg` (ripgrep) | Search | Fast regex search across files | No | None |
| `node` | Runtime | Execute JavaScript/Node.js scripts | No | None |
| `python` | Runtime | Execute Python scripts | No | None |
| `pytest` | Test | Run Python test suites | No | None |
| `npm` | Package | Node.js package management | No | None |
| `curl` | Network | HTTP requests (restricted by role) | Yes | 10/min |
| `gh` | GitHub | GitHub CLI for PR/issue operations | Yes | 30/min |
| `jq` | Data | JSON processing and transformation | No | None |
| `sed` | Text | Stream editing for text transformation | No | None |
| `awk` | Text | Pattern scanning and processing | No | None |

## Tool Categories

### Category 1: Always Available
Tools available to all roles without restriction:
- `git`, `rg`, `node`, `python`, `jq`

### Category 2: Role-Gated
Tools available only to roles with matching `permissions.tools.allow`:
- `pytest` — engineer, reviewer
- `npm` — engineer, gateway_engineer
- `curl` — connectors only (when network permission granted)

### Category 3: Restricted
Tools that require explicit permission and are denied by default:
- `network` — All outbound HTTP/WebSocket (denied unless role allows)
- `docker` — Container operations (reserved for CI)
- `kubectl` — Kubernetes operations (reserved for ops)

## Tool Resolution

```
1. Check role.permissions.tools.deny → if match, BLOCK
2. Check role.permissions.tools.allow → if match, ALLOW
3. Default: BLOCK (whitelist model)
```

## Adding New Tools

1. Register in this catalog with type, description, auth requirements
2. Add to relevant role JSON files under `permissions.tools.allow`
3. If rate-limited, add entry to gateway rate limiter config
4. Document in `api_rules.md` if the tool accesses external APIs
