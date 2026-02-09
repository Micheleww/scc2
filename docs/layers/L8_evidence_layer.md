# L8 证据与裁决层

> **对应SSOT分区**: `07_reports_evidence/`（报告与证据）  
> **对应技术手册**: 第11章  
> **层定位**: 证据收集、裁决判定、验证结果

---

## 8.1 层定位与职责

### 8.1.1 核心职责

L8是SCC架构的**证据管理层**，为全系统提供：

1. **证据收集** - 自动收集执行证据（日志、diff、指标）
2. **裁决判定** - 基于验收标准判定通过/失败
3. **证据存储** - 证据的持久化和索引
4. **验证结果** - 验证器输出的标准化
5. **故障分类** - 失败任务的结构化分类

### 8.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L8 证据与裁决层                               │
│ ├─ 证据收集（自动收集）                       │
│ ├─ 裁决判定（通过/失败）                      │
│ ├─ 证据存储（持久化/索引）                    │
│ └─ 故障分类（结构化分类）                     │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L6 Agent层, L14 质量层, L16 观测层           │
└─────────────────────────────────────────────┘
```

---

## 8.2 来自07_reports_evidence/的核心内容

### 8.2.1 裁决规则

#### 核心原则

```
- 验证器必须仅根据acceptance结果进行裁决
- 禁止不带检查的"looks good"裁决
- 故障关闭（fail-closed）
```

#### 裁决输出

```yaml
verdict:
  status: pass | fail
  fail_class:  # 如果fail，必须提供
    - timeout
    - test_failure
    - lint_error
    - type_error
    - security_violation
    - scope_violation
    - external_dependency
  evidence_paths:  # 证据路径列表
    - artifacts/scc_tasks/TASK-001/logs/
    - artifacts/scc_tasks/TASK-001/diff/
  timestamp: "2026-02-09T14:30:00Z"
  verifier: "verifier-agent"
