# SCC Domain Knowledge Base

## Architecture Overview

```
┌─────────────────────────────────────────────┐
│              SCC Gateway (:18788)             │
│  Board │ Scheduler │ Verifier │ Judge │ CFO  │
└───────────────────┬─────────────────────────┘
                    │ HTTP API
        ┌───────────┼───────────┐
   opencodecli    codex     (future)
```

- **Gateway** (`gateway.mjs`): Monolithic HTTP server handling task CRUD, job scheduling, context pack assembly, prompt rendering, circuit breakers, Token CFO
- **Board**: In-memory task store with status transitions and lane routing
- **Executor**: External workers (opencodecli, codex) that claim and execute jobs
- **Verifier**: Validates submit.json against schema, checks scope and artifacts
- **Judge**: Issues verdict (DONE/RETRY/ESCALATE) based on verification results

## Task Lifecycle

```
backlog ──→ ready ──→ in_progress ──→ done ✓
                          │
                          ├──→ failed ──→ retry ──→ in_progress
                          │                │
                          ├──→ blocked      └──→ escalate ──→ quarantine
                          │
                          └──→ needs_split ──→ (splitter creates children)
```

## Role System (7 Core Roles)

| Role | Plan | Code | Test | Key Scope |
|------|------|------|------|-----------|
| planner | Yes | No | No | Decompose goals → task graphs |
| splitter | Yes | No | No | Parent → atomic children |
| engineer | No | Yes | Yes | Implement code changes |
| reviewer | No | No | No | Review patches, give verdicts |
| doc | No | No | No | Write documentation |
| ssot_curator | No | No | No | Maintain SSOT, indexes |
| designer | Yes | No | No | Architecture, task_graph.json |

## Event System

| Event | Trigger | Handler |
|-------|---------|---------|
| `SUCCESS` | Task completed successfully | Board status → done |
| `CI_FAILED` | Tests didn't pass | Retry or escalate |
| `SCOPE_CONFLICT` | Out-of-scope modification | Task fails |
| `POLICY_VIOLATION` | Forbidden action | Escalate to human |
| `BUDGET_EXCEEDED` | Token/time limit hit | Abort |
| `CIRCUIT_OPEN` | Consecutive failures | Block dispatch to that executor |
| `TOKEN_CFO_AUTO_CORRECTION` | CFO tightened pins | Log adjustment |
