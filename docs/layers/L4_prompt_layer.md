# L4 提示词层

> **对应SSOT分区**: `03_agent_playbook/`（Agent说明书）  
> **对应技术手册**: 第9章  
> **层定位**: 提示词模板、角色定义、技能规范、交接模板

---

## 4.1 层定位与职责

### 4.1.1 核心职责

L4是SCC架构的**提示词与角色管理层**，为全系统提供：

1. **角色定义** - 9个核心Agent角色的职责、输入输出、禁止事项
2. **技能规范** - 最小技能分类和门禁规则
3. **能力目录** - Agent可调用的能力清单
4. **交接模板** - 角色间"文档即接口"的标准化模板
5. **路由契约** - 确定性任务到角色的分配规则

### 4.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L4 提示词层                                   │
│ ├─ 角色定义（9个核心角色）                    │
│ ├─ 技能规范（最小技能集）                     │
│ ├─ 能力目录（可调用的能力）                   │
│ ├─ 交接模板（文档即接口）                     │
│ └─ 路由契约（确定性分配）                     │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L6 Agent层, L11 路由层, L13 安全层           │
└─────────────────────────────────────────────┘
```

---

## 4.2 来自03_agent_playbook/的核心内容

### 4.2.1 角色规范（RoleSpec）

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/03_agent_playbook/ROLE_SPEC__v0.1.0.md` | 角色规范定义 | 9个最小角色、路由契约、门禁规则 |
| `ssot/03_agent_playbook/roles/index.md` | 角色包索引 | 所有角色的入口 |

#### 9个最小角色定义

| 角色 | 职责 | 禁止事项 | 输入 | 输出 |
|------|------|----------|------|------|
| `router` | 分配角色和执行模式 | 不得编辑代码/文档 | 任务描述+元数据 | role_id + reason + required_skills[] |
| `planner` | 仅生成契约/计划 | 不得执行或编辑 | 目标+约束 | 契约草案 |
| `chief_designer` | 生成架构蓝图/ADR草案 | 不得调度执行 | 需求+约束 | 蓝图/ADR |
| `team_lead` | 拆分工作为任务图/契约；调度团队 | 监督并停止卡住的任务 | 能力订单 | 任务图+契约 |
| `executor` | 在允许范围内做最小改动 | 不扩范围；不改入口；不碰未allowlisted文件 | 契约(task_id + scope_allow + acceptance) | Workspace diff/patch + Evidence paths |
| `verifier` | 只执行acceptance，产出verdict | 不改代码/文档（除报告/证据） | 工作空间+验收标准 | verdict(pass/fail + fail_class) + 证据 |
| `auditor` | 检查不变量（SSOT入口、门禁、证据） | 不得编辑 | 规范+证据 | 审计报告 |
| `secretary` | 将原始聊天总结为派生笔记 | 不得直接更改规范 | 原始输入 | 派生笔记 |
| `factory_manager` | 优先、批准契约、调度 | 不得直接执行更改 | 待办事项+资源 | 调度决策 |

#### 角色包（Role Pack）结构

每个角色包包含：
- `ROLE.md` - 角色定义（Mission, Non-goals, Inputs, Outputs, Memory）
- `checklist.md` - 角色检查清单
- `handoff_templates/` - 该角色的交接模板

#### Executor角色包示例

```yaml
Role Pack: Executor (v0.1.0)
Mission: 在scope_allow内做最小必要改动，产出可验证证据
Non-goals (hard):
  - 不扩范围
  - 不改入口
  - 不碰未allowlisted文件
Inputs:
  - Contract (task_id + scope_allow + acceptance)
Outputs:
  - Workspace diff / patch
  - Evidence paths（由contract outputs_expected指定）
Memory: docs/INPUTS/role_memory/executor.md
Handoff templates: docs/ssot/03_agent_playbook/handoff_templates/index.md (Task Contract)
```

#### Verifier角色包示例

```yaml
Role Pack: Verifier (v0.1.0)
Mission: 只执行acceptance，产出verdict（pass/fail + fail_class）与证据
Non-goals (hard):
  - 不改代码/文档（除了写报告/证据）
Memory: docs/INPUTS/role_memory/verifier.md
Handoff templates: docs/ssot/03_agent_playbook/handoff_templates/index.md (Progress/Feedback via review job)
```