```

### 8.2.2 失败代码目录

| Code | Meaning | Trigger | Action |
|------|---------|---------|--------|
| SCOPE_CONFLICT | Modified disallowed files | changed_files include paths outside pins.allowed_paths | Restrict edits to allowed scope; re-run with corrected pins |
| CI_FAILED | Tests failed | tests.passed=false or non-zero exit | Fix failures; attach logs; retry |
| SCHEMA_VIOLATION | Output schema invalid | submit.json missing required fields | Regenerate submit.json to match schema; retry |
| PINS_INSUFFICIENT | Context pins insufficient | Required inputs not pinned | Request additional pins or move required info into pinned scope |
| POLICY_VIOLATION | Role policy violated | Forbidden tools/actions used | Stop; escalate to policy owner; retry with compliant approach |
| BUDGET_EXCEEDED | Budget exceeded | Token/time/compute budget exceeded | Reduce scope; split task; retry |
| TIMEOUT_EXCEEDED | Execution timeout | Execution exceeds configured timeout | Split task; optimize steps; retry |
| EXECUTOR_ERROR | Executor internal failure | Runtime error, model API error | Retry; include stack trace hash |
| PREFLIGHT_FAILED | Preflight validation failed | Role/pins/task metadata validation fails | Fix config and rerun preflight |
| FILE_NOT_FOUND | Required file missing | A pinned file referenced does not exist | Add/restore the file or correct the path |
| PERMISSION_DENIED | Permission blocked | OS/filesystem permissions prevent read/write | Adjust permissions; change location; retry |
| MERGE_CONFLICT | Patch cannot apply cleanly | Patch application fails due to divergent base | Rebase/update; regenerate patch; retry |
| EVIDENCE_MISSING | Evidence incomplete | Required artifacts absent | Recreate missing evidence; ensure paths are correct |
| NEEDS_CLARIFICATION | Task ambiguity | Goal unclear or contradictory requirements | Ask targeted questions; proceed after clarification |

### 8.2.3 IO模式（Schemas）

> **来源**: `docs/prompt_os/io/schemas.md`

本节定义SCC PromptOS agents和executor使用的标准**输入/输出数据格式**。

The IO layer exists to make tasks:

- machine-validated (schema-first)
- reproducible (evidence + logs)
- auditable (explicit scope via pins)

---

## 1) Task Input Schema

### Canonical JSON shape

```json
{
  "task_id": "uuid",
  "goal": "string — natural language task description",
  "role": "string — role name",
  "pins": {
    "allowed_paths": ["string[]"],
    "forbidden_paths": ["string[]"]
  },
  "files": ["string[] — files the agent is expected to touch"],
  "context": {
    "map": "object — repository structure map",
    "docs": "object — relevant documentation references",
    "history": "object — task history"
  }
}
```

### Field semantics

- `task_id` (required): Stable UUID for correlating all artifacts.
- `goal` (required): What the agent should accomplish (human readable).
- `role` (required): Execution policy profile (e.g., "executor", "reviewer").
- `pins` (required): Scope guardrails.
  - `allowed_paths`: The only paths the agent may read/write.
  - `forbidden_paths`: Paths explicitly disallowed even if they match `allowed_paths`.
- `files` (optional): A hint list of expected file touches; used for preflight and review.
- `context` (optional): Structured helper data.
  - `map`: A precomputed repo map (when available).
  - `docs`: Links/IDs to internal docs or prior decisions.
  - `history`: Prior attempts, failures, or important constraints.

### Validation rules (recommended)

- `task_id` MUST be a UUID string.
- `pins.allowed_paths` MUST be non-empty.
- No path MAY appear in both `allowed_paths` and `forbidden_paths`.
- If `files` is present, every entry SHOULD be within `pins.allowed_paths`.

### Example

```json
{
  "task_id": "72c84e9c-0975-4c1a-b9a5-864c2725dc8a",
  "goal": "Create IO layer documentation for schemas, fail codes, and evidence.",
  "role": "executor",
  "pins": {
    "allowed_paths": ["docs/prompt_os/io/"],
    "forbidden_paths": []
  },
  "files": [
    "docs/prompt_os/io/schemas.md",
    "docs/prompt_os/io/fail_codes.md",
    "docs/prompt_os/io/evidence_spec.md"
  },
  "context": {
    "map": {},
    "docs": {},
    "history": {}
  }
}
```

---

## 2) Task Output Schema (`submit.json`)

The executor MUST emit a `submit.json` that can be validated without reading free-form text.

### Canonical JSON shape

```json
{
  "schema_version": "scc.submit.v1",
  "task_id": "string",
  "status": "DONE | NEED_INPUT | FAILED",
  "reason_code": "string (optional)",
  "changed_files": ["string[]"],
  "new_files": ["string[]"],
  "tests": {
    "commands": ["string[]"],
    "passed": "boolean",
    "summary": "string"
  },
  "artifacts": {
    "report_md": "path",
    "selftest_log": "path",
    "evidence_dir": "path",
    "patch_diff": "path",
    "submit_json": "path"
  },
  "exit_code": "integer",
  "needs_input": ["string[]"]
}
```

### Field semantics

- `schema_version` (required): Output contract identifier. MUST be `scc.submit.v1`.
- `task_id` (required): Must match the input `task_id`.
- `status` (required):
  - `DONE`: Work completed successfully.
  - `NEED_INPUT`: Blocked; requires user/system input to proceed.
  - `FAILED`: Attempt completed but unsuccessful.
- `reason_code` (optional): Machine-actionable failure reason (see `fail_codes.md`).
- `changed_files` / `new_files` (required): Paths changed/created **within the allowed scope**.
- `tests` (required): What was executed and the outcome.
  - `commands`: A list of commands (strings) intended to be runnable by the gateway.
  - `passed`: Boolean test verdict.
  - `summary`: Human readable summary.
- `artifacts` (required): Paths to evidence files produced for this task.
- `exit_code` (required): Integer exit code representing overall executor status.
- `needs_input` (required): List of concrete questions/requests when `status=NEED_INPUT`.

### Validation rules (recommended)

- `status=DONE` implies `exit_code=0`.
- If `tests.passed=false`, `status` SHOULD be `FAILED` and `reason_code` SHOULD be `CI_FAILED`.
- Every path in `changed_files` and `new_files` MUST be under `pins.allowed_paths` and not under `pins.forbidden_paths`.
- All `artifacts.*` paths MUST exist and be readable by the gateway.

---

## 3) Verdict Schema (system evaluation result)

After the gateway validates artifacts and policies, it may produce a *verdict object*.

### Canonical JSON shape

```json
{
  "schema_version": "scc.verdict.v1",
  "task_id": "string",
  "verdict": "PASS | FAIL",
  "reason_code": "string (optional)",
  "messages": ["string[]"],
  "checks": {
    "schema_valid": "boolean",
    "scope_valid": "boolean",
    "tests_passed": "boolean",
    "evidence_present": "boolean"
  },
  "timestamps": {
    "submitted_at": "RFC3339 string",
    "evaluated_at": "RFC3339 string"
  },
  "links": {
    "submit_json": "path",
    "report_md": "path",
    "selftest_log": "path",
    "patch_diff": "path",
    "evidence_dir": "path"
  }
}
```

### Notes

- `reason_code` SHOULD map to a code in `docs/prompt_os/io/fail_codes.md`.
- `checks` allows dashboards to show *what failed* without parsing free text.



---



### 8.2.4 证据规范（Evidence Specification）

> **来源**: `docs/prompt_os/io/evidence_spec.md`

证据产物用于支持可复现、可审计的任务执行：

1. **可复现性**: 其他系统（或人类）能理解发生了什么变更、如何验证的
2. **裁决依据**: 网关能以最小歧义判定 PASS/FAIL

---

## 1) Evidence Types

The following evidence items are standard.

- `patch.diff`: A git-style unified diff representing the repo change.
- `selftest.log`: Full log of self-tests executed (or the test plan if tests are deferred to gateway policy).
- `report.md`: Human-readable execution report (rationale, decisions, changed files).
- `submit.json`: Machine-readable submission object as defined in `schemas.md`.
- `screenshots/` (optional): Any screenshot evidence; only if relevant and allowed.

---

## 2) Evidence Directory Structure

Recommended structure (task-scoped directory):

```
artifacts/
├── report.md
├── selftest.log
├── evidence/
│   ├── patch.diff
│   ├── pre_state.json
│   └── post_state.json
├── patch.diff
└── submit.json
```

Notes:

- Keeping a copy of `patch.diff` at both `artifacts/patch.diff` and `artifacts/evidence/patch.diff` makes it easy for tools that expect either location.
- `pre_state.json` and `post_state.json` SHOULD capture minimal state needed to compare before/after (e.g., file list, sizes, hashes).

---

## 3) Evidence Retention Policy

Retention SHOULD balance auditability with storage cost.

Recommended baseline:

- Keep task evidence for **30 days** for routine tasks.
- Keep evidence for **90–180 days** for high-impact releases, security changes, or incident response.
- Allow **manual pinning** of evidence for long-term retention when required by compliance.

Deletion policy:

- Expired evidence MAY be deleted automatically.
- Deletion MUST preserve privacy constraints (e.g., redact secrets before long-term retention).

---

## 4) Evidence Validation Rules

The gateway (or a local preflight) SHOULD validate evidence using the rules below.

### `patch.diff`

- MUST be parseable as a unified diff.
- SHOULD include all repo changes reflected in `changed_files` and `new_files`.
- MUST NOT include changes outside pinned scope.

### `selftest.log`

- MUST be present.
- MUST include the exact commands intended/executed.
- MUST end with a terminal line like: `EXIT_CODE=<int>`.
- SHOULD include timestamps and working directory context.

### `report.md`

- MUST be present.
- MUST list: goal summary, key decisions, and changed/new files.
- SHOULD call out any deviations (e.g., tests deferred to gateway).

### `submit.json`

- MUST validate against the Task Output Schema in `schemas.md`.
- `changed_files` and `new_files` MUST match actual repo diff scope.
- `tests.commands` MUST be an array of strings; each string SHOULD be runnable by the gateway.

### `screenshots/` (optional)

- MUST contain only task-relevant images.
- MUST avoid secrets/credentials.



---



#### 证据类型

| 证据类型 | 说明 | 存储位置 |
|----------|------|----------|
| 执行日志 | 命令执行输出 | artifacts/scc_tasks/{task_id}/logs/ |
| 代码diff | 代码变更diff | artifacts/scc_tasks/{task_id}/diff/ |
| 测试报告 | 测试结果 | artifacts/scc_tasks/{task_id}/reports/ |
| 指标数据 | 性能/覆盖率指标 | artifacts/scc_tasks/{task_id}/metrics/ |
| 截图 | UI变更截图 | artifacts/scc_tasks/{task_id}/screenshots/ |

---

## 8.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 证据收集 | 收集执行证据 | `evidence_collector.py` | `evidence_collector.py --task-id TASK-001 --all` |
| 裁决判定 | 基于acceptance判定 | `verdict_engine.py` | `verdict_engine.py --contract contract.json --evidence-dir evidence/` |
| 证据查询 | 查询证据 | `evidence_query.py` | `evidence_query.py --task-id TASK-001` |
| 故障分类 | 分类失败原因 | `fail_classifier.py` | `fail_classifier.py --logs logs/ --diff diff/` |
| 证据验证 | 验证证据完整性 | `evidence_validator.py` | `evidence_validator.py --evidence-dir evidence/` |

---

## 8.4 脚本使用示例

```bash
# 1. 收集所有执行证据
python tools/scc/ops/evidence_collector.py \
  --task-id TASK-001 \
  --all \
  --output artifacts/scc_tasks/TASK-001/evidence/

