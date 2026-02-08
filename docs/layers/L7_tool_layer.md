# L7 工具层

> **对应SSOT分区**: `05_runbooks/`（操作手册）  
> **对应技术手册**: 第15章  
> **层定位**: 工具定义、工具执行、工具发现

---

## 7.1 层定位与职责

### 7.1.1 核心职责

L7是SCC架构的**工具管理层**，为全系统提供：

1. **工具注册** - 工具元数据管理和索引
2. **工具执行** - 标准化工具调用接口
3. **工具发现** - 按类别/标签搜索工具
4. **技能守卫** - 工具调用门禁检查（skill_call_guard）
5. **证据生成** - 工具执行的证据收集

### 7.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L7 工具层                                     │
│ ├─ 工具注册（元数据管理）                     │
│ ├─ 工具执行（标准化调用）                     │
│ ├─ 工具发现（搜索/分类）                      │
│ └─ 技能守卫（门禁检查）                       │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L6 Agent层, L13 安全层                       │
└─────────────────────────────────────────────┘
```

---

## 7.2 来自05_runbooks/的核心内容

### 7.2.1 执行与验证接口

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/05_runbooks/execution_verification_interfaces.md` | 执行与验证接口 | 执行接口、验证接口、门禁规则 |
| `ssot/05_runbooks/SCC_RUNBOOK__v0.1.0.md` | SCC运行手册 | 执行状态机、重试策略、DLQ规则 |

#### 执行接口（Executor）

```yaml
执行接口规范:
  输入: Contract (task_id + scope_allow + acceptance)
  输出: Workspace diff/patch + Evidence paths
  禁止:
    - 不扩范围
    - 不改入口
    - 不碰未allowlisted文件
  必须: 产生证据路径（由contract outputs_expected指定）
```

#### 验证接口（Verifier）

```yaml
验证接口规范:
  输入: 工作空间 + 验收标准
  输出: verdict(pass/fail + fail_class) + 证据
  禁止: 不改代码/文档（除了写报告/证据）
  规则: 只认测试/验证器输出，故障关闭
```

### 7.2.2 技能守卫（Skill Call Guard）

#### 门禁规则

```
- 任何声称DONE的任务必须能通过适当的guard(s)验证
- 对于基于TaskCode的CI流，guard是: tools/ci/skill_call_guard.py
- 任何任务达到SUBMIT必须通过适用的guard(s)
- 技能/工具使用必须通过工件和/或结构化日志可审计
```

#### 最小技能集（v0.1.0）

| 技能 | 说明 | 使用角色 |
|------|------|----------|
| `SHELL_READONLY` | 检查仓库（rg/cat/ls）；无写入 | router, auditor |
| `SHELL_WRITE` | 在允许的workspace roots内写入 | executor |
| `PATCH_APPLY` | 应用代码/文档补丁 | executor |
| `SELFTEST` | 运行验收命令/测试 | verifier |
| `DOCFLOW_AUDIT` | 运行docflow审计并在artifacts下写报告 | auditor |
| `REVIEW_JOB` | 生成progress + feedback + metrics | auditor, factory_manager |

---

### 7.2.3 Manager Tools（组长验收工具）

#### 委派审计工具

| 工具 | 说明 | 命令示例 |
|------|------|----------|
| `delegation_audit.py` | 汇总CodexCLI批次改动 | `python tools/scc/ops/delegation_audit.py --automation-run-id <run_id>` |
| `leader_board.py` | 队长信息板（瀑布流汇总+错误码+token） | `python tools/scc/ops/leader_board.py` |

#### OID管理工具

| 工具 | 说明 | 命令示例 |
|------|------|----------|
| `oid_registry_bootstrap.ps1/py` | 把SSOT canonical的inline OID导入Postgres | `powershell -File tools/scc/ops/oid_registry_bootstrap.ps1` |
| `oid_generator.py` | 唯一发号 | `python tools/scc/ops/oid_generator.py new --path <path> --kind md --layer DOCOPS` |
| `oid_mint_placeholders.py` | 批量替换占位符 | `python tools/scc/ops/oid_mint_placeholders.py --apply` |
| `oid_validator.ps1/py` | Postgres权威校验，fail-closed | `powershell -File tools/scc/ops/oid_validator.ps1 -ReportDir <dir>` |
| `pg_oid_18777_start.ps1` | 启动OID Postgres（本地18777） | `powershell -File tools/scc/ops/pg_oid_18777_start.ps1` |
| `pg_oid_18777_stop.ps1` | 停止OID Postgres | `powershell -File tools/scc/ops/pg_oid_18777_stop.ps1` |

