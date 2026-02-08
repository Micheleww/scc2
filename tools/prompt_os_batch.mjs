#!/usr/bin/env node
/**
 * Prompt OS Engineering — Batch Task Submission Script
 *
 * 一次性向 SCC Gateway 提交 1 个 parent task + 12 个 atomic child tasks，
 * 由 10 个 opencodecli worker 并行执行，使用免费模型 (GLM-4.7 / Kimi-K2.5)。
 *
 * Usage:
 *   node tools/prompt_os_batch.mjs                     # submit to gateway
 *   node tools/prompt_os_batch.mjs --dry-run            # print tasks JSON only
 *   SCC_BASE_URL=http://host:port node tools/prompt_os_batch.mjs
 */

const BASE_URL = process.env.SCC_BASE_URL || "http://127.0.0.1:18788";

// ─── Helpers ─────────────────────────────────────────────────────────

async function post(path, body) {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  if (!res.ok) throw new Error(`POST ${path} => ${res.status}: ${JSON.stringify(json)}`);
  return json;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ─── Parent Task ─────────────────────────────────────────────────────

const PARENT_TASK = {
  kind: "parent",
  title: "Prompt OS Engineering — Full Build",
  goal: `# Prompt OS 完整工程构建

## 目标
构建 docs/prompt_os/ 下完整的提示词操作系统工程资产，包含 5 个子系统 + 编译器层 + 角色胶囊 + 评估框架。

## 子系统
1. Norms（规范层）: constitution, policies, contracts, conflict_order
2. IO（输入输出层）: schemas, fail_codes, evidence_spec
3. Context（上下文层）: pins_spec, context_budget, memory_write_policy, task_state_fields
4. Knowledge（知识层）: glossary, best_practices, domain_kb
5. Tools（工具层）: catalog, policy, api_rules, data_rules, degrade_strategy

## 附加层
6. Compiler（编译器输出）: legal_prefix, refs_index, io_digest, tool_digest, fail_digest
7. Roles（角色胶囊）: 7 个角色的完整 .md 文件
8. Eval（评估框架）: golden_tasks, expected_verdicts, metrics

## 验收标准
- 所有 40+ 文件按规范产出
- 每个文件 > 200 字节，结构完整
- JSON 文件可通过 JSON.parse 校验
- 角色胶囊覆盖全部 7 个核心角色
- 评估框架包含至少 3 条 golden task`,
  role: "doc",
  lane: "batchlane",
  status: "ready",
  files: ["docs/prompt_os/"],
  allowedExecutors: ["opencodecli"],
  allowedModels: ["glm-4.7", "kimi-k2.5"],
};

// ─── Child Tasks ─────────────────────────────────────────────────────

function childTasks(parentId) {
  return [

    // ════════════════════════════════════════════════════════════════
    // T01 — Norms: Constitution & Conflict Order
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T01: Constitution & Conflict Order",
      goal: `# 任务：创建 Prompt OS 宪法与冲突优先级文档

## 背景
SCC (Self-Coordinating Codebase) 是一个多 AI agent 协同的代码工厂系统。
Prompt OS 是其提示词工程层，用于规范所有 agent 的行为。
"宪法" 是 Prompt OS 的最高权威文档，定义不可违反的核心原则。

## 你需要创建以下文件

### 文件 1: docs/prompt_os/norms/constitution.md

写一份 AI agent 系统宪法，包含以下章节：

1. **Preamble（序言）** — 说明本宪法的目的：约束所有 AI agent 在 SCC 系统中的行为
2. **Article 1: Safety Invariants（安全不变量）**
   - 不得删除用户未明确要求删除的文件
   - 不得执行网络请求（除非 role policy 明确允许）
   - 不得修改 contracts/, roles/, skills/ 目录（除非 role 有 can_modify_contracts 权限）
   - 不得暴露 secrets/** 下的任何内容
   - 不得绕过 preflight gate 或 hygiene check
3. **Article 2: Correctness Guarantees（正确性保证）**
   - 产出必须符合对应的 JSON Schema（submit.schema.json）
   - 测试必须通过才能提交 DONE 状态
   - 修改的文件必须在 changed_files 中声明
   - exit_code 必须为 0 才能声明成功
4. **Article 3: Scope Discipline（范围纪律）**
   - 只修改 pins.allowed_paths 允许的文件
   - 只使用 role policy 允许的工具
   - 不得超出 task goal 定义的范围
5. **Article 4: Transparency（透明性）**
   - 所有决策必须在 report.md 中说明理由
   - 失败必须 emit 对应的事件（如 CI_FAILED, POLICY_VIOLATION）
   - 不得静默吞掉错误
6. **Article 5: Amendment Process（修正流程）**
   - 宪法修正需要 admin 角色批准
   - 修正必须记录在 changelog 中

### 文件 2: docs/prompt_os/norms/conflict_order.md

写一份冲突优先级文档，说明当多个规范冲突时的解决顺序：

\`\`\`
Priority (highest → lowest):
1. Constitution (安全不变量 > 一切)
2. Hard Policies (factory_policy.json 中的硬约束)
3. Role Policy (roles/*.json)
4. Task Contract (task-level constraints)
5. Soft Policies (建议性规范)
6. Best Practices (非强制性的最佳实践)
\`\`\`

每一层需要说明：
- 什么算该层的约束
- 冲突时如何判定
- 违反时的处理（error/warning/ignore）

## 格式要求
- Markdown 格式
- 使用英文撰写（标准技术文档）
- 每个文件至少 300 字
- 结构清晰，带有目录（TOC）`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/norms/constitution.md",
        "docs/prompt_os/norms/conflict_order.md",
      ],
      pins: { allowed_paths: ["docs/prompt_os/norms/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/norms/constitution.md",
        "test -s docs/prompt_os/norms/conflict_order.md",
        "grep -q 'Article 1' docs/prompt_os/norms/constitution.md",
        "grep -q 'Priority' docs/prompt_os/norms/conflict_order.md",
      ],
      assumptions: [
        "Output in English",
        "Markdown format with TOC",
        "Each file > 300 words",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T02 — Norms: Policies (Hard / Soft / Security)
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T02: Hard, Soft & Security Policies",
      goal: `# 任务：创建 Prompt OS 策略文档集

## 背景
SCC 系统的策略分为三类：
- **Hard Policy（硬策略）**：必须遵守，违反 → 任务立即失败
- **Soft Policy（软策略）**：建议遵守，违反 → 警告但不阻断
- **Security Policy（安全策略）**：安全相关的约束集

## 你需要创建以下文件

### 文件 1: docs/prompt_os/norms/policies/hard.md

硬策略文档，包含：

1. **File Scope Enforcement**
   - Agent 只能修改 pins.allowed_paths 中声明的文件
   - Agent 只能读取 role policy allow_paths 中的文件
   - 违反 → SCOPE_CONFLICT 事件 + 任务失败

2. **Schema Compliance**
   - submit.json 必须通过 contracts/submit/submit.schema.json 校验
   - verdict.json 必须通过对应 schema 校验
   - 违反 → SCHEMA_VIOLATION 事件 + 任务失败

3. **Test Gate**
   - 声明 status=DONE 时，tests.passed 必须为 true
   - allowedTests 中的命令必须全部执行
   - 违反 → CI_FAILED 事件 + 任务失败

4. **WIP Limits**
   - 同时 in_progress 的任务不超过 factory_policy 中的 wip_limit
   - 超限 → 新任务进入 backlog 等待

5. **Budget Limits**
   - 单任务 token 用量不超过 budget.max_tokens_per_task
   - 单任务执行时间不超过 timeoutMs
   - 超限 → BUDGET_EXCEEDED + 任务失败

### 文件 2: docs/prompt_os/norms/policies/soft.md

软策略文档，包含：

1. **Code Style** — 遵循项目已有风格，不强制
2. **Documentation** — 建议为新函数添加 JSDoc，不强制
3. **Commit Message** — 建议使用 conventional commits 格式
4. **Error Handling** — 建议使用 try-catch 而非静默忽略
5. **Logging** — 建议使用结构化日志

每条软策略说明：建议原因、不遵守的后果（warning 级别）、例外情况

### 文件 3: docs/prompt_os/norms/policies/security.md

安全策略文档，包含：

1. **Secret Protection** — **/secrets/** 路径永远不可读写
2. **No Network Access** — 除非 role policy tools.allow 包含 "network"
3. **Input Validation** — 外部输入必须校验，防止注入
4. **No Eval/exec** — 禁止使用 eval()、exec()、child_process.exec(user_input)
5. **Dependency Safety** — 不得添加未经审查的新依赖
6. **Credential Hygiene** — 不得在日志/报告中输出密钥

## 格式要求
- 英文 Markdown，每个文件有 TOC
- 每条策略需要：描述、违反后果、示例`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/norms/policies/hard.md",
        "docs/prompt_os/norms/policies/soft.md",
        "docs/prompt_os/norms/policies/security.md",
      ],
      pins: { allowed_paths: ["docs/prompt_os/norms/policies/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/norms/policies/hard.md",
        "test -s docs/prompt_os/norms/policies/soft.md",
        "test -s docs/prompt_os/norms/policies/security.md",
        "grep -q 'File Scope' docs/prompt_os/norms/policies/hard.md",
      ],
      assumptions: [
        "Output in English",
        "Each file has TOC",
        "Each policy has description + consequence + example",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T03 — Norms: Contracts (Task Contract Spec + Escalation)
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T03: Task Contract & Escalation Spec",
      goal: `# 任务：创建任务合同规范和升级链文档

## 背景
在 SCC 系统中，每个 task 与系统之间有一份"合同"：
- Task 承诺在 scope 内完成 goal
- 系统承诺提供 context、tools、budget
- 当 task 无法完成时，需要按升级链处理

## 你需要创建以下文件

### 文件 1: docs/prompt_os/norms/contracts/task_contract_spec.md

任务合同规范文档：

1. **Contract Structure（合同结构）**
   \`\`\`
   Task Contract = {
     task_id:          唯一标识
     goal:             任务目标（自然语言）
     role:             执行角色
     pins:             允许访问的文件路径
     allowed_tests:    必须通过的测试命令
     allowed_models:   可使用的模型列表
     allowed_executors: 可使用的执行器
     timeout:          超时时间
     max_attempts:     最大重试次数
   }
   \`\`\`

2. **Obligation Matrix（义务矩阵）**
   | 方面 | Agent 义务 | System 义务 |
   |------|-----------|------------|
   | Scope | 只修改 pins 允许的文件 | 提供 pins 声明的文件访问 |
   | Quality | tests.passed = true | 执行所有 allowedTests |
   | Reporting | 产出 submit.json + report.md | 存储 artifacts |
   | Timeout | timeout 内完成 | timeout 后终止 |

3. **Breach Handling（违约处理）**
   - Agent 违反 scope → SCOPE_CONFLICT
   - Agent 测试失败 → CI_FAILED
   - Agent 超时 → TIMEOUT_EXCEEDED
   - System 未提供 context → PINS_INSUFFICIENT

4. **Contract Lifecycle**
   - Created → Active → Fulfilled / Breached
   - 说明每个状态转换的条件

### 文件 2: docs/prompt_os/norms/contracts/escalation.md

升级链文档：

1. **Escalation Levels（升级层级）**
   - Level 0: Self-retry（同一模型重试，max_attempts 内）
   - Level 1: Model upgrade（切换到更强模型）
   - Level 2: Role escalation（切换到更高权限角色）
   - Level 3: Human intervention（需要人工介入 → NEED_INPUT）
   - Level 4: Task abort（任务废弃 → DLQ）

2. **Escalation Triggers（触发条件）**
   - 连续 N 次同一 error → 升级
   - POLICY_VIOLATION → 直接 Level 3
   - BUDGET_EXCEEDED → 直接 Level 4

3. **Escalation Flow Diagram**（ASCII 流程图）

## 格式要求
- 英文 Markdown
- 包含表格和流程图
- 每个文件至少 400 字`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/norms/contracts/task_contract_spec.md",
        "docs/prompt_os/norms/contracts/escalation.md",
      ],
      pins: { allowed_paths: ["docs/prompt_os/norms/contracts/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/norms/contracts/task_contract_spec.md",
        "test -s docs/prompt_os/norms/contracts/escalation.md",
        "grep -q 'Obligation' docs/prompt_os/norms/contracts/task_contract_spec.md",
        "grep -q 'Level' docs/prompt_os/norms/contracts/escalation.md",
      ],
      assumptions: [
        "Output in English",
        "Include tables and ASCII flow diagrams",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T04 — IO Layer: Schemas, Fail Codes, Evidence Spec
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T04: IO Layer — Schemas, Fail Codes, Evidence",
      goal: `# 任务：创建 IO 层文档

## 背景
IO 层定义了 SCC 系统中所有 agent 输入输出的标准格式。

## 你需要创建以下文件

### 文件 1: docs/prompt_os/io/schemas.md

输入输出 Schema 规范，描述：

1. **Task Input Schema**
   \`\`\`json
   {
     "task_id": "uuid",
     "goal": "string — 自然语言任务描述",
     "role": "string — 角色名",
     "pins": {
       "allowed_paths": ["string[]"],
       "forbidden_paths": ["string[]"]
     },
     "files": ["string[] — 需要操作的文件列表"],
     "context": {
       "map": "object — 代码库结构图",
       "docs": "object — 相关文档引用",
       "history": "object — 任务历史"
     }
   }
   \`\`\`

2. **Task Output Schema (submit.json)**
   \`\`\`json
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
   \`\`\`

3. **Verdict Schema** — 系统对 submit 的判定结果格式

### 文件 2: docs/prompt_os/io/fail_codes.md

错误代码目录，每个代码包含：代码、含义、触发条件、处理建议

| Code | Meaning | Trigger | Action |
|------|---------|---------|--------|
| SCOPE_CONFLICT | 修改了不允许的文件 | changed_files 超出 pins | 重新限定 scope 后重试 |
| CI_FAILED | 测试未通过 | tests.passed = false | 检查测试输出后重试 |
| SCHEMA_VIOLATION | 输出格式不合规 | submit.json 校验失败 | 修复格式后重试 |
| PINS_INSUFFICIENT | 上下文不足 | 缺少必要的 pin 文件 | 请求补充 pins |
| POLICY_VIOLATION | 违反角色策略 | 使用了禁止的工具/路径 | 升级处理 |
| BUDGET_EXCEEDED | 超出预算限制 | token/time 超限 | 优化后重试或升级 |
| TIMEOUT_EXCEEDED | 执行超时 | 超过 timeoutMs | 拆分任务或升级 |
| EXECUTOR_ERROR | 执行器内部错误 | 模型 API 故障等 | 自动重试 |
| PREFLIGHT_FAILED | 预检失败 | role/pins 校验不通过 | 修正配置 |

（至少 15 个错误代码）

### 文件 3: docs/prompt_os/io/evidence_spec.md

证据规范文档：

1. **Evidence Types（证据类型）**
   - patch.diff: git diff 格式的变更补丁
   - selftest.log: 测试执行的完整日志
   - report.md: 任务执行报告
   - submit.json: 标准化提交文件
   - screenshots/: 可选的截图证据

2. **Evidence Directory Structure**
   \`\`\`
   artifacts/
   ├── report.md
   ├── selftest.log
   ├── evidence/
   │   ├── patch.diff
   │   ├── pre_state.json
   │   └── post_state.json
   ├── patch.diff
   └── submit.json
   \`\`\`

3. **Evidence Retention Policy** — 保留策略
4. **Evidence Validation Rules** — 每种证据的校验规则

## 格式要求
- 英文 Markdown
- fail_codes 必须用表格格式
- 至少 15 个错误代码`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/io/schemas.md",
        "docs/prompt_os/io/fail_codes.md",
        "docs/prompt_os/io/evidence_spec.md",
      ],
      pins: { allowed_paths: ["docs/prompt_os/io/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/io/schemas.md",
        "test -s docs/prompt_os/io/fail_codes.md",
        "test -s docs/prompt_os/io/evidence_spec.md",
        "grep -q 'SCOPE_CONFLICT' docs/prompt_os/io/fail_codes.md",
      ],
      assumptions: [
        "Output in English",
        "Fail codes table must have at least 15 entries",
        "Include JSON examples in schemas.md",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T05 — Context Layer
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T05: Context Layer — Pins, Budget, Memory, State",
      goal: `# 任务：创建上下文管理层文档

## 背景
上下文层管理 agent 执行时的信息输入。SCC 使用 "pins" 机制控制 agent 可访问的文件范围。

## 你需要创建以下文件

### 文件 1: docs/prompt_os/context/pins_spec.md

Pins（别针）规范：

1. **什么是 Pins**
   - Pins 是任务级别的文件访问控制声明
   - 每个任务有 allowed_paths（允许）和 forbidden_paths（禁止）
   - Pins 由 planner/splitter 在创建任务时分配

2. **Pins 结构**
   \`\`\`json
   {
     "allowed_paths": ["src/gateway.mjs", "src/utils/*.mjs", "docs/**"],
     "forbidden_paths": ["**/secrets/**", "node_modules/**"]
   }
   \`\`\`

3. **Pins Resolution（解析规则）**
   - Glob 语法：** 匹配多级目录，* 匹配单级
   - forbidden 优先于 allowed
   - 空 allowed_paths = 不允许访问任何文件

4. **Pins Inheritance（继承规则）**
   - Child task 的 pins ⊆ parent task 的 pins
   - 不可超出 parent 授权范围

5. **Pins Validation（校验规则）**
   - Preflight 阶段校验 pins 与 role policy 的兼容性
   - pins_required = true 的角色必须有非空 allowed_paths

### 文件 2: docs/prompt_os/context/context_budget.md

上下文预算管理：

1. **Token Budget（令牌预算）**
   - max_context_tokens: 单次提示的最大 token 数
   - context_priority: 当预算不足时的裁剪优先级
     1. Task goal（不可裁剪）
     2. Pins content（按相关度裁剪）
     3. Map summary（可裁剪为摘要）
     4. History（可完全省略）

2. **Budget Allocation Strategy**
   - goal: 固定占比 ~15%
   - pinned files: ~50%
   - map/context: ~25%
   - reserved for output: ~10%

3. **Overflow Handling（溢出处理）**
   - 超限时按优先级裁剪
   - 裁剪日志记入 context_trim_log

### 文件 3: docs/prompt_os/context/memory_write_policy.md

记忆写入策略：

1. **Short-term Memory（短期记忆）**
   - 任务内的中间状态，任务完成后清除
2. **Long-term Memory（长期记忆）**
   - 跨任务的学习成果，写入 docs/ 或 map/
   - 只允许通过特定角色（ssot_curator）写入
3. **Memory Conflict Resolution**
   - 新记忆与旧记忆冲突时的处理规则

### 文件 4: docs/prompt_os/context/task_state_fields.md

任务状态字段规范：

列出 task 对象的所有状态字段及其含义：

| Field | Type | Description | Mutable |
|-------|------|-------------|---------|
| id | uuid | 任务唯一标识 | No |
| status | enum | backlog/ready/in_progress/done/failed | Yes |
| kind | enum | parent/atomic | No |
| role | string | 执行角色 | No |
| lane | enum | fastlane/mainlane/batchlane/quarantine/dlq | Yes |
| priority | number | 优先级 | Yes |
| ... | ... | ... | ... |

（列出至少 20 个字段）

## 格式要求
- 英文 Markdown
- 使用表格和 JSON 示例
- task_state_fields 至少 20 个字段`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/context/pins_spec.md",
        "docs/prompt_os/context/context_budget.md",
        "docs/prompt_os/context/memory_write_policy.md",
        "docs/prompt_os/context/task_state_fields.md",
      ],
      pins: { allowed_paths: ["docs/prompt_os/context/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/context/pins_spec.md",
        "test -s docs/prompt_os/context/context_budget.md",
        "test -s docs/prompt_os/context/memory_write_policy.md",
        "test -s docs/prompt_os/context/task_state_fields.md",
      ],
      assumptions: [
        "Output in English",
        "task_state_fields must list at least 20 fields",
        "Include JSON examples",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T06 — Knowledge Layer
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T06: Knowledge — Glossary, Best Practices, Domain KB",
      goal: `# 任务：创建知识层文档

## 背景
知识层为 agent 提供领域知识参考，确保术语一致、实践统一。

## 你需要创建以下文件

### 文件 1: docs/prompt_os/knowledge/glossary.md

SCC 系统术语表，按字母排序，每个术语包含：
- **Term**: 术语名
- **Definition**: 定义
- **Context**: 使用场景
- **Related**: 相关术语

必须包含以下术语（至少 30 个）：

| Term | Definition |
|------|-----------|
| Agent | AI 执行单元，接收任务并产出结果 |
| Board | 任务面板，管理所有任务的生命周期 |
| Circuit Breaker | 熔断器，连续失败后暂停任务分派 |
| Constitution | 宪法，Prompt OS 最高权威文档 |
| Contract | 合同，任务与系统之间的约定 |
| DLQ | Dead Letter Queue，死信队列 |
| Degradation Matrix | 降级矩阵，模型不可用时的降级策略 |
| Escalation | 升级，任务无法完成时的处理流程 |
| Evidence | 证据，任务执行结果的证明 |
| Factory Policy | 工厂策略，全局行为配置 |
| Gate | 门禁，任务执行前后的检查点 |
| Goal | 目标，任务的自然语言描述 |
| Hygiene Check | 卫生检查，任务完成后的格式校验 |
| Instinct | 本能聚类，相似任务的模式识别 |
| Lane | 泳道，任务的调度通道 |
| Map | 代码地图，仓库结构的符号索引 |
| Pins | 别针，文件级访问控制声明 |
| Playbook | 剧本，预定义的任务序列 |
| Preflight | 预检，任务执行前的资格检查 |
| Role | 角色，agent 的权限和能力集 |
| Scope | 范围，任务允许修改的文件集 |
| Skill | 技能，角色可使用的专项能力 |
| SSOT | Single Source of Truth，唯一可信源 |
| Submit | 提交，agent 完成任务后的标准化输出 |
| Verdict | 判定，系统对提交结果的评判 |
| WIP Limit | 在制品限制，同时进行任务的数量上限 |
| ... | 至少补充到 30 个 |

### 文件 2: docs/prompt_os/knowledge/best_practices.md

最佳实践指南：

1. **Task Decomposition（任务分解）**
   - 每个 atomic task 应该 < 500 行变更
   - 优先纵向切分（按功能），不要横向切分（按层）
   - Parent task 只做计划，不做实施

2. **Prompt Writing（提示词编写）**
   - Goal 必须包含：背景、具体要求、验收标准
   - 使用 markdown 格式化，便于模型解析
   - 提供 before/after 示例

3. **Testing（测试）**
   - 优先写存在性测试（文件是否生成）
   - 其次写内容测试（关键内容是否包含）
   - 最后写集成测试（多文件协作）

4. **Error Recovery（错误恢复）**
   - 遇到 CI_FAILED：先读 selftest.log，修复后重试
   - 遇到 SCOPE_CONFLICT：检查 pins 配置
   - 遇到 TIMEOUT：拆分为更小的子任务

5. **Documentation（文档）**
   - report.md 必须说明做了什么和为什么
   - 代码变更必须配 patch.diff
   - 新文件列入 new_files

### 文件 3: docs/prompt_os/knowledge/domain_kb.md

领域知识库：

1. **SCC Architecture Overview（架构概览）**
   - Gateway: HTTP API 服务器，核心调度
   - Board: 任务状态管理
   - Executor: 任务执行器（opencodecli, codex）
   - Verifier: 提交校验器
   - Judge: 判定器（DONE/RETRY/ESCALATE）

2. **Task Lifecycle（任务生命周期）**
   \`\`\`
   backlog → ready → in_progress → [done | failed | blocked]
                                        ↓
                                    [retry → in_progress]
                                        ↓
                                    [escalate → quarantine/dlq]
   \`\`\`

3. **Role System（角色系统）**
   - 7 核心角色的简要说明
   - 权限矩阵

4. **Event System（事件系统）**
   - 事件类型及触发条件

## 格式要求
- 英文 Markdown
- Glossary 按字母排序，至少 30 个术语
- Best practices 带编号和示例`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/knowledge/glossary.md",
        "docs/prompt_os/knowledge/best_practices.md",
        "docs/prompt_os/knowledge/domain_kb.md",
      ],
      pins: { allowed_paths: ["docs/prompt_os/knowledge/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/knowledge/glossary.md",
        "test -s docs/prompt_os/knowledge/best_practices.md",
        "test -s docs/prompt_os/knowledge/domain_kb.md",
        "grep -c '|' docs/prompt_os/knowledge/glossary.md | awk '{exit ($1 >= 30) ? 0 : 1}'",
      ],
      assumptions: [
        "Output in English",
        "Glossary must have at least 30 terms in table format",
        "Best practices must include examples",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T07 — Tools Layer
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T07: Tools — Catalog, Policy, API/Data Rules, Degrade",
      goal: `# 任务：创建工具层文档

## 背景
工具层定义 agent 可用的工具集及使用策略。

## 你需要创建以下文件

### 文件 1: docs/prompt_os/tools/catalog.md

工具目录，列出所有可用工具：

| Tool | Category | Description | Risk Level | Requires Auth |
|------|----------|-------------|------------|---------------|
| git | VCS | 版本控制操作 | LOW | No |
| rg (ripgrep) | Search | 代码搜索 | LOW | No |
| node | Runtime | Node.js 执行 | MEDIUM | No |
| python | Runtime | Python 执行 | MEDIUM | No |
| pytest | Test | Python 测试框架 | LOW | No |
| network | IO | 网络访问 | HIGH | Yes (role) |
| bash | Shell | Shell 命令执行 | HIGH | No |
| fs.read | File | 文件读取 | LOW | No (via pins) |
| fs.write | File | 文件写入 | MEDIUM | No (via pins) |
| fs.delete | File | 文件删除 | HIGH | Yes (explicit) |

每个工具需要：名称、分类、描述、风险级别、是否需要授权、使用限制

### 文件 2: docs/prompt_os/tools/policy.md

工具使用策略：

1. **Default Deny（默认拒绝）**
   - 未在 role policy tools.allow 中列出的工具 → 禁止使用
2. **Explicit Deny Override（显式拒绝覆盖）**
   - tools.deny 中列出的工具 → 绝对禁止，即使 allow 中也有
3. **Risk-based Approval（基于风险的审批）**
   - LOW: 自动允许
   - MEDIUM: 需要 preflight 通过
   - HIGH: 需要人工审批或特殊角色
4. **Audit Trail（审计跟踪）**
   - 所有工具调用记录到 evidence

### 文件 3: docs/prompt_os/tools/api_rules.md

API 使用规则：

1. **Rate Limiting** — 模型 API 调用频率限制
2. **Retry Policy** — 失败重试策略（指数退避）
3. **Fallback Chain** — 主模型失败时的备选模型链
4. **Token Accounting** — Token 用量记录和预算追踪
5. **Response Validation** — 模型响应的格式校验

### 文件 4: docs/prompt_os/tools/data_rules.md

数据规则：

1. **Data Classification（数据分类）**
   - Public: 可自由读写
   - Internal: 仅内部角色可访问
   - Confidential: secrets/** 下，任何角色不可访问
2. **Data Flow Rules（数据流规则）**
   - 数据只能从高分类流向低分类，不可反向
3. **PII Handling（个人信息处理）**
   - 日志中不得包含 PII
   - report.md 中如需引用，须脱敏

### 文件 5: docs/prompt_os/tools/degrade_strategy.md

降级策略：

1. **Model Degradation（模型降级）**
   \`\`\`
   Tier 1 (Premium): claude-opus, gpt-4o
   Tier 2 (Standard): claude-sonnet, gpt-4o-mini
   Tier 3 (Free): glm-4.7, kimi-k2.5, deepseek
   \`\`\`
   当高级模型不可用时，按 Tier 降级

2. **Feature Degradation（功能降级）**
   - Map 不可用 → 回退到文件列表
   - Instinct 不可用 → 跳过聚类
   - Playbook 不可用 → 单步执行

3. **Circuit Breaker Rules（熔断规则）**
   - 连续 N 次失败 → 熔断该模型/执行器
   - 熔断后 cooldown 期间不分派
   - cooldown 后半开试探

## 格式要求
- 英文 Markdown
- catalog 必须用表格
- 每个文件有 TOC`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/tools/catalog.md",
        "docs/prompt_os/tools/policy.md",
        "docs/prompt_os/tools/api_rules.md",
        "docs/prompt_os/tools/data_rules.md",
        "docs/prompt_os/tools/degrade_strategy.md",
      ],
      pins: { allowed_paths: ["docs/prompt_os/tools/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/tools/catalog.md",
        "test -s docs/prompt_os/tools/policy.md",
        "test -s docs/prompt_os/tools/api_rules.md",
        "test -s docs/prompt_os/tools/data_rules.md",
        "test -s docs/prompt_os/tools/degrade_strategy.md",
      ],
      assumptions: [
        "Output in English",
        "Catalog must use table format",
        "Each file must have TOC",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T08 — Compiler: Legal Prefix + IO Digest
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T08: Compiler — Legal Prefix & IO Digest",
      goal: `# 任务：生成编译器输出 — 法律前缀和 IO 摘要

## 背景
Prompt OS 的"编译器"将源文档编译为紧凑的运行时格式。
这些编译输出会被注入到每次 agent 调用的 system prompt 前缀中。

## 你需要创建以下文件

### 文件 1: docs/prompt_os/compiler/legal_prefix_v1.txt

这是注入到每个 agent 系统提示词开头的"法律前缀"文本。
它是 constitution.md 和 hard policies 的浓缩版，用最少的 token 传达最关键的约束。

格式要求：
- 纯文本，不使用 Markdown
- 总长度 < 800 tokens（约 600 英文单词）
- 使用编号列表，简洁明了
- 覆盖以下要点：

\`\`\`
[SCC LEGAL PREFIX v1]

1. SCOPE: You may ONLY modify files listed in your pins.allowed_paths.
   Modifying any file outside scope → immediate task failure.

2. SAFETY: You must NEVER:
   a) Access paths under **/secrets/**
   b) Make network requests unless explicitly allowed
   c) Delete files not specified in the task
   d) Use eval(), exec() with user input
   e) Bypass preflight or hygiene checks

3. OUTPUT: You MUST produce:
   a) artifacts/submit.json conforming to scc.submit.v1 schema
   b) artifacts/report.md explaining what you did and why
   c) artifacts/selftest.log with test execution output
   d) artifacts/patch.diff with all changes

4. TESTS: All commands in allowedTests MUST pass before
   declaring status=DONE. If tests fail, status=FAILED.

5. TRANSPARENCY: Report all errors. Never silently ignore failures.
   Emit appropriate events on failure.

6. CONFLICT RESOLUTION: Constitution > Hard Policy > Role Policy >
   Task Contract > Soft Policy > Best Practice.

[END LEGAL PREFIX]
\`\`\`

以上为参考模板，你需要完善和扩展，确保涵盖所有关键约束。

### 文件 2: docs/prompt_os/compiler/io_digest_v1.txt

IO 摘要 — 浓缩版的输入输出格式说明。
这是 io/schemas.md 和 io/fail_codes.md 的编译版。

格式要求：
- 纯文本
- 总长度 < 500 tokens
- 包含：
  1. submit.json 必填字段列表（一行一个）
  2. 常见错误代码速查表（代码 → 一句话说明）
  3. artifacts 必须包含的 5 个文件

模板参考：
\`\`\`
[SCC IO DIGEST v1]

== SUBMIT.JSON REQUIRED FIELDS ==
schema_version: "scc.submit.v1"
task_id: <your task ID>
status: DONE | NEED_INPUT | FAILED
changed_files: [list of modified file paths]
tests: { commands: [...], passed: bool, summary: "..." }
artifacts: { report_md, selftest_log, evidence_dir, patch_diff, submit_json }
exit_code: 0 (success) | non-zero (failure)
needs_input: [] (empty if status != NEED_INPUT)

== COMMON FAIL CODES ==
SCOPE_CONFLICT    → modified files outside allowed scope
CI_FAILED         → tests did not pass
SCHEMA_VIOLATION  → submit.json format invalid
PINS_INSUFFICIENT → needed files not in pins
POLICY_VIOLATION  → used forbidden tool/path
BUDGET_EXCEEDED   → exceeded token/time limit
TIMEOUT_EXCEEDED  → execution timed out

== REQUIRED ARTIFACTS ==
1. artifacts/report.md
2. artifacts/selftest.log
3. artifacts/evidence/
4. artifacts/patch.diff
5. artifacts/submit.json

[END IO DIGEST]
\`\`\`

## 格式要求
- 纯文本格式（.txt），不是 Markdown
- legal_prefix < 800 tokens
- io_digest < 500 tokens
- 简洁、高信息密度`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/compiler/legal_prefix_v1.txt",
        "docs/prompt_os/compiler/io_digest_v1.txt",
      ],
      pins: { allowed_paths: ["docs/prompt_os/compiler/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/compiler/legal_prefix_v1.txt",
        "test -s docs/prompt_os/compiler/io_digest_v1.txt",
        "grep -q 'LEGAL PREFIX' docs/prompt_os/compiler/legal_prefix_v1.txt",
        "grep -q 'IO DIGEST' docs/prompt_os/compiler/io_digest_v1.txt",
      ],
      assumptions: [
        "Plain text format, NOT Markdown",
        "legal_prefix < 800 tokens",
        "io_digest < 500 tokens",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T09 — Compiler: Tool Digest + Fail Digest
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T09: Compiler — Tool Digest & Fail Digest",
      goal: `# 任务：生成编译器输出 — 工具摘要和失败摘要

## 背景
与 T08 类似，这两个文件也是编译器输出，注入 agent 的 system prompt。

## 你需要创建以下文件

### 文件 1: docs/prompt_os/compiler/tool_digest_v1.txt

工具摘要 — 浓缩版的工具使用说明。

\`\`\`
[SCC TOOL DIGEST v1]

== AVAILABLE TOOLS ==
Your available tools depend on your role policy (tools.allow).
Common tools:

  git     — version control (commit, diff, log, status)
  rg      — code search (ripgrep, fast regex search)
  node    — execute JavaScript/Node.js code
  python  — execute Python scripts
  pytest  — run Python test suites
  bash    — shell command execution

== TOOL RULES ==
1. ONLY use tools listed in your role's tools.allow
2. NEVER use tools in your role's tools.deny
3. Network access requires explicit "network" in tools.allow
4. All tool invocations are logged for audit

== RISK LEVELS ==
  LOW:    git, rg, pytest, fs.read
  MEDIUM: node, python, fs.write, bash
  HIGH:   network, fs.delete

== API RULES ==
- Retry failed API calls with exponential backoff (2s, 4s, 8s, max 3)
- Track token usage per call
- Validate model response format before using
- Fallback: Tier1 → Tier2 → Tier3 models

[END TOOL DIGEST]
\`\`\`

完善以上模板，确保覆盖所有工具和规则。

### 文件 2: docs/prompt_os/compiler/fail_digest_v1.txt

失败处理摘要 — 告诉 agent 遇到各种错误时如何处理。

\`\`\`
[SCC FAIL DIGEST v1]

== WHEN YOU ENCOUNTER AN ERROR ==

IF test fails:
  → Read selftest.log for details
  → Fix the issue
  → Re-run tests
  → If still failing after max_attempts → status=FAILED, reason_code=CI_FAILED

IF scope violation:
  → Check your pins.allowed_paths
  → Remove modifications to out-of-scope files
  → Re-submit

IF schema validation fails:
  → Check submit.json against scc.submit.v1 schema
  → Ensure all required fields present
  → Ensure correct types (status is string, exit_code is integer)

IF timeout approaching:
  → Save partial progress
  → Set status=NEED_INPUT
  → Describe what's left in needs_input array

IF model API error:
  → Retry up to 3 times with backoff
  → If persistent → status=FAILED, reason_code=EXECUTOR_ERROR

IF pins insufficient:
  → Set status=NEED_INPUT
  → List needed files in needs_input
  → reason_code=PINS_INSUFFICIENT

== ESCALATION QUICK REF ==
  Self-retry → Model upgrade → Role escalation → Human → Abort
  POLICY_VIOLATION → immediate human escalation
  BUDGET_EXCEEDED → immediate abort

[END FAIL DIGEST]
\`\`\`

## 格式要求
- 纯文本格式
- tool_digest < 500 tokens
- fail_digest < 500 tokens
- 面向 agent 阅读，使用 IF/THEN 风格`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/compiler/tool_digest_v1.txt",
        "docs/prompt_os/compiler/fail_digest_v1.txt",
      ],
      pins: { allowed_paths: ["docs/prompt_os/compiler/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/compiler/tool_digest_v1.txt",
        "test -s docs/prompt_os/compiler/fail_digest_v1.txt",
        "grep -q 'TOOL DIGEST' docs/prompt_os/compiler/tool_digest_v1.txt",
        "grep -q 'FAIL DIGEST' docs/prompt_os/compiler/fail_digest_v1.txt",
      ],
      assumptions: [
        "Plain text, NOT Markdown",
        "Each file < 500 tokens",
        "Use IF/THEN style for fail digest",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T10 — Compiler: Refs Index (JSON)
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T10: Compiler — Refs Index JSON",
      goal: `# 任务：生成编译器输出 — 引用索引

## 背景
refs_index 是一个 JSON 文件，作为所有 Prompt OS 文档的交叉引用索引。
编译器/路由器可以用它快速定位需要注入哪些文档片段。

## 你需要创建

### 文件: docs/prompt_os/compiler/refs_index_v1.json

JSON 格式的引用索引：

\`\`\`json
{
  "version": "v1",
  "generated_at": "2026-02-08T00:00:00Z",
  "index": {
    "norms": {
      "constitution": {
        "path": "docs/prompt_os/norms/constitution.md",
        "digest_key": "legal_prefix",
        "inject_when": "always",
        "priority": 1,
        "tags": ["safety", "scope", "transparency"]
      },
      "conflict_order": {
        "path": "docs/prompt_os/norms/conflict_order.md",
        "digest_key": "legal_prefix",
        "inject_when": "always",
        "priority": 2,
        "tags": ["conflict", "priority"]
      },
      "hard_policy": {
        "path": "docs/prompt_os/norms/policies/hard.md",
        "digest_key": "legal_prefix",
        "inject_when": "always",
        "priority": 3,
        "tags": ["enforcement", "gates"]
      },
      "soft_policy": {
        "path": "docs/prompt_os/norms/policies/soft.md",
        "digest_key": null,
        "inject_when": "on_demand",
        "priority": 10,
        "tags": ["style", "suggestion"]
      },
      "security_policy": {
        "path": "docs/prompt_os/norms/policies/security.md",
        "digest_key": "legal_prefix",
        "inject_when": "always",
        "priority": 4,
        "tags": ["security", "safety"]
      }
    },
    "io": {
      "schemas": { "path": "docs/prompt_os/io/schemas.md", "digest_key": "io_digest", "inject_when": "always", "priority": 5, "tags": ["format", "schema"] },
      "fail_codes": { "path": "docs/prompt_os/io/fail_codes.md", "digest_key": "fail_digest", "inject_when": "always", "priority": 6, "tags": ["error", "recovery"] },
      "evidence_spec": { "path": "docs/prompt_os/io/evidence_spec.md", "digest_key": "io_digest", "inject_when": "on_demand", "priority": 11, "tags": ["evidence", "artifacts"] }
    },
    "context": {
      "pins_spec": { "path": "docs/prompt_os/context/pins_spec.md", "digest_key": null, "inject_when": "on_demand", "priority": 12, "tags": ["pins", "access"] },
      "context_budget": { "path": "docs/prompt_os/context/context_budget.md", "digest_key": null, "inject_when": "on_demand", "priority": 13, "tags": ["budget", "tokens"] },
      "memory_write_policy": { "path": "docs/prompt_os/context/memory_write_policy.md", "digest_key": null, "inject_when": "on_demand", "priority": 14, "tags": ["memory", "state"] },
      "task_state_fields": { "path": "docs/prompt_os/context/task_state_fields.md", "digest_key": null, "inject_when": "on_demand", "priority": 15, "tags": ["task", "state"] }
    },
    "knowledge": {
      "glossary": { "path": "docs/prompt_os/knowledge/glossary.md", "digest_key": null, "inject_when": "on_demand", "priority": 16, "tags": ["terms", "definitions"] },
      "best_practices": { "path": "docs/prompt_os/knowledge/best_practices.md", "digest_key": null, "inject_when": "on_demand", "priority": 17, "tags": ["practices", "patterns"] },
      "domain_kb": { "path": "docs/prompt_os/knowledge/domain_kb.md", "digest_key": null, "inject_when": "on_demand", "priority": 18, "tags": ["architecture", "system"] }
    },
    "tools": {
      "catalog": { "path": "docs/prompt_os/tools/catalog.md", "digest_key": "tool_digest", "inject_when": "always", "priority": 7, "tags": ["tools", "catalog"] },
      "policy": { "path": "docs/prompt_os/tools/policy.md", "digest_key": "tool_digest", "inject_when": "always", "priority": 8, "tags": ["tools", "rules"] },
      "api_rules": { "path": "docs/prompt_os/tools/api_rules.md", "digest_key": "tool_digest", "inject_when": "on_demand", "priority": 19, "tags": ["api", "retry"] },
      "data_rules": { "path": "docs/prompt_os/tools/data_rules.md", "digest_key": null, "inject_when": "on_demand", "priority": 20, "tags": ["data", "classification"] },
      "degrade_strategy": { "path": "docs/prompt_os/tools/degrade_strategy.md", "digest_key": "tool_digest", "inject_when": "on_demand", "priority": 21, "tags": ["degradation", "fallback"] }
    },
    "roles": {
      "planner": { "path": "docs/prompt_os/roles/planner.md", "inject_when": "role_match", "priority": 100, "tags": ["role"] },
      "splitter": { "path": "docs/prompt_os/roles/splitter.md", "inject_when": "role_match", "priority": 100, "tags": ["role"] },
      "engineer": { "path": "docs/prompt_os/roles/engineer.md", "inject_when": "role_match", "priority": 100, "tags": ["role"] },
      "reviewer": { "path": "docs/prompt_os/roles/reviewer.md", "inject_when": "role_match", "priority": 100, "tags": ["role"] },
      "doc": { "path": "docs/prompt_os/roles/doc.md", "inject_when": "role_match", "priority": 100, "tags": ["role"] },
      "ssot_curator": { "path": "docs/prompt_os/roles/ssot_curator.md", "inject_when": "role_match", "priority": 100, "tags": ["role"] },
      "designer": { "path": "docs/prompt_os/roles/designer.md", "inject_when": "role_match", "priority": 100, "tags": ["role"] }
    },
    "eval": {
      "metrics": { "path": "docs/prompt_os/eval/metrics.md", "inject_when": "never", "priority": 200, "tags": ["eval"] },
      "golden_tasks": { "path": "docs/prompt_os/eval/golden_tasks/", "inject_when": "never", "priority": 200, "tags": ["eval", "golden"] },
      "expected_verdicts": { "path": "docs/prompt_os/eval/expected_verdicts/", "inject_when": "never", "priority": 200, "tags": ["eval", "verdict"] }
    }
  },
  "inject_rules": {
    "always": "Injected into every agent system prompt via digest",
    "on_demand": "Injected only when tags match task context",
    "role_match": "Injected only when agent role matches",
    "never": "Never injected, used for offline evaluation only"
  }
}
\`\`\`

以上为完整模板。你需要：
1. 确保 JSON 语法正确（可通过 JSON.parse 校验）
2. 确保所有 path 字段与实际目录结构一致
3. 确保 tags 准确反映文档内容
4. generated_at 使用当前时间

## 格式要求
- 合法 JSON 格式
- 必须通过 JSON.parse 校验
- 缩进 2 空格`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/compiler/refs_index_v1.json",
      ],
      pins: { allowed_paths: ["docs/prompt_os/compiler/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/compiler/refs_index_v1.json",
        "node -e \"JSON.parse(require('fs').readFileSync('docs/prompt_os/compiler/refs_index_v1.json','utf8')); console.log('VALID JSON')\"",
      ],
      assumptions: [
        "Valid JSON with 2-space indentation",
        "All paths must match the docs/prompt_os/ directory structure",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T11 — Role Capsules (7 roles)
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T11: Role Capsules — 7 Core Roles",
      goal: `# 任务：创建 7 个角色胶囊文件

## 背景
角色胶囊是每个角色的完整行为说明书，当 agent 被分配某角色时，
对应的角色胶囊会被注入 system prompt。

## 你需要创建 7 个文件

每个角色胶囊必须遵循以下模板结构：

\`\`\`markdown
# Role: {RoleName}

## Identity
You are a {RoleName} in the SCC (Self-Coordinating Codebase) system.
{一句话说明角色定位}

## Capabilities
- can_plan: {true/false}
- can_write_code: {true/false}
- can_run_tests: {true/false}
- can_modify_contracts: {true/false}
- can_emit_events: {true/false}

## Permissions
### Read Access
- Allowed: {paths}
- Denied: {paths}

### Write Access
- Allowed: {paths}
- Denied: {paths}

### Tools
- Allowed: {tools}
- Denied: {tools}

## Workflow
1. {Step 1}
2. {Step 2}
...

## Required Outputs
- {output 1}
- {output 2}

## Gates
- Preflight: {required/not required}
- Hygiene: {required/not required}
- Max Attempts: {N}
- Stop Conditions: {list}

## Events
- On Success: {events}
- On Failure: {events}

## Common Pitfalls
1. {pitfall 1 + how to avoid}
2. {pitfall 2 + how to avoid}

## Examples
### Good Example
{brief example of correct behavior}

### Bad Example
{brief example of incorrect behavior}
\`\`\`

## 7 个角色的关键信息

### 1. docs/prompt_os/roles/planner.md
- Identity: 任务规划者，将大目标分解为可执行的子任务
- can_plan: true, can_write_code: false
- Read: docs/**, map/**, contracts/**
- Write: docs/tasks/**
- Tools: node
- Workflow: 分析目标 → 识别依赖 → 创建任务图 → 分配角色和 pins

### 2. docs/prompt_os/roles/splitter.md
- Identity: 任务拆分者，将 parent task 拆分为 atomic child tasks
- can_plan: true, can_write_code: false
- Read: docs/**, map/**
- Write: board tasks (via API)
- Tools: node
- Workflow: 接收 parent goal → 分析范围 → 创建 child tasks → 分配 pins

### 3. docs/prompt_os/roles/engineer.md
- Identity: 代码工程师，执行具体编码任务
- can_plan: false, can_write_code: true, can_run_tests: true
- Read: pins required (only pinned files)
- Write: scc-top/**, docs/**
- Tools: git, rg, node, python, pytest
- Workflow: 读取 pins → 理解 goal → 编码实现 → 运行测试 → 提交 submit.json
- Gates: preflight required, hygiene required, max 2 attempts

### 4. docs/prompt_os/roles/reviewer.md
- Identity: 代码审查者，审查 engineer 的产出
- can_plan: false, can_write_code: false
- Read: docs/**, artifacts/**, map/**
- Write: docs/reviews/**
- Tools: git, rg
- Workflow: 读取 patch → 检查质量 → 给出 verdict → 记录 review

### 5. docs/prompt_os/roles/doc.md
- Identity: 文档专家，创建和维护文档
- can_plan: false, can_write_code: false
- Read: docs/**, map/**, artifacts/**
- Write: docs/**
- Tools: git, node
- Workflow: 分析需求 → 收集信息 → 编写文档 → 格式检查

### 6. docs/prompt_os/roles/ssot_curator.md
- Identity: SSOT 管理者，维护唯一可信源
- Read: docs/**, map/**, contracts/**, roles/**, skills/**
- Write: docs/**
- Tools: git, rg, node, python
- Workflow: 扫描变更 → 更新索引 → 检查一致性 → 修复冲突

### 7. docs/prompt_os/roles/designer.md
- Identity: 架构设计师，负责任务图和系统设计
- can_plan: true, can_write_code: false
- Read: docs/**, map/**, artifacts/**
- Write: 无（只读 + 产出 task_graph.json）
- Tools: node
- Workflow: 分析目标 → 设计架构 → 创建任务图 → 提交设计

## 格式要求
- 英文 Markdown
- 严格遵循模板结构
- 每个角色文件至少 300 字
- 必须包含 Good/Bad Example`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/roles/planner.md",
        "docs/prompt_os/roles/splitter.md",
        "docs/prompt_os/roles/engineer.md",
        "docs/prompt_os/roles/reviewer.md",
        "docs/prompt_os/roles/doc.md",
        "docs/prompt_os/roles/ssot_curator.md",
        "docs/prompt_os/roles/designer.md",
      ],
      pins: { allowed_paths: ["docs/prompt_os/roles/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/roles/planner.md",
        "test -s docs/prompt_os/roles/engineer.md",
        "test -s docs/prompt_os/roles/reviewer.md",
        "test -s docs/prompt_os/roles/doc.md",
        "test -s docs/prompt_os/roles/designer.md",
        "test -s docs/prompt_os/roles/splitter.md",
        "test -s docs/prompt_os/roles/ssot_curator.md",
      ],
      assumptions: [
        "Output in English",
        "Follow template strictly",
        "Each file > 300 words",
        "Must include Good/Bad examples",
      ],
    },

    // ════════════════════════════════════════════════════════════════
    // T12 — Eval Framework: Golden Tasks, Verdicts, Metrics
    // ════════════════════════════════════════════════════════════════
    {
      title: "PromptOS T12: Eval Framework — Golden Tasks, Verdicts, Metrics",
      goal: `# 任务：创建评估框架

## 背景
评估框架用于持续测量 Prompt OS 的效果。
包含标准化测试用例（golden tasks）、预期判定结果和度量指标。

## 你需要创建以下文件

### 文件 1: docs/prompt_os/eval/metrics.md

评估指标文档：

1. **Task Success Rate（任务成功率）**
   - 定义: done_count / total_count
   - 目标: > 85%
   - 计算周期: 每日/每周

2. **First-Attempt Pass Rate（首次通过率）**
   - 定义: first_attempt_done / total_count
   - 目标: > 60%
   - 意义: 衡量提示词质量

3. **Escalation Rate（升级率）**
   - 定义: escalated_count / total_count
   - 目标: < 10%

4. **Average Attempts（平均尝试次数）**
   - 定义: sum(attempts) / total_count
   - 目标: < 1.5

5. **Policy Violation Rate（策略违规率）**
   - 定义: violation_count / total_count
   - 目标: < 2%

6. **Token Efficiency（Token 效率）**
   - 定义: tokens_used / task_complexity_score
   - 目标: 持续下降

7. **Test Coverage（测试覆盖率）**
   - 定义: tasks_with_tests / total_tasks
   - 目标: 100%

8. **Evidence Completeness（证据完整性）**
   - 定义: tasks_with_full_evidence / total_tasks
   - 目标: > 95%

每个指标包含：名称、定义公式、目标值、计算方法、告警阈值

### 文件 2: docs/prompt_os/eval/golden_tasks/README.md

Golden Tasks 说明文档 + 3 个示例 golden task：

\`\`\`markdown
# Golden Tasks

Golden tasks are standardized test cases for evaluating Prompt OS quality.

## Task Format
Each golden task is a JSON file with:
- task: the task definition (goal, role, files, pins)
- expected_outcome: expected status, changed files, test results
- difficulty: easy / medium / hard

## Example Tasks
\`\`\`

然后提供 3 个内嵌的 golden task 示例：

**Golden Task 1: Simple Doc Creation (Easy)**
\`\`\`json
{
  "id": "golden-001",
  "name": "Create a README.md",
  "difficulty": "easy",
  "task": {
    "goal": "Create a README.md file with project name, description, and usage instructions",
    "role": "doc",
    "files": ["README.md"],
    "pins": { "allowed_paths": ["README.md", "docs/**"] }
  },
  "expected_outcome": {
    "status": "DONE",
    "changed_files": ["README.md"],
    "tests_passed": true
  },
  "evaluation_criteria": [
    "File exists and is non-empty",
    "Contains project name",
    "Contains usage section"
  ]
}
\`\`\`

**Golden Task 2: Bug Fix (Medium)** — 修复一个简单的 bug
**Golden Task 3: Multi-file Refactor (Hard)** — 重构涉及多个文件

### 文件 3: docs/prompt_os/eval/expected_verdicts/README.md

预期判定结果说明文档：

\`\`\`markdown
# Expected Verdicts

Maps golden task outcomes to expected system verdicts.

## Verdict Types
- DONE: Task completed successfully
- RETRY: Task needs another attempt
- ESCALATE: Task needs model/role upgrade
- REJECT: Task output violates policies

## Verdict Matrix
| Golden Task | Submit Status | Tests | Expected Verdict |
|------------|--------------|-------|-----------------|
| golden-001 | DONE | passed | DONE |
| golden-001 | DONE | failed | RETRY |
| golden-001 | FAILED | - | RETRY |
| golden-002 | DONE | passed | DONE |
| golden-002 | DONE | failed | RETRY |
| golden-003 | NEED_INPUT | - | ESCALATE |
\`\`\`

说明每个判定的逻辑和依据。

## 格式要求
- 英文 Markdown
- Golden tasks 包含内嵌 JSON 示例
- Metrics 至少 8 个指标
- Verdict matrix 覆盖所有组合`,
      kind: "atomic",
      parentId,
      role: "doc",
      lane: "batchlane",
      status: "ready",
      files: [
        "docs/prompt_os/eval/metrics.md",
        "docs/prompt_os/eval/golden_tasks/README.md",
        "docs/prompt_os/eval/expected_verdicts/README.md",
      ],
      pins: { allowed_paths: ["docs/prompt_os/eval/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli"],
      allowedModels: ["glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "test -s docs/prompt_os/eval/metrics.md",
        "test -s docs/prompt_os/eval/golden_tasks/README.md",
        "test -s docs/prompt_os/eval/expected_verdicts/README.md",
        "grep -q 'Success Rate' docs/prompt_os/eval/metrics.md",
      ],
      assumptions: [
        "Output in English",
        "Metrics must have at least 8 indicators",
        "Golden tasks must include 3 JSON examples",
      ],
    },
  ];
}

// ─── Main ────────────────────────────────────────────────────────────

async function main() {
  const dryRun = process.argv.includes("--dry-run");

  console.log("╔══════════════════════════════════════════════════════════╗");
  console.log("║   Prompt OS Engineering — Batch Task Submission          ║");
  console.log("╚══════════════════════════════════════════════════════════╝");
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Mode: ${dryRun ? "DRY RUN (no submissions)" : "LIVE"}\n`);

  // ── Step 1: Create parent task ──
  console.log("━━━ Step 1: Creating parent task ━━━");
  let parentId = null;

  if (dryRun) {
    parentId = "dry-run-parent-id";
    console.log("[DRY] Parent task:", JSON.stringify(PARENT_TASK, null, 2));
    console.log(`[DRY] Parent ID: ${parentId}\n`);
  } else {
    try {
      const parent = await post("/board/tasks", PARENT_TASK);
      parentId = parent.id;
      console.log(`✓ Parent task created: ${parentId}`);
      console.log(`  Title: ${parent.title}\n`);
    } catch (err) {
      console.error(`✗ Failed to create parent task: ${err.message}`);
      process.exit(1);
    }
  }

  // ── Step 2: Create child tasks ──
  console.log("━━━ Step 2: Creating 12 child tasks ━━━");
  const children = childTasks(parentId);
  const results = [];

  for (let i = 0; i < children.length; i++) {
    const task = children[i];
    const label = `T${String(i + 1).padStart(2, "0")}`;

    if (dryRun) {
      console.log(`[DRY] ${label}: ${task.title}`);
      console.log(`      Files: ${task.files.join(", ")}`);
      results.push({ label, title: task.title, id: `dry-${label}`, status: "dry-run" });
    } else {
      try {
        const created = await post("/board/tasks", task);
        console.log(`✓ ${label}: ${created.title} → ${created.id}`);
        results.push({ label, title: created.title, id: created.id, status: "created" });
      } catch (err) {
        console.error(`✗ ${label}: ${task.title} → ${err.message}`);
        results.push({ label, title: task.title, id: null, status: "failed", error: err.message });
      }
      // Small delay between submissions to avoid overwhelming the gateway
      await sleep(200);
    }
  }

  // ── Step 3: Summary ──
  console.log("\n━━━ Summary ━━━");
  console.log(`Parent: ${parentId}`);
  console.log(`Children: ${results.filter(r => r.status === "created" || r.status === "dry-run").length}/${results.length} successful\n`);

  console.log("┌─────┬────────────────────────────────────────────────────────────┬──────────┐");
  console.log("│ ID  │ Title                                                      │ Status   │");
  console.log("├─────┼────────────────────────────────────────────────────────────┼──────────┤");
  for (const r of results) {
    const t = r.title.substring(0, 58).padEnd(58);
    const s = r.status.padEnd(8);
    console.log(`│ ${r.label} │ ${t} │ ${s} │`);
  }
  console.log("└─────┴────────────────────────────────────────────────────────────┴──────────┘");

  if (!dryRun) {
    console.log(`\nAll tasks submitted. Gateway will dispatch to opencodecli workers.`);
    console.log(`Monitor at: ${BASE_URL}/sccdev/`);
  } else {
    console.log(`\nDry run complete. Run without --dry-run to submit to gateway.`);
    // Write task definitions to file for review
    const allTasks = { parent: PARENT_TASK, children: children };
    const outPath = "artifacts/prompt_os_tasks.json";
    const { writeFileSync, mkdirSync } = await import("fs");
    mkdirSync("artifacts", { recursive: true });
    writeFileSync(outPath, JSON.stringify(allTasks, null, 2));
    console.log(`Task definitions written to: ${outPath}`);
  }
}

main().catch(err => {
  console.error("Fatal error:", err);
  process.exit(1);
});
