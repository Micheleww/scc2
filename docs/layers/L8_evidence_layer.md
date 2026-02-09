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

IO层的设计目标：
- **机器可验证**（schema-first）
- **可复现**（证据 + 日志）
- **可审计**（通过pins明确范围）

---

### 1) 任务输入Schema（Task Input）

#### 标准JSON结构

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

#### 字段说明

- `task_id`（必需）: 稳定UUID，用于关联所有产物
- `goal`（必需）: Agent需要完成的任务（自然语言）
- `role`（必需）: 执行策略配置文件（如"executor"、"reviewer"）
- `pins`（必需）: 范围护栏
  - `allowed_paths`: Agent可读写的唯一路径列表
  - `forbidden_paths`: 即使匹配allowed_paths也明确禁止的路径
- `files`（可选）: 预期文件触碰列表，用于预检和审查
- `context`（可选）: 结构化辅助数据
  - `map`: 预计算的仓库结构图
  - `docs`: 内部文档链接/ID
  - `history`: 历史尝试、失败记录

#### 验证规则

- `task_id` 必须是UUID字符串
- `pins.allowed_paths` 不得为空
- 同一路径不得同时出现在 `allowed_paths` 和 `forbidden_paths` 中
- 如果提供了 `files`，每项都应在 `pins.allowed_paths` 范围内

#### 示例

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

### 2) 任务输出Schema（submit.json）

执行器必须输出一个 `submit.json`，可在不读取自由文本的情况下进行验证。

#### 标准JSON结构

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

#### 字段说明

- `schema_version`（必需）: 输出契约标识符，必须是 `scc.submit.v1`
- `task_id`（必需）: 必须与输入的 `task_id` 一致
- `status`（必需）:
  - `DONE`: 工作成功完成
  - `NEED_INPUT`: 被阻塞，需要用户/系统输入
  - `FAILED`: 尝试完成但未成功
- `reason_code`（可选）: 机器可执行的失败原因（参见失败代码目录）
- `changed_files` / `new_files`（必需）: 在允许范围内变更/创建的路径
- `tests`（必需）: 执行了什么测试及其结果
  - `commands`: 可由网关运行的命令列表
  - `passed`: 布尔测试结果
  - `summary`: 人类可读摘要
- `artifacts`（必需）: 该任务产生的证据文件路径
- `exit_code`（必需）: 整数退出码
- `needs_input`（必需）: `status=NEED_INPUT` 时的具体问题/请求列表

#### 验证规则

- `status=DONE` 意味着 `exit_code=0`
- 如果 `tests.passed=false`，`status` 应为 `FAILED`，`reason_code` 应为 `CI_FAILED`
- `changed_files` 和 `new_files` 中的每个路径必须在 `pins.allowed_paths` 范围内
- 所有 `artifacts.*` 路径必须存在且可被网关读取

---

### 3) 裁决Schema（Verdict）

网关验证产物和策略后，会产生一个 *裁决对象*。

#### 标准JSON结构

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

#### 说明

- `reason_code` 应映射到 `docs/prompt_os/io/fail_codes.md` 中的代码
- `checks` 允许仪表板在不解析自由文本的情况下展示 *什么失败了*



---



### 8.2.4 证据规范（Evidence Specification）

> **来源**: `docs/prompt_os/io/evidence_spec.md`

证据产物用于支持可复现、可审计的任务执行：

1. **可复现性**: 其他系统（或人类）能理解发生了什么变更、如何验证的
2. **裁决依据**: 网关能以最小歧义判定 PASS/FAIL

---

#### 1) 证据类型

以下证据项目为标准配置：

- `patch.diff`: Git风格的统一diff，表示仓库变更
- `selftest.log`: 自测执行完整日志（或延迟到网关策略时的测试计划）
- `report.md`: 人类可读的执行报告（依据、决策、变更文件）
- `submit.json`: 机器可读的提交对象（定义见上方Schema）
- `screenshots/`（可选）: 截图证据，仅在相关且允许时使用

---

#### 2) 证据目录结构

推荐结构（按任务隔离）：

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

说明：
- 在 `artifacts/patch.diff` 和 `artifacts/evidence/patch.diff` 两处保留副本，方便不同工具读取
- `pre_state.json` 和 `post_state.json` 应捕获最小状态用于前后对比（文件列表、大小、哈希）

---

#### 3) 证据保留策略

保留策略需平衡可审计性与存储成本：

- 常规任务证据保留 **30天**
- 高影响发布、安全变更、事件响应保留 **90-180天**
- 合规要求时允许**手动固定**长期保留

删除策略：
- 过期证据可自动删除
- 删除前必须遵守隐私约束（如编辑密钥后再长期保留）

---

#### 4) 证据验证规则

网关（或本地预检）应按以下规则验证证据：

**`patch.diff`**:
- 必须可解析为统一diff格式
- 应包含 `changed_files` 和 `new_files` 中的所有仓库变更
- 不得包含pins范围外的变更

**`selftest.log`**:
- 必须存在
- 必须包含精确的执行命令
- 必须以终端行结束：`EXIT_CODE=<int>`
- 应包含时间戳和工作目录上下文

**`report.md`**:
- 必须存在
- 必须列出：目标摘要、关键决策、变更/新增文件
- 应注明任何偏差（如测试延迟到网关执行）

**`submit.json`**:
- 必须通过任务输出Schema验证
- `changed_files` 和 `new_files` 必须与实际仓库diff范围一致
- `tests.commands` 必须是字符串数组，每项应可由网关运行

**`screenshots/`**（可选）:
- 只能包含与任务相关的图片
- 不得包含密钥/凭据



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
      description: "契约规范，定义acceptance和verdict"
    - path: scc-top/docs/ssot/05_runbooks/execution_verification_interfaces.md
      description: "执行与验证接口，定义verifier输出"
  
  tools:
    - tools/scc/ops/evidence_collector.py
    - tools/scc/ops/verdict_engine.py
    - tools/scc/ops/evidence_query.py
    - tools/scc/ops/fail_classifier.py
    - tools/scc/ops/evidence_validator.py
  
  related_chapters:
    - technical_manual/chapter_11_evidence_layer.md
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