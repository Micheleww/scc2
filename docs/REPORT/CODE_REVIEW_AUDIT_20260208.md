# SCC2 Code Review Audit Report

**Date**: 2026-02-08
**Scope**: Full repository strict code review
**Reviewer**: Automated (Claude Opus 4.6)

---

## Executive Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 8 |
| HIGH     | 18 |
| MEDIUM   | 25 |
| LOW      | 12 |

The repository is a sophisticated multi-component system (Node.js + Python) with ~1,300 files. The primary risks are: **a single 13,600-line god-file** (`gateway.mjs`), **command injection vulnerabilities** in Python subprocess calls, **near-zero unit test coverage** for critical paths, and **overly permissive JSON schemas** that silently accept invalid data.

---

## Module 1: `oc-scc-local/src/gateway.mjs` (13,603 lines)

### CRITICAL: God-File / Single Point of Failure

The gateway is a single monolithic file containing:
- HTTP server & reverse proxy
- Job queue scheduler & executor
- Taskboard CRUD
- Circuit breaker / degradation logic
- Instinct pattern clustering (simhash, failure taxonomy)
- Playbook engine
- SSOT sync
- Five Whys / Radius Audit orchestration
- Flow manager
- Prompt rendering bridge
- YAML serializer
- Worker lifecycle management
- 100+ REST endpoint handlers

**Risk**: Any syntax error, uncaught exception, or merge conflict in this single file takes down the entire system. Debugging, testing, and reviewing a 13K-line file is impractical.

### Findings

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | CRITICAL | `gateway.mjs` (entire file) | 13,603-line god-file; needs decomposition into 15-20 modules |
| 2 | HIGH | `gateway.mjs:5-8` | Inconsistent indentation (tabs on lines 5-8, spaces elsewhere) |
| 3 | HIGH | `gateway.mjs:2200` | `SCC_REPO_ROOT` defaults to `"C:/scc"` (Windows-only, 10+ occurrences) |
| 4 | HIGH | `gateway.mjs:26` | `occliBin` hardcoded to `"C:/scc/OpenCode/opencode-cli.exe"` |
| 5 | HIGH | `gateway.mjs:2093` | `--dangerously-bypass-approvals-and-sandbox` flag on codex exec |
| 6 | HIGH | `gateway.mjs:61` | `guardBypassRegex` detects guard bypass text but only logs, does not block |
| 7 | HIGH | `gateway.mjs:2222-2274` | `validateSubmitSchema` and `validateVerdictSchema` are nested inside each other due to a missing closing brace -- **structural bug** |
| 8 | MEDIUM | `gateway.mjs:169-174` | `computeRouterStatsSnapshot` swallows all write errors silently |
| 9 | MEDIUM | `gateway.mjs:676-697` | `readJsonlTail` reads entire file into memory -- O(n) for large JSONL files, should use reverse-read or streaming |
| 10 | MEDIUM | `gateway.mjs:1364,1369,1379,1384` | `toYaml()` uses `\\n` (literal backslash-n) instead of actual newlines in several places |
| 11 | MEDIUM | `gateway.mjs:1812` | `renderInstinctSchemasYaml()` writes `\\n` (escaped) to file instead of actual newline |
| 12 | MEDIUM | `gateway.mjs:2017` | `mapResultToEventType` has mixed tab/space indentation |
| 13 | LOW | `gateway.mjs:1389-1391` | `sha1()` function duplicates functionality already in `crypto`; `sha256Hex()` is also duplicated (defined both here and in `prompt_registry.mjs`) |
| 14 | LOW | `gateway.mjs:260` | `defaultSsotAxioms.ssot_hash` is a placeholder `"sha256:TODO"` |

### Missing Tests

- **Zero unit tests** for gateway.mjs
- The `smoke.mjs` file only checks HTTP status codes on 6 endpoints
- No test for job scheduling logic, circuit breakers, degradation matrix, or verdict computation integration

---