### 4.2.2 技能规范（SkillSpec）

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/03_agent_playbook/SKILL_SPEC__v0.1.0.md` | 技能规范定义 | 最小技能集、门禁规则、证据规则 |
| `ssot/03_agent_playbook/skill_spec.json` | 机器可读规范 | JSON格式技能定义 |

#### 门禁规则（规范）

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

#### 完整Skills目录（51个技能）

根据 `skills/registry.json`，SCC包含以下技能：

**核心开发技能**:
| 技能ID | 所属角色 | 说明 |
|--------|----------|------|
| `implementation` | engineer | 代码实现 |
| `patch_only` | engineer | 仅补丁修改 |
| `patch.apply_minimal` | executor | 最小化补丁应用 |
| `glue_code` | integrator | 胶水代码编写 |
| `interface_spec` | designer | 接口规范定义 |
| `min_diff` | integrator | 最小差异实现 |
| `acceptance_criteria` | designer | 验收标准定义 |

**任务管理技能**:
| 技能ID | 所属角色 | 说明 |
|--------|----------|------|
| `task_decomposition` | designer | 任务分解 |
| `taskgraph.compile` | planner | 任务图编译 |
| `taskgraph.atomicize` | split | 任务原子化 |
| `dispatch_planning` | factory_manager | 调度规划 |
| `queue_orchestration` | factory_manager | 队列编排 |
| `queue.partition` | factory_manager | 队列分区 |
| `routing.fallback` | factory_manager | 路由回退 |
| `retry.plan` | retry_orchestrator | 重试计划 |

**质量保障技能**:
| 技能ID | 所属角色 | 说明 |
|--------|----------|------|
| `tests.run_allowed` | executor | 运行允许的测试 |
| `smoke_tests` | qa | 冒烟测试 |
| `triage` | qa | 问题分类 |
| `evidence_check` | auditor | 证据检查 |
| `evidence.verify_triplet` | audit | 证据三元组验证 |
| `failure_triad` | auditor | 失败三元分析 |
| `log_review` | auditor | 日志审查 |
| `gap_analysis` | status_review | 差距分析 |
| `status_review` | status_review | 状态审查 |
| `status.summarize_events` | status_review | 事件汇总 |
| `risk.assess` | planner | 风险评估 |
| `bottleneck_analysis` | factory_manager | 瓶颈分析 |

**CI/CD技能**:
| 技能ID | 所属角色 | 说明 |
|--------|----------|------|
| `ci.fix_build` | ci_fixup | CI构建修复 |
| `ci.reproduce` | ci_fixup | CI问题复现 |
| `preflight.run` | preflight_gate | 预检运行 |
| `preflight.requirements_infer` | split | 需求推断 |

**数据与映射技能**:
| 技能ID | 所属角色 | 说明 |
|--------|----------|------|
| `map.build` | map_curator | 映射构建 |
| `map.sqlite.build` | map_curator | SQLite映射构建 |
| `map.query` | pins | 映射查询 |
| `pins_only` | pinser | Pins专用操作 |
| `pins.build_minimal` | pins | 最小Pins构建 |
| `scope_minimization` | pinser | 范围最小化 |
| `navigation` | doc | 导航文档 |

**治理与文档技能**:
| 技能ID | 所属角色 | 说明 |
|--------|----------|------|
| `adr.write_6line` | doc_adr_scribe | ADR六行写法 |
| `ssot.update_index` | ssot_curator | SSOT索引更新 |
| `ssot.sync_apply` | ssot_curator | SSOT同步应用 |
| `playbook.publish` | playbook_publisher | 手册发布 |
| `runbooks` | doc | 运行手册 |
| `lessons.mine` | lessons_miner | 经验挖掘 |

**发布与评估技能**:
| 技能ID | 所属角色 | 说明 |
|--------|----------|------|
| `pr.bundle_create` | release_integrator | PR包创建 |
| `replay.run_smoke` | eval_curator | 冒烟重放 |
| `eval.curate_manifest` | eval_curator | 评估清单管理 |
| `events.backfill` | auditor | 事件回填 |
| `stability.control` | stability_controller | 稳定性控制 |
| `policy.check_scope` | audit | 策略范围检查 |

> **完整注册表**: `skills/registry.json` 包含所有51个技能的定义和归属

#### 证据规则（规范）

```
规范文档不得嵌入大段证据；必须链接到：
- artifacts/...
- docs/INPUTS/...
```

### 4.2.3 能力目录（Capability Catalog）

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/03_agent_playbook/CAPABILITY_CATALOG__v0.1.0.md` | 能力目录 | 最小能力集 |
| `ssot/03_agent_playbook/capability_catalog.json` | 机器可读目录 | JSON格式能力定义 |