# 2. 运行裁决判定
python tools/scc/ops/verdict_engine.py \
  --contract contracts/task_001.json \
  --evidence-dir artifacts/scc_tasks/TASK-001/evidence/ \
  --output verdict.json

# 3. 查询任务证据
python tools/scc/ops/evidence_query.py \
  --task-id TASK-001 \
  --type logs \
  --format json

# 4. 分类失败原因
python tools/scc/ops/fail_classifier.py \
  --logs artifacts/scc_tasks/TASK-001/logs/ \
  --diff artifacts/scc_tasks/TASK-001/diff/ \
  --output fail_classification.json

# 5. 验证证据完整性
python tools/scc/ops/evidence_validator.py \
  --evidence-dir artifacts/scc_tasks/TASK-001/evidence/ \
  --contract contracts/task_001.json
```

---

## 8.5 关键文件针脚

```yaml
L8_evidence_layer:
  ssot_partition: "07_reports_evidence"
  chapter: 11
  description: "证据与裁决层 - 提供证据收集、裁决判定、故障分类"
  
  core_spec_files:
    - path: scc-top/docs/ssot/04_contracts/contract_min_spec.md
      oid: 01891D2ED9EDD141F7A88297698B
      description: "契约规范，定义acceptance和verdict"
    - path: scc-top/docs/ssot/05_runbooks/execution_verification_interfaces.md
      oid: 0134F186F18A844FCCB01634A0C2
      description: "执行与验证接口，定义verifier输出"
  
  tools:
    - path: tools/scc/ops/evidence_collector.py
      oid: 018A54E990922545E6B5415AA533
    - path: tools/scc/ops/verdict_engine.py
      oid: 01F55EF61C7F8044B9B3E6A84EE2
    - path: tools/scc/ops/evidence_query.py
      oid: 01BBFE5E1D93E64EA1BE5DE79F7D
    - path: tools/scc/ops/fail_classifier.py
      oid: 013BD0E493BDD44576A433834041
    - path: tools/scc/ops/evidence_validator.py
      oid: 0118A16A013C8243ECB18FA8C994
  
  related_chapters:
    - chapter: technical_manual/chapter_11_evidence_layer.md
      oid: 015563A46583EC4885BEA4A2020A
```

---

## 8.6 本章小结

### 8.6.1 核心概念

| 概念 | 说明 |
|------|------|
| 裁决 | 基于acceptance判定pass/fail |
| 故障分类 | 结构化的fail_class（timeout, test_failure等） |
| 证据 | 执行日志、diff、报告、指标等 |
| 故障关闭 | 无法验证时必须判定为fail |

### 8.6.2 依赖关系

```
L8 证据与裁决层
    │
    ├─ 依赖 → L2任务层（契约定义acceptance）
    ├─ 依赖 → L6Agent层（执行产生证据）
    │
    ├─ 提供裁决给 → L14 质量层
    └─ 提供证据给 → L16 观测层
```

---


---

**导航**: [← L7](./L7_tool_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L9](./L9_state_layer.md)