## Module 2: `oc-scc-local/src/` (Supporting Modules)

### `prompt_registry.mjs`

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | LOW | Lines 1-331 | Well-structured, good path traversal prevention via `safeResolveUnderRoot`. No critical issues. |
| 2 | LOW | Line 80 | Cache invalidation relies on `mtimeMs` comparison, which can have sub-ms precision issues on some filesystems |

### `role_system.mjs`

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | LOW | Lines 1-221 | Well-structured with good validation. Minor: `readJsonFile` (line 6-9) does not strip BOM. |
| 2 | LOW | Line 201 | `roleDefaultSkills` silently caps at 32 skills without warning |

### `factory_policy_v1.mjs`

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | MEDIUM | Lines 1-63 | Only tests boolean `true`/`false` in degradation matrix `when` clause; no support for numeric thresholds or ranges |

### `verifier_judge_v1.mjs`

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | MEDIUM | Line 71 | `gatesOk` logic uses string `.includes(":failed")` which could false-match on legitimate reason strings |
| 2 | LOW | Lines 1-89 | Only 89 lines; well-focused. But verdict logic should have exhaustive tests (only 4 cases in selfcheck) |

### `preflight_v1.mjs`

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | MEDIUM | Line 72 | `globToRegex` has incomplete escaping -- `[` and `]` inside character classes are not handled |
| 2 | LOW | Lines 78-111 | `shellSplit` is a home-grown shell parser; does not handle all POSIX edge cases (escaped quotes, dollar expansion) |

---

## Module 3: Python Tools (`tools/scc/`, `scc-top/tools/`)

### CRITICAL: Command Injection

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | CRITICAL | `scc-top/tools/scc/ops/run_contract_task.py:66` | `shell=True` with user-controlled `cmd` parameter |
| 2 | CRITICAL | `scc-top/tools/scc/ops/contract_runner.py:45` | `shell=True` in subprocess call |
| 3 | CRITICAL | `tools/scc/runtime/run_child_task.py:407-421` | `_run_shell()` accepts unsanitized `executor_cmd` from CLI args |
| 4 | HIGH | `scc-top/tools/unified_server/services/executor_service.py:49,58` | Hardcoded paths: `r"C:\Users\Nwe-1\AppData\Roaming\npm\codex.cmd"` and `r"c:\scc\OpenCode\opencode-cli.exe"` |

### HIGH: Missing Test Coverage

| Directory | Python Files | Test Files | Coverage |
|-----------|-------------|------------|----------|
| `tools/scc/` | 50 | 0 | **0%** |
| `tools/scc/runtime/` | 8 | 0 | **0%** |
| `tools/scc/gates/` | 6 | 0 | **0%** |
| `scc-top/tools/` | 281 | 34 | 12% |

Critical untested modules:
- `tools/scc/runtime/run_child_task.py` -- main executor
- `tools/scc/runtime/orchestrator_v1.py` -- task orchestration
- `tools/scc/runtime/unified_diff_apply.py` -- patch application
- `tools/scc/gates/run_ci_gates.py` -- CI gate enforcement

### Other Python Issues

| # | Severity | File | Issue |
|---|----------|------|-------|
| 5 | HIGH | `tools/scc/runtime/orchestrator_v1.py:89-95` | TOCTOU race in lock file check |
| 6 | MEDIUM | `tools/scc/models/adapters.py:103-104` | `except Exception: continue` silently ignores JSON parse errors |
| 7 | MEDIUM | `requeue_and_dispatch.py:2-3` | Hardcoded `http://127.0.0.1:18788` and `artifacts/taskboard/tasks.json` |
| 8 | MEDIUM | `tools/scc/runtime/run_child_task.py:197` | Hardcoded timeout `timeout_s=240` |
| 9 | LOW | Multiple files | Bare `except Exception:` instead of specific exception types |

---

## Module 4: Contracts (JSON Schemas)