#### 最小能力集（v0.1.0）

| 能力 | 说明 | 调用者 |
|------|------|--------|
| `CAP_DOCFLOW_AUDIT` | 运行docflow审计 → 报告在artifacts/scc_state/ | auditor |
| `CAP_RAW_TO_TASKTREE` | 从WebGPT导出生成docs/DERIVED/task_tree.json | secretary |
| `CAP_REVIEW_JOB` | 写progress + feedback (raw-b) + metrics | auditor |
| `CAP_CODEX_DELEGATION` | 通过/executor/codex/run调度并行CodexCLI parents | factory_manager |
| `CAP_TASKCODE_GUARD` | 通过tools/ci/skill_call_guard.py验证TaskCode triplet | verifier |

### 4.2.4 交接模板（Handoff Templates）

#### 核心文件

| 文件路径 | 说明 | 用途 |
|----------|------|------|
| `ssot/03_agent_playbook/handoff_templates/index.md` | 模板索引 | 所有交接模板的入口 |
| `ssot/03_agent_playbook/handoff_templates/TASK_CONTRACT__TEMPLATE__v0.1.0.md` | 任务契约模板 | Team Lead → Crew |
| `ssot/03_agent_playbook/handoff_templates/BLUEPRINT__TEMPLATE__v0.1.0.md` | 蓝图模板 | Chief Designer → Factory |
| `ssot/03_agent_playbook/handoff_templates/GOAL_BRIEF__TEMPLATE__v0.1.0.md` | 目标简报模板 | Secretary → (Designer/Factory) |
| `ssot/03_agent_playbook/handoff_templates/CAPABILITY_ORDER__TEMPLATE__v0.1.0.md` | 能力订单模板 | Factory → Team Lead |
| `ssot/03_agent_playbook/handoff_templates/PROGRESS_REPORT__TEMPLATE__v0.1.0.md` | 进度报告模板 | Auditor → Canonical |
| `ssot/03_agent_playbook/handoff_templates/FEEDBACK_PACKAGE__TEMPLATE__v0.1.0.md` | 反馈包模板 | Auditor → Raw-b |

#### 交接模板索引

```
Secretary → (Designer/Factory): GOAL_BRIEF__TEMPLATE__v0.1.0.md
Chief Designer → Factory: BLUEPRINT__TEMPLATE__v0.1.0.md
Factory → Team Lead: CAPABILITY_ORDER__TEMPLATE__v0.1.0.md
Team Lead → Crew: TASK_CONTRACT__TEMPLATE__v0.1.0.md
Auditor → Canonical: PROGRESS_REPORT__TEMPLATE__v0.1.0.md
Auditor → Raw-b: FEEDBACK_PACKAGE__TEMPLATE__v0.1.0.md
```

### 4.2.5 路由契约（Routing Contract）

#### 路由规则（规范）

```yaml
Routing Contract (normative):
  Input:
    - 任务描述（目标文本）
    - 可选元数据（类型、受影响路径、风险标志）
  Output:
    - 一个role_id
    - reason
    - 可选required_skills[]
  Rule: 给定相同输入和RoleSpec，路由必须是确定性的
```

---

## 4.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 角色路由 | 确定性任务到角色分配 | `role_router.py` | `role_router.py --task "fix login bug" --meta '{"risk": "high"}'` |
| 技能验证 | 验证技能调用合规性 | `skill_call_guard.py` | `skill_call_guard.py --task-code TASK-001 --skill SHELL_WRITE` |
| 能力查询 | 查询可用能力 | `capability_query.py` | `capability_query.py list` |
| 角色检查 | 运行角色检查清单 | `role_checklist.py` | `role_checklist.py --role executor --task TASK-001` |
| 交接生成 | 生成交接文档 | `handoff_generator.py` | `handoff_generator.py --template TASK_CONTRACT --data task.json` |
| 模板渲染 | 渲染交接模板 | `template_renderer.py` | `template_renderer.py --template BLUEPRINT --vars '{"goal": "..."}'` |

---

## 4.4 脚本使用示例