#### 任务管理工具

| 工具 | 说明 | 命令示例 |
|------|------|----------|
| `dispatch_from_task_tree.py` | 从任务树生成安全派发配置 | `python tools/scc/ops/dispatch_from_task_tree.py --taskcode <TaskCode> --limit 5` |
| `sync_task_tree_to_scc_tasks.py` | task_tree → artifacts/scc_tasks | `python tools/scc/ops/sync_task_tree_to_scc_tasks.py --only-missing --emit-report` |
| `backfill_task_tree_from_scc_tasks.py` | artifacts/scc_tasks → task_tree | `python tools/scc/ops/backfill_task_tree_from_scc_tasks.py --only-with-verdict` |
| `review_job_run.py` | progress+feedback+metrics+verdict gate | `python tools/scc/ops/review_job_run.py --taskcode REVIEW_JOB_V010 --run-mvm` |
| `taskcode_verify.ps1` | 技能调用/三件套门禁 | `powershell -File tools/scc/ops/taskcode_verify.ps1 -TaskCode <TaskCode> -Area <area>` |

#### 范围与调度工具

| 工具 | 说明 | 命令示例 |
|------|------|----------|
| `scope_gate` | 批量派发建议用configs/scc/*.json | 在parent中指定`allowed_globs[]`+`isolate_worktree: true` |
| `dispatch_watchdog.py` | 监控并自动终止卡住的CLI | `python tools/scc/ops/dispatch_watchdog.py --base http://127.0.0.1:18788 --poll-s 60` |
| `deterministic_snippet_pack.py` | 确定性抽取上下文，减少token | `python tools/scc/ops/deterministic_snippet_pack.py --allowed-glob <glob> --task-text "<task>" --json` |
| `ssot_search.py` | 基于registry.json选取权威上下文 | `python tools/scc/ops/ssot_search.py --task-text "<task>" --limit 12` |
| `dispatch_task.py` | RoleSpec路由+安全config生成 | `python tools/scc/ops/dispatch_task.py --goal "<goal>" --parents-file <parents.json>` |
| `dispatch_with_watchdog.ps1` | watchdog+批量派发一键 | `powershell -File tools/scc/ops/dispatch_with_watchdog.ps1 -Config <config.json> -Model gpt-5.2` |

#### 验证工具

| 工具 | 说明 | 命令示例 |
|------|------|----------|
| `top_validator.ps1/py` | Top/SSOT最小闭环校验 | `powershell -File tools/scc/ops/top_validator.ps1` |

### 7.2.4 工具目录详情

### 7.2.5 工具使用策略

# Tool Usage Policy

## Table of Contents

- [Overview](#overview)
- [1. Default Deny](#1-default-deny)
- [2. Explicit Deny Override](#2-explicit-deny-override)
- [3. Risk-based Approval](#3-risk-based-approval)
- [4. Audit Trail](#4-audit-trail)
- [Operational Notes](#operational-notes)

## Overview

This policy defines how an agent decides whether a tool may be used, based on role policy, explicit denies, and risk level.

## 1. Default Deny

- If a tool is **not** listed in `role.policy.tools.allow`, it is **forbidden**.
- “Not listed” includes unknown tools, aliases, or tools whose names do not match exactly.
- When uncertain, the agent must stop and request clarification or updated policy.

## 2. Explicit Deny Override

- Tools listed in `role.policy.tools.deny` are **absolutely forbidden**.
- Deny overrides allow: if a tool is in both `allow` and `deny`, the effective decision is **deny**.

## 3. Risk-based Approval

Risk level controls the required gating before a tool call.

### LOW (Auto-allow)

- Allowed when present in `allow` and not present in `deny`.
- Minimal preflight: confirm scope and target paths.

### MEDIUM (Preflight required)

- Requires a preflight checklist to pass before execution.
- Preflight must include:
  - Intent: what the command will do.
  - Scope: which files/paths are impacted.
  - Safety: why it is not destructive and how to roll back.
  - Determinism: no hidden downloads or remote code execution.

### HIGH (Human approval or special role)

- Requires explicit human approval **or** a privileged role with documented authorization.
- Must include an execution plan and an audit record.
- Must be narrowly scoped; broad or destructive operations are not allowed by default.

## 4. Audit Trail

- Every tool invocation must be recorded as evidence.
- The audit record should include:
  - Timestamp
  - Tool name and risk level
  - Parameters (redacted as needed)
  - Result (success/failure)
  - Files changed (if any)

### 7.2.6 API规则

#### 速率限制
- 强制执行每个密钥和每个角色的限制（每分钟请求数和每分钟token数）
- 在429/503响应上应用自适应节流
- 使用共享限制器防止跨worker的"惊群效应"

#### 重试策略
- 仅在瞬态故障上重试（例如超时、429、502、503、504）
- 使用指数退避和抖动
- 将重试限制为少量有界次数（例如2-5次尝试）以避免失控成本
- 永远不要重试非幂等操作，除非API明确支持

#### 回退链
- 定义主模型/服务和有序回退列表
- 仅在以下情况下回退：
  - 主服务不可用（超时/5xx），或
  - 主服务速率限制超过阈值，或
  - 响应验证失败
- 在回退期间保留安全和策略约束（不要"回退到"较不安全的配置）

#### Token核算
- 跟踪：每次调用的提示token、完成token和总token
- 每次运行和每个用户的预算消耗
- 将预算遥测发送到证据/审计日志（仅数字；无PII）
- 当预算超出时，降级功能或拒绝并显示明确错误

#### 响应验证
- 针对预期模式验证响应（JSON模式/正则表达式/结构检查）
- 拒绝以下响应：
  - 无法解析
  - 超出大小/token限制
  - 包含策略禁止的内容
- 验证失败时，要么：
  - 使用约束提示请求更正的响应，或
  - 触发回退

### 7.2.7 数据规则

#### 数据分类

在读取/写入之前对所有数据（输入、中间产物、输出）进行分类：

- **Public**: 可广泛安全地读取/写入
- **Internal**: 仅内部角色可访问；不要对外发布
- **Confidential**: 位于 `secrets/**` 下或以其他方式标记为机密；**任何角色都不得访问**

#### 数据流规则

- 数据仅在明确清理时才能从**较高敏感度流向较低敏感度**
- 禁止的流：
  - Internal → Public 未经清理
  - Confidential → 任何其他分类
- 生成派生产物（报告、证据）时，确保它们不嵌入受限内容

#### PII处理

- 日志不得包含PII
- 如果报告需要引用用户标识符，请对其进行编辑或标记化
- 如果文档需要示例，请使用合成数据

## Operational Notes

- Prefer the least-privileged tool that can accomplish the goal.
- Never exfiltrate secrets/PII via `network` or logs.
- For filesystem tools, pins/allowlists are enforcement boundaries; they are not “recommendations”.


---



#### 文件操作工具

| 工具 | 说明 | 输入 | 输出 | 成本 | 失败模式 |
|------|------|------|------|------|----------|
| `read_file` | 读取文件内容 | path, offset, limit | content, lines, size | ~10 tokens | FILE_NOT_FOUND, PERMISSION_DENIED, PATH_OUTSIDE_ALLOWLIST |
| `write_file` | 写入文件内容 | path, content, append | bytes_written, checksum | low | PATH_OUTSIDE_ALLOWLIST, DISK_FULL, PERMISSION_DENIED |
| `glob` | 文件模式匹配 | pattern, path | files[] | low | - |
| `ls` | 列出目录 | path | entries[] | low | PATH_NOT_FOUND |

#### 搜索工具

| 工具 | 说明 | 输入 | 输出 | 成本 | 失败模式 |
|------|------|------|------|------|----------|
| `grep` | 内容搜索 | pattern, path, glob | matches[] | medium | - |
| `search_codebase` | 语义搜索 | query, target_dirs | snippets[] | high | - |

#### 执行工具

| 工具 | 说明 | 输入 | 输出 | 成本 | 失败模式 |
|------|------|------|------|------|----------|
| `run_command` | 执行命令 | command, cwd, blocking | stdout, stderr, exit_code | variable | COMMAND_NOT_FOUND, TIMEOUT, PERMISSION_DENIED |
| `web_search` | 网络搜索 | query, num | results[] | high | - |
| `web_fetch` | 获取网页 | url | content | medium | - |

#### 编辑工具

| 工具 | 说明 | 输入 | 输出 | 成本 | 失败模式 |
|------|------|------|------|------|----------|
| `search_replace` | 搜索替换 | file_path, old_str, new_str | - | low | FILE_NOT_FOUND, NO_MATCH |
| `write` | 写入文件 | file_path, content | - | low | PATH_OUTSIDE_ALLOWLIST |
| `delete_file` | 删除文件 | file_paths[] | - | low | FILE_NOT_FOUND, PERMISSION_DENIED |

#### Windows脚本策略备注

当PowerShell脚本策略禁用时，使用Python版本：
- `python tools/scc/ops/top_validator.py --registry docs/ssot/registry.json`
- `python tools/scc/ops/oid_validator.py --report-dir docs/REPORT/<area>/artifacts/<TaskCode>`

---

## 7.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 工具注册 | 注册新工具 | `tool_registry.py` | `tool_registry.py register --name git_diff --path tools/git/diff.py` |
| 工具执行 | 执行工具 | `tool_runner.py` | `tool_runner.py --tool git_diff --args '{"files": ["*.py"]}'` |
| 工具发现 | 搜索工具 | `tool_discovery.py` | `tool_discovery.py --category ops --tag "file-ops"` |
| 技能守卫 | 验证技能调用 | `skill_call_guard.py` | `skill_call_guard.py --task-code TASK-001 --skill SHELL_WRITE` |
| 证据收集 | 收集工具执行证据 | `tool_evidence.py` | `tool_evidence.py --execution-id EXEC-001` |

---

## 7.4 脚本使用示例

```bash
# 1. 注册新工具
python tools/scc/ops/tool_registry.py register \
  --name git_diff \
  --path tools/git/diff.py \
  --category git \
  --tags '["version-control", "diff"]' \
  --description "Generate git diff for changed files"

# 2. 执行工具
python tools/scc/ops/tool_runner.py \
  --tool git_diff \
  --args '{"files": ["*.py"], "cached": true}' \
  --capture-output \
  --save-evidence

# 3. 发现工具
python tools/scc/ops/tool_discovery.py \
  --category ops \
  --tag "file-ops" \
  --format table

# 4. 验证技能调用（CI门）
python tools/ci/skill_call_guard.py \
  --task-code TASK-001 \
  --skill SHELL_WRITE \
  --scope-allow '["src/*", "tests/*"]' \
  --actual-paths '["src/main.py", "src/utils.py"]' \
  --fail-closed

# 5. 收集工具执行证据
python tools/scc/ops/tool_evidence.py \
  --execution-id EXEC-001 \
  --include-logs \
  --include-output \
  --output artifacts/scc_tasks/TASK-001/tool_evidence/
```

---

## 7.5 关键文件针脚

```yaml
L7_tool_layer:
  ssot_partition: "05_runbooks"
  chapter: 15
  description: "工具层 - 提供工具注册、执行、发现、技能守卫"
  
  core_spec_files:
    - path: scc-top/docs/ssot/05_runbooks/execution_verification_interfaces.md
      oid: 01KGDT0H7TXA8XY6TDRXAZ9N1J
      layer: CANON
      primary_unit: X.DISPATCH
      description: "执行与验证接口规范"
    - path: scc-top/docs/ssot/05_runbooks/SCC_RUNBOOK__v0.1.0.md
      description: "SCC运行手册，包含执行状态机"
    - path: scc-top/docs/ssot/03_agent_playbook/SKILL_SPEC__v0.1.0.md
      description: "技能规范，定义最小技能集"
  
  tools:
    - tools/scc/ops/tool_registry.py
    - tools/scc/ops/tool_runner.py
    - tools/scc/ops/tool_discovery.py
    - tools/ci/skill_call_guard.py
    - tools/scc/ops/tool_evidence.py
  
  related_chapters:
    - technical_manual/chapter_15_tool_layer.md
```

---

## 7.6 本章小结

### 7.6.1 核心概念

| 概念 | 说明 |
|------|------|
| 执行接口 | Executor的输入输出规范 |
| 验证接口 | Verifier的输入输出规范 |
| 技能守卫 | 验证技能调用合规性的门禁 |
| 最小技能集 | 6个核心技能（SHELL_READONLY, SHELL_WRITE等） |

### 7.6.2 依赖关系

```
L7 工具层
    │
    ├─ 依赖 → L4提示词层（技能规范）
    ├─ 依赖 → L6Agent层（执行需求）
    │
    ├─ 提供工具给 → L6 Agent层
    └─ 提供守卫给 → L13 安全层
```

---


---

**导航**: [← L6](./L6_agent_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L8](./L8_evidence_layer.md)