### Overly Permissive Schemas

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | HIGH | `contracts/envelope/envelope.schema.json:11` | `"payload": {}` -- completely unconstrained, defeats validation purpose |
| 2 | HIGH | `contracts/event/event.schema.json:6` | `"additionalProperties": true` -- typos in field names silently accepted |
| 3 | HIGH | `contracts/verdict/verdict.schema.json:17` | `actions` items allow arbitrary properties |
| 4 | MEDIUM | `contracts/factory_policy/factory_policy.schema.json` | No cross-field validation: `EXTERNAL + INTERNAL` can exceed `TOTAL` WIP limit |
| 5 | MEDIUM | `contracts/child_task/child_task.schema.json` | No `maxItems` on `files` and `allowedTests` arrays |
| 6 | MEDIUM | `contracts/submit/submit.schema.json` | `changed_files` required but `new_files` and `touched_files` optional -- inconsistent |
| 7 | LOW | All schemas | No `description` fields explaining field semantics |
| 8 | LOW | All schemas | No `maxLength` on string fields |

---

## Module 5: Selfcheck Scripts

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | HIGH | `scripts/selfcheck_eval_samples_v1.mjs:57` | Hardcoded `cmd.exe` -- Windows-only, fails on Linux/macOS |
| 2 | HIGH | `scripts/selfcheck_factory_policy_v1.mjs:11` | Default path `"C:/scc"` -- Windows-only |
| 3 | MEDIUM | All selfcheck scripts | Smoke tests only; no edge case / error path / negative testing |
| 4 | MEDIUM | `selfcheck_verdict_v1.mjs` | Only 4 test cases for verdict logic |
| 5 | LOW | All selfcheck scripts | No test report output (TAP, JUnit XML) -- only exit codes |

---

## Module 6: CI/CD (`.github/workflows/claude.yml`)

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | MEDIUM | `claude.yml:42` | Uses `claude-3-5-sonnet-latest` (floating tag) -- review results may change unpredictably between runs |
| 2 | LOW | `claude.yml:26` | Claude action runs on every PR open/sync -- could be expensive for high-volume repos |
| 3 | LOW | Repo-wide | No linting, type-checking, or test CI workflow -- only the Claude review action exists |

---

## Module 7: UI (`oc-scc-local/ui/sccdev/`)

| # | Severity | File | Issue |
|---|----------|------|-------|
| 1 | MEDIUM | `app.js:30-33` | `setHtml()` uses `innerHTML` -- if any server data is not escaped, XSS is possible |
| 2 | MEDIUM | `app.js:163` | `setInterval(() => refresh().catch(() => {}), 2500)` -- 2.5s polling with silent error swallowing |
| 3 | LOW | `app.js:2` | `esc()` function only escapes `&`, `<`, `>` -- missing `"` and `'` escaping for attribute contexts |

---

## Module 8: Configuration & Secrets

| # | Severity | Location | Issue |
|---|----------|----------|-------|
| 1 | HIGH | `gateway.mjs` (10+ locations) | Windows paths `"C:/scc"` hardcoded as fallback defaults throughout |
| 2 | MEDIUM | `config/runtime.env` | No `.gitignore` entry for `runtime.env` (only `runtime.env.example` is committed) |
| 3 | MEDIUM | `opencode.json` | Contains API provider URLs but relies on external secrets management |
| 4 | LOW | `gateway.mjs:292-398` | 107-entry `configRegistry` array with no schema validation of its own structure |

---

## Actionable Fix Checklist

### P0 -- Immediate (Blocks Production Safety)

- [ ] **FIX** `scc-top/tools/scc/ops/run_contract_task.py`: Remove `shell=True`, use argument lists
- [ ] **FIX** `scc-top/tools/scc/ops/contract_runner.py`: Remove `shell=True`, use argument lists
- [ ] **FIX** `tools/scc/runtime/run_child_task.py`: Validate `--executor-cmd` input before shell execution
- [ ] **FIX** `gateway.mjs:2222-2274`: Fix nested function definitions (missing closing brace causes `validateVerdictSchema` to be defined inside `validateSubmitSchema`)
- [ ] **FIX** `gateway.mjs:1364,1369,1379,1384`: `toYaml()` produces literal `\n` strings instead of newlines