```bash
# 1. 路由任务到适当角色
python tools/scc/ops/role_router.py \
  --task "修复登录页面的CSS样式问题" \
  --meta '{"type": "frontend", "risk": "low", "paths": ["src/css/login.css"]}' \
  --format json
# 输出: {"role_id": "executor", "reason": "frontend bug fix within scope", "required_skills": ["SHELL_WRITE", "PATCH_APPLY"]}

# 2. 验证技能调用合规性（CI门）
python tools/ci/skill_call_guard.py \
  --task-code TASK-001 \
  --skill SHELL_WRITE \
  --scope-allow '["src/css/*", "src/js/*"]' \
  --actual-paths '["src/css/login.css"]' \
  --fail-closed

# 3. 查询所有可用能力
python tools/scc/ops/capability_query.py list \
  --format table \
  --include-roles

# 4. 运行角色检查清单
python tools/scc/ops/role_checklist.py \
  --role executor \
  --task TASK-001 \
  --check-inputs \
  --check-outputs \
  --check-non-goals

# 5. 生成任务契约交接文档
python tools/scc/ops/handoff_generator.py \
  --template TASK_CONTRACT \
  --data task_001.json \
  --output contracts/task_001_contract.md

# 6. 渲染蓝图模板
python tools/scc/ops/template_renderer.py \
  --template BLUEPRINT \
  --vars '{"goal": "实现用户认证系统", "constraints": ["使用JWT", "支持OAuth"], "acceptance": ["单元测试覆盖率>80%"]}' \
  --output blueprints/auth_system.md
```

---

## 4.5 关键文件针脚

```yaml
L4_prompt_layer:
  ssot_partition: "03_agent_playbook"
  chapter: 9
  description: "提示词层 - 提供角色定义、技能规范、能力目录、交接模板"
  
  core_spec_files:
    - path: scc-top/docs/ssot/03_agent_playbook/ROLE_SPEC__v0.1.0.md
      oid: 01KGCV31NRV7N75QMWE6X01JWQ
      layer: CANON
      primary_unit: X.DISPATCH
      description: "角色规范定义，9个最小角色、路由契约、门禁规则"
    - path: scc-top/docs/ssot/03_agent_playbook/SKILL_SPEC__v0.1.0.md
      oid: 01KGCV31PTC2CNRKV9BM3KXXWQ
      layer: CANON
      primary_unit: X.DISPATCH
      description: "技能规范定义，最小技能集、门禁规则、证据规则"
    - path: scc-top/docs/ssot/03_agent_playbook/CAPABILITY_CATALOG__v0.1.0.md
      oid: 01KGCV31KR2Z3Y3Y4GPPNNNGRZ
      layer: CANON
      primary_unit: X.DISPATCH
      description: "能力目录，Agent可调用的最小能力集"
    - path: scc-top/docs/ssot/03_agent_playbook/handoff_templates/index.md
      oid: 01KGDT0H7TXA8XY6TDRXAZ9N1J
      layer: CANON
      primary_unit: S.NAV_UPDATE
      description: "交接模板索引，角色间文档即接口的模板"

### 4.2.5 Pins-first规范与CI手册

#### 核心规则

目标：让模型只读最小上下文，降低读仓成本，提升并行吞吐。

1. **只给 3-10 个关键文件**（不提供目录）
2. **大文件/日志不要进入 context pack**
3. **Executor 必须 pins-first，缺 pins 直接失败**

#### SSOT公理（SSOT_AXIOMS_JSON）

```json
{
  "schema_version": "scc.ssot_axioms.v1",
  "axioms": [
    {
      "id": "AXIOM-001",
      "statement": "Executor never reads SSOT directly",
      "rationale": "Ensures all context is explicitly provided via pins"
    },
    {
      "id": "AXIOM-002", 
      "statement": "All tasks must use pins-first constraints",
      "rationale": "Minimizes context window and improves reproducibility"
    }
  ]
}
```

#### CI通过手册（必读）

**步骤**：
1. 确认改动文件都在 `pins.allowed_paths` 内，且未触碰 `forbidden_paths`
2. 运行 `allowedTests` 中的自测命令（代码任务必须包含至少一条非 `task_selftest` 的真实测试）
3. 在输出中追加 SUBMIT JSON：
   ```
   SUBMIT: {"status":"pass","reason_code":"...","touched_files":["file1","file2"],"tests_run":["your test cmd"]}
   ```
4. 证据可裁决：exit_code=0，SUBMIT.touched_files 与实际改动一致，日志/补丁齐全
5. 本地预检查：`python scc-top/tools/scc/ops/task_selftest.py --task-id <task_id>` 确认返回码 0

**错误码**：
- `ci_failed`: 测试命令执行失败或 exit_code!=0，先复现再补证据
- `ci_skipped`: 缺少可执行测试命令；添加至少一条非 task_selftest 的 allowedTests
- `tests_only_task_selftest`: 仅给了 task_selftest；补充真实测试命令后重试

#### Task Class Library

预定义的常见任务类型：

| 任务类 | 描述 | Pins模板 | 允许测试 |
|--------|------|----------|----------|
| schema_add_field_v1 | 添加数据库字段 | db/schema_core_v1 | db:migrate:smoke |
| scc_api_add_endpoint_v1 | 添加SCC API端点 | scc_api_routes_v1 | scc:routes:smoke |
| scc_task_store_update_v1 | 更新任务存储 | scc_task_store_v1 | scc:tasks:smoke |
| scc_claim_lease_v1 | 申领/释放任务 | scc_claiming_v1 | scc:claim:smoke |
| model_router_rule_update_v1 | 更新模型路由规则 | model_router_v1 | router:smoke |
| tool_registry_add_v1 | 添加工具注册 | tool_registry_v1 | tool:registry:smoke |
| config_flag_add_v1 | 添加配置/标志 | config_flag_v1 | config:smoke |

#### Pins Templates

预定义的上下文包模板：

```json
{
  "templates": [
    {
      "id": "db/schema_core_v1",
      "allowed_paths": ["src/db/schema.sql"],
      "forbidden_paths": ["infra/"],
      "max_files": 2,
      "max_loc": 200
    },
    {
      "id": "scc_api_routes_v1",
      "allowed_paths": ["packages/opencode/src/server/routes/scc.ts"],
      "max_files": 2,
      "max_loc": 220
    },
    {
      "id": "scc_task_store_v1",
      "allowed_paths": ["packages/opencode/src/scc/tasks.ts"],
      "max_files": 2,
      "max_loc": 220
    }
  ]
}
```

### 4.2.6 编译器产物（Compiler Outputs）

#### Legal Prefix（效力声明）

运行时注入的前缀，声明权威条款和优先级：

```
# SCC Legal Prefix v1.0.0
# 效力声明 - 必须遵守

