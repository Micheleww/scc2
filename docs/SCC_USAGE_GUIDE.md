# SCC Usage Guide — For All AI Agents

> This document is the definitive reference for any AI agent (opencodecli, codex, Claude, GPT, GLM, Kimi, etc.) operating within the SCC (Self-Coordinating Codebase) system. Read this before executing any task.

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Task Lifecycle](#2-task-lifecycle)
3. [How to Create Tasks (API Reference)](#3-how-to-create-tasks)
4. [Role System](#4-role-system)
5. [Pins System (File Access Control)](#5-pins-system)
6. [Submit Contract](#6-submit-contract)
7. [Error Codes & Recovery](#7-error-codes--recovery)
8. [Factory Policy & Circuit Breakers](#8-factory-policy--circuit-breakers)
9. [Prompt System](#9-prompt-system)
10. [Key Endpoints Quick Reference](#10-key-endpoints-quick-reference)
11. [Token Optimization](#11-token-optimization)
12. [Common Pitfalls](#12-common-pitfalls)

---

## 1. System Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                   SCC Gateway (:18788)                    │
│              oc-scc-local/src/gateway.mjs                 │
│                                                          │
│  ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────┐ │
│  │  Board    │  │ Scheduler │  │ Verifier │  │ Judge  │ │
│  │ (Tasks)   │  │ (Dispatch)│  │ (Schema) │  │(Verdict)│ │
│  └─────┬────┘  └─────┬─────┘  └────┬─────┘  └───┬────┘ │
│        │              │             │             │      │
│  ┌─────┴──────────────┴─────────────┴─────────────┴────┐ │
│  │              HTTP API Layer                          │ │
│  └─────────────────────┬───────────────────────────────┘ │
└────────────────────────┼─────────────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
    ┌─────▼─────┐  ┌────▼─────┐  ┌────▼─────┐
    │ opencodecli│  │ opencode │  │  codex   │
    │  Worker 1  │  │ Worker 2 │  │ Worker 3 │
    └───────────┘  └──────────┘  └──────────┘
```

**Core Components:**

| Component | Location | Responsibility |
|-----------|----------|---------------|
| **Gateway** | `oc-scc-local/src/gateway.mjs` | HTTP server, task board, scheduler, circuit breaker, prompt rendering, context pack assembly |
| **Board** | In-memory (gateway.mjs) | Task CRUD, status transitions, lane routing, WIP enforcement |
| **Executor** | External (opencodecli/codex) | Claims tasks, executes goals, produces submit.json |
| **Verifier** | `oc-scc-local/src/verifier_judge.mjs` | Validates submit.json against schema, checks scope/tests |
| **Judge** | `oc-scc-local/src/verifier_judge.mjs` | Issues verdict: DONE / RETRY / ESCALATE |
| **Preflight** | `oc-scc-local/src/preflight.mjs` | Pre-execution checks: role policy, pins, test requirements |
| **Map** | `oc-scc-local/src/map_v1.mjs` | Code structure index with symbols, entry points, env keys |
| **Prompt Registry** | `oc-scc-local/src/prompt_registry.mjs` | Block-based prompt template system |

**Default Gateway Port:** `18788` (configurable via `GATEWAY_PORT` env var)

---

## 2. Task Lifecycle

### Status Flow

```
backlog → ready → in_progress ──→ done ✓
                      │
                      ├──→ failed ──→ [retry → in_progress]
                      │                        │
                      ├──→ blocked             ├──→ [escalate → quarantine]
                      │                        │
                      └──→ needs_split         └──→ [abort → dlq]
```

**Valid statuses:** `backlog`, `needs_split`, `ready`, `in_progress`, `blocked`, `done`, `failed`

### Lanes

| Lane | Purpose | Priority |
|------|---------|----------|
| `fastlane` | Urgent/small tasks | Highest — dispatched first |
| `mainlane` | Standard work | Normal |
| `batchlane` | Parallel batch jobs | Low — bulk operations |
| `quarantine` | Problematic tasks | Isolated — manual review |
| `dlq` | Dead Letter Queue | Terminal — abandoned tasks |

### Parent vs Atomic Tasks

- **Parent tasks** (`kind: "parent"`): Containers for planning/splitting. Cannot be executed directly.
- **Atomic tasks** (`kind: "atomic"`): Executable units of work. Must have `files[]` array.
- **Budgets**: `max_children` limits children per parent; `max_depth` limits nesting levels.
- **Inheritance**: Child tasks inherit parent's lane if not overridden.

---

## 3. How to Create Tasks

### API Endpoint

```
POST http://127.0.0.1:18788/board/tasks
Content-Type: application/json
```

### Required Fields

```json
{
  "title": "Short descriptive title",
  "goal": "Detailed task description with acceptance criteria"
}
```

### Full Schema (All Fields)

```json
{
  "title": "string (required)",
  "goal": "string (required) — the prompt the executor receives",

  "kind": "parent | atomic (default: atomic)",
  "parentId": "uuid (optional — links to parent task)",

  "role": "string (default: engineer) — must match roles/*.json",
  "status": "backlog | ready | in_progress | ... (default: backlog)",
  "lane": "fastlane | mainlane | batchlane | quarantine | dlq (default: mainlane)",
  "priority": "number (optional)",

  "files": ["string[] (required for atomic) — repo-relative file paths, max 16"],
  "skills": ["string[] (optional, max 16) — defaults to role skills"],

  "pins": {
    "allowed_paths": ["string[] (required if pins present, at least 1)"],
    "forbidden_paths": ["string[] (optional)"]
  },

  "allowedExecutors": ["opencodecli", "codex"],
  "allowedModels": ["string[] (max 8) — e.g. glm-4.7, kimi-k2.5, claude-sonnet"],
  "allowedTests": ["string[] (max 24) — test commands to verify output"],
  "assumptions": ["string[] (max 16) — constraints/context"],

  "runner": "external | internal (default: external)",
  "timeoutMs": "number (optional)",
  "contract": "object (optional — acceptance contract)",
  "toolingRules": "object (optional)"
}
```

### Validation Rules

| Rule | Consequence |
|------|-------------|
| `title` is empty | → 400 `missing_title` |
| `goal` is empty | → 400 `missing_goal` |
| `kind=atomic` but no `files` | → 400 `missing_files` |
| `pins` present but `allowed_paths` empty | → 400 `missing_pins_allowlist` |
| Patch-producing role but no real test in `allowedTests` | → 400 `missing_real_test` |
| Files outside role's write scope | → 400 `role_policy_violation` |
| Parent has too many children | → 400 `max_children_exceeded` |
| Nesting depth exceeded | → 400 `max_depth_exceeded` |

### Example: Create a doc task

```bash
curl -X POST http://127.0.0.1:18788/board/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Write API documentation",
    "goal": "Create docs/api/README.md covering all board endpoints...",
    "kind": "atomic",
    "role": "doc",
    "lane": "batchlane",
    "status": "ready",
    "files": ["docs/api/README.md"],
    "pins": { "allowed_paths": ["docs/api/"] },
    "allowedExecutors": ["opencodecli"],
    "allowedModels": ["glm-4.7", "kimi-k2.5"],
    "allowedTests": ["test -s docs/api/README.md"]
  }'
```

### Response (201 Created)

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Write API documentation",
  "status": "ready",
  "lane": "batchlane",
  "createdAt": 1707350400000,
  ...
}
```

---

## 4. Role System

Roles define what an agent CAN and CANNOT do. Each role is a JSON file in `roles/*.json`.

### Core Roles

| Role | Can Plan | Can Code | Can Test | Primary Scope |
|------|----------|----------|----------|--------------|
| **planner** | Yes | No | No | Decompose goals into task graphs |
| **splitter** | Yes | No | No | Split parent → atomic children |
| **engineer** | No | Yes | Yes | Write code, run tests |
| **reviewer** | No | No | No | Review patches, give verdicts |
| **doc** | No | No | No | Write/maintain documentation |
| **ssot_curator** | No | No | No | Maintain Single Source of Truth |
| **designer** | Yes | No | No | System architecture, task_graph.json |

### Role Policy Structure (roles/*.json)

```json
{
  "name": "engineer",
  "can_plan": false,
  "can_write_code": true,
  "can_run_tests": true,
  "can_modify_contracts": false,
  "can_emit_events": true,
  "preflight_required": true,
  "hygiene_required": true,
  "max_attempts": 2,
  "paths": {
    "read": { "allow": ["scc-top/**", "docs/**"], "deny": ["secrets/**"] },
    "write": { "allow": ["scc-top/**", "docs/**"], "deny": ["contracts/**", "roles/**"] }
  },
  "tools": {
    "allow": ["git", "rg", "node", "python", "pytest"],
    "deny": ["network"]
  },
  "required_outputs": {
    "artifacts": ["artifacts/**"],
    "submit_schema": "contracts/submit/submit.schema.json"
  }
}
```

### Key Rules
- You can ONLY use tools listed in `tools.allow`
- You can ONLY write to paths matching `paths.write.allow`
- `deny` always overrides `allow`
- If `preflight_required: true`, pins and role policy are validated before execution
- If `hygiene_required: true`, output format is validated after execution

---

## 5. Pins System

Pins (别针) are **task-level file access control**. They determine which files you can read/write for a specific task.

### Structure

```json
{
  "allowed_paths": ["src/gateway.mjs", "docs/**"],
  "forbidden_paths": ["**/secrets/**", "node_modules/**"]
}
```

### Rules

1. **Glob syntax**: `**` matches multiple directories, `*` matches single level
2. **Forbidden overrides allowed**: If a path matches both, it's forbidden
3. **Empty allowed_paths = no access**: You cannot read or write anything
4. **Child ⊆ Parent**: A child task's pins must be a subset of its parent's pins
5. **Pins + Role = Final scope**: Your effective scope = `pins ∩ role.paths.write`

### Optimal Pins Usage

```
❌ BAD:  { "allowed_paths": ["src/**"] }                    → too broad, wastes context tokens
✅ GOOD: { "allowed_paths": ["src/gateway.mjs"] }           → precise file
✅ BEST: { "allowed_paths": ["src/gateway.mjs"],             → precise file + line range
          "line_windows": { "src/gateway.mjs": [3500, 3700] } }
```

Using `line_windows` reduces context from 200KB → 5-10KB, saving ~50K tokens per task.

---

## 6. Submit Contract

When you complete a task, you MUST produce these outputs:

### Machine-Parsable Output Lines

Every task output MUST include these 4 lines (the gateway parses them):

```
REPORT: <one-line outcome description>
SELFTEST.LOG: <test commands run, or 'none'>
EVIDENCE: <artifact paths, or 'none'>
SUBMIT: {"status":"DONE","reason_code":"ok","touched_files":["file1.md"],"tests_run":["test -s file1.md"]}
```

### submit.json Schema (`contracts/submit/submit.schema.json`)

```json
{
  "schema_version": "scc.submit.v1",
  "task_id": "uuid",
  "status": "DONE | NEED_INPUT | FAILED",
  "reason_code": "string (e.g. ok, ci_failed, scope_conflict)",
  "changed_files": ["list of files you modified"],
  "new_files": ["list of new files you created"],
  "tests": {
    "commands": ["test commands executed"],
    "passed": true,
    "summary": "All 3 tests passed"
  },
  "artifacts": {
    "report_md": "artifacts/report.md",
    "selftest_log": "artifacts/selftest.log",
    "evidence_dir": "artifacts/evidence/",
    "patch_diff": "artifacts/patch.diff",
    "submit_json": "artifacts/submit.json"
  },
  "exit_code": 0,
  "needs_input": []
}
```

### Status Meanings

| Status | When to Use | What Happens Next |
|--------|------------|-------------------|
| `DONE` | Task completed, all tests pass | Judge validates → moves to `done` |
| `NEED_INPUT` | Missing info/files to continue | `needs_input[]` sent to planner → human |
| `FAILED` | Unrecoverable error in this attempt | May retry if `attempts < max_attempts` |

### Required Artifacts Checklist

- [ ] `artifacts/report.md` — Explain what you did and why
- [ ] `artifacts/selftest.log` — Full test execution output
- [ ] `artifacts/patch.diff` — All file changes as diff
- [ ] `artifacts/submit.json` — Structured submission
- [ ] `artifacts/evidence/` — Additional evidence (optional)

---

## 7. Error Codes & Recovery

### Error Code Reference

| Code | Meaning | Auto Recovery | Action |
|------|---------|---------------|--------|
| `CI_FAILED` | Tests did not pass | Yes (retry) | Read selftest.log, fix issue, re-run |
| `SCOPE_CONFLICT` | Modified files outside pins | Yes (retry) | Remove out-of-scope changes |
| `SCHEMA_VIOLATION` | submit.json format invalid | Yes (retry) | Fix JSON against schema |
| `PINS_INSUFFICIENT` | Needed files not in pins | No → NEED_INPUT | Request additional pins |
| `POLICY_VIOLATION` | Used forbidden tool/path | No → Escalate | Requires role change |
| `BUDGET_EXCEEDED` | Token or time limit hit | No → Abort | Split into smaller tasks |
| `TIMEOUT_EXCEEDED` | Execution timed out | No → Abort | Reduce scope |
| `EXECUTOR_ERROR` | Model API failure | Yes (retry 3x) | Exponential backoff |
| `PREFLIGHT_FAILED` | Pre-execution checks failed | No → Fix config | Correct pins/role |
| `ci_skipped` | No test commands provided | No → Fix task | Add allowedTests |
| `tests_only_task_selftest` | Only selftest, no real tests | No → Fix task | Add real test commands |

### Escalation Chain

```
Level 0: Self-retry (same model, within max_attempts)
    ↓ still failing
Level 1: Model upgrade (switch to stronger model via degradation matrix)
    ↓ still failing
Level 2: Role escalation (switch to higher-permission role)
    ↓ still failing
Level 3: Human intervention (status=NEED_INPUT)
    ↓ unresolvable
Level 4: Task abort (→ DLQ)
```

**Fast-track escalation:**
- `POLICY_VIOLATION` → skip to Level 3 (human)
- `BUDGET_EXCEEDED` → skip to Level 4 (abort)

---

## 8. Factory Policy & Circuit Breakers

### Factory Policy (`factory_policy.json`)

Controls global system behavior:

```json
{
  "wip_limit": 10,
  "lanes": {
    "fastlane": { "wip": 3, "priority": 1 },
    "mainlane": { "wip": 5, "priority": 2 },
    "batchlane": { "wip": 10, "priority": 3 }
  },
  "budgets": {
    "max_tokens_per_task": 100000,
    "max_children": 20,
    "max_depth": 3
  },
  "circuit_breakers": {
    "consecutive_failures": 5,
    "cooldown_ms": 300000
  }
}
```

### Circuit Breaker Pattern

```
CLOSED (normal) ──[5 consecutive failures]──→ OPEN (blocked)
                                                   │
                                          [cooldown 5 min]
                                                   │
                                              HALF-OPEN
                                                   │
                                    ┌──────────────┼──────────────┐
                                    │              │              │
                               [success]      [failure]     [failure]
                                    │              │              │
                                 CLOSED          OPEN          OPEN
```

### Degradation Matrix (Model Tiers)

```
Tier 1 (Premium):  claude-opus, gpt-4o
Tier 2 (Standard): claude-sonnet, gpt-4o-mini
Tier 3 (Free):     glm-4.7, kimi-k2.5, deepseek
```

When a tier is unavailable or budget-constrained, the system falls back to the next tier.

---

## 9. Prompt System

### Architecture

```
Prompt Registry (registry.json)
    │
    ├── Block Templates (prompts/blocks/*.txt)
    │   └── {{placeholder}} interpolation
    │
    ├── Context Pack (assembled at runtime)
    │   ├── Pinned file content
    │   ├── Line windows
    │   └── Map summary
    │
    └── Runtime Injection
        ├── <context_pack> XML block
        ├── <thread> history block
        └── CI Handbook (static)
```

### Prompt Registry (`oc-scc-local/prompts/registry.json`)

Defines reusable prompt blocks:
```json
{
  "blocks": {
    "header_3pointers_v1": {
      "src": "blocks/header_3pointers_v1.txt",
      "description": "Standard 4-pointer header for all prompts"
    }
  }
}
```

### Block Template Example

```
READ_FIRST (SSOT pointers):
1) {{law_ref}}      → docs/AI_CONTEXT.md
2) {{nav_ref}}      → docs/NAVIGATION.md
3) {{rules_ref}}    → docs/PROMPTING.md
4) {{exec_ref}}     → docs/EXECUTOR.md
```

### Context Pack Assembly (gateway.mjs:7370-7547)

1. Resolve pins → file list
2. Read each file (respecting line_windows)
3. Concatenate with headers: `## {filename} (lines {start}-{end})`
4. Enforce byte limit (220KB default)
5. Store as `contextpacks/{id}.md`
6. Inject into prompt as `<context_pack id="{id}">...</context_pack>`

### Thread History Injection

For multi-turn tasks, recent decisions are injected:
```xml
<thread id="abc123">
Recent decisions:
- Chose to split auth module into 3 subtasks
- Selected engineer role for implementation
- Skipped map rebuild (no structural changes)
</thread>
```

---

## 10. Key Endpoints Quick Reference

### Board (Task Management)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/board/tasks` | List all tasks (supports `?status=ready&lane=batchlane`) |
| `POST` | `/board/tasks` | Create new task |
| `GET` | `/board/tasks/:id` | Get task by ID |
| `PATCH` | `/board/tasks/:id` | Update task (status, lane, priority) |
| `DELETE` | `/board/tasks/:id` | Remove task |

### Executor

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/executor/jobs/atomic` | Submit atomic job for execution |
| `GET` | `/executor/jobs/:id` | Get job status |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/sccdev/api/v1/snapshot` | Full system state snapshot |
| `GET` | `/sccdev/` | Web UI dashboard |
| `GET` | `/health` | Health check |

### Docs (served via gateway)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/docs/INDEX.md` | Documentation entry point |
| `GET` | `/docs/AI_CONTEXT.md` | Agent context rules |
| `GET` | `/docs/EXECUTOR.md` | Execution contract |

---

## 11. Token Optimization

> This section is critical for cost control. Based on analysis of gateway.mjs token mechanisms.

### Current Token Usage Profile

| Component | Avg Tokens | Source |
|-----------|-----------|--------|
| Context pack | 1,500-55,000 | Pinned files (up to 220KB) |
| CI Handbook | ~200 | Static injection every prompt |
| Header/blocks | ~100 | 3-pointer + role block |
| Thread history | ~50 | Last 3-6 decisions |
| Goal/prompt | 500-2,000 | Task-specific |

### Strategy 1: Precision Pins (Highest Impact)

The Token CFO (`gateway.mjs:6252-6325`) detects that **60%+ of context files go unused** in 15-20% of tasks.

```
❌ pins: { allowed_paths: ["src/**"] }
   → Includes entire src/ directory → 220KB context → 55K tokens WASTED

✅ pins: { allowed_paths: ["src/gateway.mjs"],
           line_windows: { "src/gateway.mjs": [3500, 3700] } }
   → Only 200 lines → ~4KB context → ~1K tokens
```

**Action for Planner/Splitter roles:** Always use the narrowest possible pins. Use map_v1 symbol index to identify exact line ranges.

### Strategy 2: Prompt Caching (Claude-Specific)

Current `cache_ratio ≈ 0%` — no caching benefit.

**Fix:** Structure prompts so the **static prefix** (constitution + handbook + role capsule) remains identical across tasks of the same role. Claude's API will automatically cache this prefix.

```
[STATIC PREFIX — cached after first call]     ← ~500 tokens, free after cache
├── Legal prefix (constitution summary)
├── CI Handbook
├── Role capsule (e.g., engineer.md)
└── Tool digest

[VARIABLE SUFFIX — different per task]        ← billed every time
├── <context_pack> (pinned files)
├── <thread> (history)
└── Goal text
```

### Strategy 3: Context Grading by Task Type

Not all tasks need 220KB of context:

| Task Type | Recommended Limit | Rationale |
|-----------|-------------------|-----------|
| `doc` | 50KB | Only needs goal + reference snippets |
| `split` / `plan` | 80KB | Map summary + task list |
| `review` | 100KB | Patch diff + relevant code |
| `engineer` (bug fix) | 120KB | Error log + pinned code |
| `engineer` (feature) | 200KB | Needs broad context |

### Strategy 4: Token CFO Feedback Loop

The Token CFO already runs every 120 seconds (`TOKEN_CFO_HOOK_TICK_MS`), scanning the last 1200 jobs for waste. Currently it generates reports but doesn't auto-correct.

**Close the loop:**
- Let Token CFO's `actions[]` automatically tighten `pins_template` for wasteful task classes
- Exclude files that are consistently pinned but never touched
- Log savings per iteration for tracking

### Strategy 5: JSON Compaction

`JSON.stringify(obj, null, 2)` wastes ~33% bytes on indentation. For injected params:

```javascript
// ❌ In prompt injection:
JSON.stringify(snapshot, null, 2)  // 3KB

// ✅ In prompt injection:
JSON.stringify(snapshot)           // 2KB (saves 33%)
```

### Strategy 6: Map Summarization Levels

Instead of injecting the full symbol index:

| Level | Content | Size | Use For |
|-------|---------|------|---------|
| L0 | File list + entry points | ~2KB | doc, split |
| L1 | L0 + function signatures | ~10KB | review, plan |
| L2 | L1 + full symbols + dependencies | ~50KB+ | engineer |

### Token CFO Configuration

```
TOKEN_CFO_HOOK_ENABLED=true          # Enable waste detection
TOKEN_CFO_HOOK_TICK_MS=120000        # Check every 2 minutes
TOKEN_CFO_HOOK_MIN_MS=600000         # Min 10 min between CFO tasks
TOKEN_CFO_UNUSED_RATIO=0.6           # 60% unused triggers alert
TOKEN_CFO_INCLUDED_MIN=3             # Min 3 files to trigger
```

---

## 12. Common Pitfalls

### For All Agents

1. **Always check pins before modifying files.** If a file isn't in `allowed_paths`, don't touch it. The verifier will reject your submission with `SCOPE_CONFLICT`.

2. **Always produce submit.json.** Even if you fail, produce a submit with `status: "FAILED"` and `reason_code`. Silent failures are the worst outcome.

3. **Run ALL allowedTests.** The judge checks `tests.passed`. If you skip tests and claim DONE, you'll get `CI_FAILED`.

4. **Don't read SSOT directly.** `docs/SSOT.md` is for Designer role only. Executors use pins/context packs.

5. **Keep artifacts under `artifacts/<task_id>/`.** Don't leave stray files outside this directory.

### System-Level Known Issues

| Issue | Location | Impact |
|-------|----------|--------|
| **God-file** | `gateway.mjs` (13,603 lines) | Hard to navigate; changes risk side effects |
| **Silent catch blocks** | 50+ instances of `catch { }` | Errors get swallowed; check logs manually |
| **Windows paths hardcoded** | `C:\scc\...` in multiple configs | Breaks on Linux/Mac; use env vars instead |
| **toYaml() bug** | `gateway.mjs:1364,1369,1379,1384` | Produces literal `\n` instead of newlines |
| **Nested function redefinition** | `gateway.mjs:2222-2274` | `validateSubmitSchema`/`validateVerdictSchema` redefined inside function |
| **Overly permissive schemas** | `contracts/submit/submit.schema.json` | `additionalProperties: true` allows arbitrary fields |

### Tips for Free Models (GLM-4.7, Kimi-K2.5)

1. **Be explicit in goals.** Free models need more detailed instructions than premium models.
2. **Provide templates.** Show the exact format you want in the goal.
3. **Keep tasks small.** 1-3 files per task, not 10+.
4. **Use Chinese + English.** These models handle bilingual prompts well.
5. **Include validation tests.** Simple `test -s file.md` catches most failures early.

---

## Quick Start Checklist

For any new task, ensure:

- [ ] `title` and `goal` are set (required)
- [ ] `role` matches what you need to do
- [ ] `files` lists ALL files you'll create/modify
- [ ] `pins.allowed_paths` covers your files
- [ ] `allowedTests` has at least 1 real test (not just `task_selftest`)
- [ ] `allowedModels` and `allowedExecutors` are set
- [ ] Goal includes: background, requirements, acceptance criteria
- [ ] Output will include: report.md, selftest.log, patch.diff, submit.json

---

## Related Documents

- `docs/INDEX.md` — Document registry (all docs must be listed here)
- `docs/AI_CONTEXT.md` — Pins-first rules, CI handbook, task class library
- `docs/EXECUTOR.md` — Fail-closed execution contract
- `docs/NAVIGATION.md` — Endpoint and control plane reference
- `docs/PROMPT_REGISTRY.md` — Prompt block system documentation
- `docs/prompt_os/` — Prompt OS engineering assets (norms, IO, context, knowledge, tools, compiler, roles, eval)

---

*Last updated: 2026-02-08 | Generated from code review of SCC v1 codebase*
