# API Rules

> Prompt OS — Tools Layer / API Rules

## SCC Gateway API

### Base URL
```
http://localhost:18788
```

### Authentication
- No auth required for local gateway
- Future: Bearer token for remote gateway access

### Rate Limits
- Board API: 60 requests/minute per client
- Health endpoint: unlimited
- Bulk operations: 10 requests/minute

## Endpoint Rules

### Task CRUD
| Method | Endpoint | Required Fields | Notes |
|--------|----------|-----------------|-------|
| `POST` | `/board/tasks` | `title`, `goal` | Atomic tasks also need `files[]` |
| `GET` | `/board/tasks` | — | Returns all tasks; supports `?status=` filter |
| `GET` | `/board/tasks/:id` | — | Returns single task with full state |
| `PATCH` | `/board/tasks/:id` | varies | Update task fields (status, pins, etc.) |
| `DELETE` | `/board/tasks/:id` | — | Soft-delete; moves to `archived` status |

### Submission
| Method | Endpoint | Required Fields | Notes |
|--------|----------|-----------------|-------|
| `POST` | `/board/tasks/:id/submit` | `submit.json` body | Must conform to `contracts/submit/submit.schema.json` |
| `POST` | `/board/tasks/:id/verdict` | `verdict` body | Judge endpoint; `DONE`/`RETRY`/`ESCALATE` |

### System
| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Gateway health check (returns `{ ok: true }`) |
| `GET` | `/board/stats` | Board statistics (task counts by status) |
| `POST` | `/dispatch` | Trigger scheduler to dispatch ready tasks |

## Request Rules

1. **Content-Type**: Always `application/json`
2. **Idempotency**: POST to `/board/tasks` is NOT idempotent; use title-based dedup
3. **Error Format**: All errors return `{ error: string, code: string, details?: object }`
4. **Pagination**: Not currently supported; all tasks returned in single response
5. **Timeouts**: Client should set 30s timeout for all requests

## Response Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created (new task) |
| 400 | Bad request (validation failed) |
| 404 | Task not found |
| 409 | Conflict (invalid status transition) |
| 422 | Unprocessable (schema validation failed) |
| 429 | Rate limited |
| 500 | Internal server error |

## External API Rules

### When Network Access is Granted
1. Only call pre-approved endpoints (listed in connector config)
2. Set timeout to 10s for external calls
3. Retry failed calls with exponential backoff (max 3 retries)
4. Log all external calls with URL, status code, and latency
5. Never send repository secrets or credentials in requests
6. Parse responses defensively; never trust external data shapes