## 存在性声明
以下引用文档为权威条款，具有约束力：
- docs/prompt_os/constitution.md@v1.0.0
- docs/prompt_os/conflict_order.md@v1.0.0
- docs/L3_documentation/policies/hard.md@v1.0.0

## 优先级声明（冲突时按此顺序）
1. Constitution (L0) - 不可违反
2. Hard Policies (L1) - 违反即失败
3. Role Constraints (L2) - 超出即拒绝
4. Task Contracts (L3) - 违反即重试
5. Factory Policies (L4) - 违反即熔断
6. Soft Policies (L5) - 偏好，不阻断

## 违规后果
- 违反 L0-L1: 任务立即失败，记录安全事件
- 违反 L2: 操作被拒绝，可能角色降级
- 违反 L3: 任务重试或升级
- 违反 L4: 触发熔断或降级
- 违反 L5: 记录，无惩罚

## 核心原则（必须遵守）
1. PINS-FIRST: 必须 pins-first，缺 pins 直接失败
2. FAIL-CLOSED: 不确定时关闭而非开放
3. EVIDENCE-BASED: 所有裁决必须有证据
4. VERSIONED-REFS: 所有引用必须带版本
5. MINIMAL-CONTEXT: 只加载必要的上下文
```

#### Refs Index（引用索引）

权威引用索引，包含所有关键文档的路径、版本、哈希：

| ID | 路径 | 版本 | 优先级 | Always Include |
|----|------|------|--------|----------------|
| constitution | docs/prompt_os/constitution.md | v1.0.0 | L0 | ✓ |
| conflict_order | docs/prompt_os/conflict_order.md | v1.0.0 | L1 | ✓ |
| hard_policies | docs/L3_documentation/policies/hard.md | v1.0.0 | L1 | ✓ |
| rbac_policy | docs/L13_security/rbac_policy.json | v1.0.0 | L2 | ✓ |
| fail_codes | docs/prompt_os/io/fail_codes.md | v1.0.0 | L3 | ✓ |

  
  role_packs:
    - path: scc-top/docs/ssot/03_agent_playbook/roles/router/
      oid: 011F1603B44E614A36AC6D0301B2
      description: "Router角色包"
    - path: scc-top/docs/ssot/03_agent_playbook/roles/planner/
      oid: 010F2FE9E35B714E709D1A03C8B8
      description: "Planner角色包"
    - path: scc-top/docs/ssot/03_agent_playbook/roles/executor/
      oid: 01A8D9DFC365D749C4941E64CDCB
      description: "Executor角色包"
    - path: scc-top/docs/ssot/03_agent_playbook/roles/verifier/
      oid: 010326A948C7804EE3A1BBC90998
      description: "Verifier角色包"
    - path: scc-top/docs/ssot/03_agent_playbook/roles/auditor/
      oid: 01170F0D2B11A24D698D543C3715
      description: "Auditor角色包"
    - path: scc-top/docs/ssot/03_agent_playbook/roles/secretary/
      oid: 0185EAD8B5EC4E4EE68C41CB821D
      description: "Secretary角色包"
    - path: scc-top/docs/ssot/03_agent_playbook/roles/factory_manager/
      oid: 013BC4018FDA4D4B9E8DC410FD07
      description: "Factory Manager角色包"
    - path: scc-top/docs/ssot/03_agent_playbook/roles/team_lead/
      oid: 014C26424A53BA442CA52DD29AC0
      description: "Team Lead角色包"
    - path: scc-top/docs/ssot/03_agent_playbook/roles/chief_designer/
      oid: 01327AFF4F47BF43B8A0B1D6BD76
      description: "Chief Designer角色包"
  
  handoff_templates:
    - path: scc-top/docs/ssot/03_agent_playbook/handoff_templates/TASK_CONTRACT__TEMPLATE__v0.1.0.md
      oid: 01C2F7E900D1224BC983C4A4B61D
      description: "任务契约模板（Team Lead → Crew）"
    - path: scc-top/docs/ssot/03_agent_playbook/handoff_templates/BLUEPRINT__TEMPLATE__v0.1.0.md
      oid: 016C54F893F50E4BB094A4F1C31B
      description: "蓝图模板（Chief Designer → Factory）"
    - path: scc-top/docs/ssot/03_agent_playbook/handoff_templates/GOAL_BRIEF__TEMPLATE__v0.1.0.md
      oid: 0150A0818124A34CDC806E66F6BF
      description: "目标简报模板（Secretary → Designer/Factory）"
    - path: scc-top/docs/ssot/03_agent_playbook/handoff_templates/CAPABILITY_ORDER__TEMPLATE__v0.1.0.md
      oid: 01C46BA8F41D3548AC8E73D86E30
      description: "能力订单模板（Factory → Team Lead）"
    - path: scc-top/docs/ssot/03_agent_playbook/handoff_templates/PROGRESS_REPORT__TEMPLATE__v0.1.0.md
      oid: 017842432E70D147CA96792B46A1
      description: "进度报告模板（Auditor → Canonical）"
    - path: scc-top/docs/ssot/03_agent_playbook/handoff_templates/FEEDBACK_PACKAGE__TEMPLATE__v0.1.0.md
      oid: 01D4939E7263414C23BA755CAF55
      description: "反馈包模板（Auditor → Raw-b）"
  
  machine_readable_specs:
    - path: scc-top/docs/ssot/03_agent_playbook/role_spec.json
      oid: 01F22F65C17E2C46CDB0E5EC1CE6
      description: "角色规范（JSON格式）"
    - path: scc-top/docs/ssot/03_agent_playbook/skill_spec.json
      oid: 01707A98E483E54BF6AF495221E7
      description: "技能规范（JSON格式）"
    - path: scc-top/docs/ssot/03_agent_playbook/capability_catalog.json
      oid: 01B9E8CC449E6D48C3BB98CBFA74
      description: "能力目录（JSON格式）"
  
### 4.2.7 Context Pack规范（Slot-Based）

#### 目标

- **单一法律载体**: 所有层次/优先级/效力由固定slot决定
- **单一执行入口**: 执行必须在Context Pack渲染、验证并写入磁盘后才能进行
- **Fail-closed**: 超出范围的读/写、缺失的版本引用、缺失的必需slot或完整性违规必须失败

#### 固定Slots（不能添加/删除）

Slot顺序具有约束力：

| Slot | 名称 | 类型 | 说明 |
|------|------|------|------|
| SLOT0 | LEGAL_PREFIX | always-on | 效力声明 |
| SLOT1 | BINDING_REFS | always-on | 版本化+哈希化的引用 |
| SLOT2 | ROLE_CAPSULE | conditional | 角色胶囊 |
| SLOT3 | TASK_BUNDLE | conditional | 任务包（执行必需） |
| SLOT4 | STATE | conditional | 状态 |
| SLOT5 | TOOLS | conditional | 工具 |
| SLOT6 | OPTIONAL_CONTEXT | conditional | 可选上下文（**非约束性**） |

#### 绑定语义

- **绑定slots**: `SLOT0..SLOT5`（根据存在规则；`SLOT0`和`SLOT1`始终开启）
- **非绑定slot**: `SLOT6 OPTIONAL_CONTEXT`仅为建议性，绝不能覆盖绑定slots

#### 运行时输出

渲染后的pack输出写入：
- `artifacts/scc_runs/<run_id>/rendered_context_pack.json`
- `artifacts/scc_runs/<run_id>/rendered_context_pack.txt`
- `artifacts/scc_runs/<run_id>/meta.json`

### 4.2.8 角色定义（JSON格式）

#### Judge（裁决者）

```json
{
  "role_id": "oid:L6:Role:01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "name": "judge",
  "description": "裁决者，解决冲突、发布最终裁决",
  "permissions": {
    "read": ["evidence/*", "contracts/*", "verdicts/*", "audit_logs/*"],
    "write": ["verdicts/*", "conflict_resolutions/*"]
  },
  "skills": ["resolve_conflict", "issue_verdict", "interpret_constitution", "review_evidence"],
  "constraints": {
    "read_only_evidence": true,
    "no_direct_code_access": true,
    "verdict_must_have_reasoning": true,
    "timeout": 600
  },
  "responsibilities": [
    "解决策略冲突",
    "解释 Constitution",
    "审查证据并发布裁决",
    "更新 Conflict Order（如需要）",
    "记录裁决理由"
  ],
  "principles": [
    "只读证据，不读解释",
    "基于事实，不基于推测",
    "裁决必须可验证",
    "保持中立，不偏袒任何一方"
  ]
}
```

#### Task Compiler（任务编译者）

```json
{
  "role_id": "oid:L6:Role:01ARZ3NDEKTSV4RRFFQ69G5FAV",
  "name": "task_compiler",
  "description": "任务编译者，将任务计划编译为可执行的 Task Bundle",
  "permissions": {
    "read": ["contracts/*", "docs/prompt_os/norms/contracts/*", "task_graphs/*", "plans/*"],
    "write": ["task_bundles/*"]
  },
  "skills": ["compile_task_bundle", "validate_contract", "generate_pins", "create_allowlist"],
  "constraints": {
    "max_bundle_size": "10MB",
    "max_pins_per_task": 20,
    "timeout": 300
  },
  "responsibilities": [
    "解析任务图，生成任务合同",
    "根据任务类型生成 pins",
    "创建 allowlist 和 tool_allowlist",
    "验证 bundle 完整性",
    "输出标准化的 task_bundle/"
  ]
}
```

  
  tools:
    - path: tools/scc/ops/role_router.py
      oid: 01B942B9D4F21E4574B3136D56FA
    - path: tools/ci/skill_call_guard.py
      oid: 01B9D5BFEFB6214F11B9AA796DC5
    - path: tools/scc/ops/capability_query.py
      oid: 01F9582ED9AA7440B7940403D36A
    - path: tools/scc/ops/role_checklist.py
      oid: 0148E89CDDA0604927B8D061A999
    - path: tools/scc/ops/handoff_generator.py
      oid: 01702FCC1FA2F94BAD93B9EE20BC
    - path: tools/scc/ops/template_renderer.py
      oid: 0197CA42206FEE40C98E6D706556
  
  related_chapters:
    - chapter: technical_manual/chapter_09_prompt_layer.md
      oid: 019B4B039D5B274A6DB045E9C5F7
```