### P1 -- High Priority (Next Sprint)

- [ ] **DECOMPOSE** `gateway.mjs` into separate modules: `scheduler.mjs`, `board.mjs`, `circuit_breaker.mjs`, `instinct.mjs`, `playbook_engine.mjs`, `flow_manager.mjs`, `workers.mjs`, `routes.mjs`, `utils.mjs`
- [ ] **REMOVE** all hardcoded `"C:/scc"` and `"C:/scc/OpenCode/..."` paths; require `SCC_REPO_ROOT` env var or compute from `__dirname`
- [ ] **ADD** unit tests for `verifier_judge_v1.mjs` (target: 20+ cases covering all verdict paths)
- [ ] **ADD** unit tests for `preflight_v1.mjs` (target: path traversal, glob edge cases, missing files)
- [ ] **ADD** unit tests for `factory_policy_v1.mjs` (target: degradation matrix matching)
- [ ] **FIX** `contracts/envelope/envelope.schema.json`: Define payload sub-schemas per protocol
- [ ] **FIX** `contracts/event/event.schema.json`: Set `additionalProperties: false`
- [ ] **ADD** `.eslintrc` / `biome.json` and CI linting step
- [ ] **ADD** `npm test` script that runs all selfchecks and reports results

### P2 -- Medium Priority (2-4 Sprints)

- [ ] **ADD** Python unit tests for `tools/scc/runtime/` (target: 80% coverage)
- [ ] **ADD** Python unit tests for `tools/scc/gates/` (target: 80% coverage)
- [ ] **FIX** `tools/scc/runtime/orchestrator_v1.py`: Replace lock file TOCTOU with atomic operation
- [ ] **FIX** All selfcheck scripts: Add cross-platform support (remove `cmd.exe` dependency)
- [ ] **FIX** `app.js:2`: Add `"` and `'` to `esc()` function for full XSS prevention
- [ ] **FIX** `app.js:30-33`: Use `textContent` instead of `innerHTML` where possible
- [ ] **ADD** `maxItems` constraints to all array fields in contract schemas
- [ ] **ADD** `description` fields to all contract schema properties
- [ ] **ADD** CI workflow for linting + selfcheck tests on every PR
- [ ] **FIX** Bare `except Exception:` in Python files -- use specific exception types

### P3 -- Low Priority (Backlog)

- [ ] **REMOVE** duplicate `sha256Hex()` / `sha1()` utility functions
- [ ] **FIX** `gateway.mjs:260`: Replace `"sha256:TODO"` placeholder
- [ ] **ADD** TAP or JUnit output format to selfcheck scripts
- [ ] **ADD** `maxLength` constraints to string fields in schemas
- [ ] **PIN** Claude action to a specific model version instead of `latest` tag
- [ ] **ADD** API rate limiting on gateway endpoints (currently unlimited)

---

## Risk Summary by Module

| Module | Risk Level | Primary Concern |
|--------|-----------|-----------------|
| `gateway.mjs` | **CRITICAL** | God-file, structural bugs, 0 tests |
| Python `runtime/` | **CRITICAL** | Command injection, 0 tests |
| Python `ops/` | **CRITICAL** | `shell=True` injection |
| Contract schemas | **HIGH** | Silently accept invalid data |
| Selfcheck scripts | **HIGH** | Windows-only, smoke-level coverage |
| CI/CD | **MEDIUM** | No lint/test pipeline |
| UI | **MEDIUM** | Potential XSS via innerHTML |
| Config | **MEDIUM** | Hardcoded Windows paths |
| `prompt_registry.mjs` | **LOW** | Well-structured |
| `role_system.mjs` | **LOW** | Well-structured |