---


### 4.2.9 编译流程与运行时Prompt组成

> **层级**: L4  
> **阶段**: 阶段1-定义层  
> **依赖**: L3, L17  
> **被依赖**: L2  
> **版本**: v1.0.0  
> **更新日期**: 2026-02-08

## 层级职责

提示词层负责将静态文档编译为可执行的运行时提示词：
1. **Compiler** - 将源文档编译为运行时片段
2. **Router** - 根据任务动态选择注入内容
3. **Legal Prefix** - 效力声明（Always-on）
4. **Refs Index** - 权威引用索引

## 核心组件

| 组件 | 路径 | 状态 | 说明 |
|------|------|------|------|
| 效力声明 | [../prompt_os/compiler/legal_prefix_v1.txt](../prompt_os/compiler/legal_prefix_v1.txt) | 🚧 P0 | 运行时前缀 |
| 引用索引 | [../prompt_os/compiler/refs_index_v1.json](../prompt_os/compiler/refs_index_v1.json) | 🚧 P0 | 权威引用 |
| IO摘要 | io_digest_v1.txt | 🔜 P1 | IO层摘要 |
| 工具摘要 | tool_digest_v1.txt | 🔜 P1 | 工具层摘要 |
| 错误码摘要 | fail_digest_v1.txt | 🔜 P1 | 错误码摘要 |

## 编译流程

```
源文档（Markdown/JSON）
    ↓
Compiler解析
    ↓
提取关键信息
    ↓
生成编译产物
    ├── legal_prefix_v1.txt
    ├── refs_index_v1.json
    ├── io_digest_v1.txt
    ├── tool_digest_v1.txt
    └── fail_digest_v1.txt
    ↓
运行时注入
```

## 运行时Prompt组成

```
┌─────────────────────────────────────┐
│  Legal Prefix（Always-on）           │
│  - 效力声明                          │
│  - 优先级规则                        │
│  - 违规后果                          │
├─────────────────────────────────────┤
│  Binding Refs Index（Always-on）     │
│  - 权威文档列表                      │
│  - 版本与哈希                        │
├─────────────────────────────────────┤
│  IO Digest（Always-on）              │
│  - 输入格式                          │
│  - 输出格式                          │
│  - 错误码                            │
├─────────────────────────────────────┤
│  Role Capsule（Conditional）         │
│  - 角色职责                          │
│  - 权限范围                          │
│  - 禁止事项                          │
├─────────────────────────────────────┤
│  Task Bundle（Conditional）          │
│  - 任务合同                          │
│  - Pins                              │
│  - 验收标准                          │
├─────────────────────────────────────┤
│  User/Task Input                     │
│  - 具体任务内容                      │
└─────────────────────────────────────┘
```

## 注入策略

| 内容类型 | 注入条件 | Token预算 |
|---------|---------|----------|
| Always-on | 所有任务 | 500 |
| Conditional | 按角色/任务类型 | 1500 |
| Never-on | 默认不注入 | - |

## 相关文件

- [../prompt_os/compiler/](../prompt_os/compiler/) - 编译产物目录
- [../L3_documentation/layer_index.md](../L3_documentation/layer_index.md) - 文档层
- [../L2_task/layer_index.md](../L2_task/layer_index.md) - 任务层

## 变更记录

| 日期 | 版本 | 变更内容 |
|------|------|---------|
| 2026-02-08 | v1.0.0 | 初始版本 |

## 4.6 本章小结

### 4.6.1 核心概念

| 概念 | 说明 | 来源文件 |
|------|------|----------|
| Role | Agent角色，9个最小角色定义 | ROLE_SPEC__v0.1.0.md |
| Skill | 技能，6个最小技能 | SKILL_SPEC__v0.1.0.md |
| Capability | 能力，5个最小能力 | CAPABILITY_CATALOG__v0.1.0.md |
| Handoff Template | 交接模板，6个标准模板 | handoff_templates/index.md |
| Routing Contract | 路由契约，确定性分配 | ROLE_SPEC__v0.1.0.md |
| Role Pack | 角色包，包含ROLE.md/checklist | roles/ |

### 4.6.2 关键规则

1. **确定性路由**: 给定相同输入和RoleSpec，路由必须是确定性的
2. **门禁规则**: 任何声称DONE的任务必须能通过适当的guard(s)验证
3. **证据分离**: 规范文档不得嵌入大段证据，必须链接到artifacts/
4. **角色禁止事项**: 每个角色有明确的Non-goals(hard)，必须遵守
5. **交接文档化**: 角色间协作必须通过标准化的交接模板

### 4.6.3 依赖关系

```
L4 提示词层
    │
    ├─ 依赖 → L17本体层（OID用于角色/技能标识）
    ├─ 依赖 → L2任务层（契约定义角色输入输出）
    │
    ├─ 提供角色定义给 → L6 Agent层
    ├─ 提供技能规范给 → L7 工具层
    ├─ 提供路由契约给 → L11 路由层
    ├─ 提供交接模板给 → L15 变更层
    └─ 提供门禁规则给 → L13 安全层
```

---

**导航**: [← L3](./L3_documentation_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L5](./L5_model_layer.md)