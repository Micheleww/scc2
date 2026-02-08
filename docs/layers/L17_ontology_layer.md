# L17 知识与本体层

> **对应SSOT分区**: `01_conventions/`（约定规范）  
> **对应技术手册**: 第2章  
> **层定位**: 最基础层，提供术语定义、ID体系、实体关系

---

## 17.1 层定位与职责

### 17.1.1 核心职责

L17是SCC架构的**最基础层**，为全系统提供：

1. **术语定义** - 统一全系统的词汇和概念
2. **ID体系** - OID/ULID生成与管理规范
3. **实体关系** - 核心实体及其关系的正式定义
4. **文档元数据** - 文档的标准化描述

### 17.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L17 知识与本体层                              │
│ ├─ ID体系 (ULID/OID)                         │
│ ├─ 实体关系定义                               │
│ ├─ Unit Registry                             │
│ └─ 文档治理规范                               │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L1-L16 所有其他层级                          │
└─────────────────────────────────────────────┘
```

---

## 17.2 来自01_conventions/的核心内容

### 17.2.1 OID/ULID规范体系

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/01_conventions/OID_SPEC__v0.1.0.md` | OID规范定义 | ULID格式、生成规则、验证规则、PostgreSQL注册表 |
| `ssot/01_conventions/UNIT_REGISTRY__v0.1.0.md` | Unit注册表 | 13个Stream、40+个Unit定义 |

#### OID/ULID格式详解

```
ULID格式（26字符Crockford's Base32编码）
┌─────────────────────────────────────────────────────────┐
│  01ARZ3NDEKTSV4RRFFQ69G5FAV                              │
│  └┬┘└──────┬──────┘└──────┬──────┘                     │
│   │        │              │                             │
│   │        │              └── 随机数 (80 bits)          │
│   │        └───────────────── 时间戳 (48 bits)          │
│   └────────────────────────── Crockford's Base32        │
└─────────────────────────────────────────────────────────┘

验证规则：
- 长度 == 26字符
- 字符集: 0-9 A-H J K M N P-T V-Z（大写）
- 排除 I, L, O, U 避免混淆
```

#### PostgreSQL权威注册表

```sql
-- objects表结构（来自OID_SPEC__v0.1.0.md）
CREATE TABLE objects (
    oid TEXT PRIMARY KEY,
    path TEXT NOT NULL,                    -- repo_root相对路径
    kind TEXT NOT NULL,                    -- md/json/ts/py/log/patch/...
    layer TEXT NOT NULL,                   -- RAW|DERIVED|CANON|DIST|CODE|CONF|TOOL|REPORT
    primary_unit TEXT NOT NULL,            -- 必须存在于Unit Registry
    tags TEXT[] NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active', -- active|moved|deprecated|tombstoned
    sha256 TEXT NULL,
    derived_from TEXT[] NOT NULL DEFAULT '{}',
    replaced_by TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 推荐索引
CREATE UNIQUE INDEX idx_active_path ON objects(path) WHERE status='active';
CREATE INDEX idx_primary_unit ON objects(primary_unit);
CREATE INDEX idx_tags ON objects USING GIN(tags);
```

### 17.2.2 Unit Registry（单元注册表）

#### Stream定义（13个Stream）

| Stream | 名称 | 说明 |
|--------|------|------|
| G | Goal & Intake | 人类目标输入和 intake 路由 |
| R | Raw Capture | 捕获原始源 + 清单 |
| N | Normalize | 事件规范化、绑定、去重 |
| D | Derive Tasks | 从原始源派生任务树 |
| K | Contractize | 契约 + 验收定义 |
| X | Execute | 调度 + 执行器集成 |
| V | Verify | 测试 + 裁决 + 质量门 |
| P | Progress Review | 定期进度审计 |
| S | Synthesize & Publish | 规范更新 + 分发 |
| F | Feedback | 反馈包 -> raw-b 重新 intake |
| A | Agent Roles | 路由/执行角色 |
| C | Capability Catalog | 能力清单 + 映射 |
| W | Workspace | 工作空间规范/不变量 |

#### 核心Unit示例

```yaml
# G — Goal & Intake
G.GOAL_INPUT:          "解释来自网络聊天的原始人类目标"
G.INTAKE_ROUTING:      "将传入项目路由到派生/契约/调度"

# A — Agent Roles  
A.ROUTER:              "确定性路由任务到角色"
A.PLANNER:             "仅生成计划/契约草案"
A.EXECUTOR:            "在允许列表内应用更改并生成证据"
A.VERIFIER:            "运行验收并发出裁决工件"
A.AUDITOR:             "审计不变量/证据而不编辑"
A.SECRETARY:           "将原始输入总结为派生笔记"
A.FACTORY_MANAGER:     "优先/调度；不直接执行更改"

# V — Verify
V.TESTS:               "运行测试/冒烟/类型检查"
V.VERDICT:             "裁决评估 + 通过/失败分类"
V.OID_VALIDATOR:       "oid_validator 门"
V.GUARD:               "通用守卫检查（故障关闭）"
V.SKILL_GUARD:         "技能调用守卫（taskcode/guard 链）"
```

### 17.2.3 术语表（Glossary）

| Term | Definition | Context | Related |
|------|------------|---------|---------|
| Agent | An AI execution unit that receives tasks and produces results. | Used when describing who/what performs work in the system. | Role, Executor |
| Artifact | A generated deliverable produced during execution (e.g., report, patch, logs). | Referenced by verifiers/judges as proof of completion. | Evidence, Submit |
| Circuit Breaker | A safety mechanism that pauses task dispatch after repeated failures. | Prevents cascading failures when an executor/model is unhealthy. | Degradation Matrix, Escalation |
| Constitution | The highest-authority document defining Prompt OS rules and priorities. | Used to resolve conflicts between policies and behaviors. | Factory Policy, Contract |
| Contract | The explicit agreement between a task and the system (inputs, outputs, constraints). | Defines acceptance criteria, pins, tests, and required artifacts. | Scope, Submit |
| DLQ | Dead Letter Queue; a holding area for tasks that can no longer be processed normally. | Used after repeated failures or unresolved blocks. | Quarantine, Escalation |
| Escalation | The process for handling tasks that cannot be completed within constraints. | Triggered by missing scope, unclear requirements, or persistent failures. | DLQ, Verdict |
| Evidence | Proof that a task was executed correctly (logs, diffs, screenshots, outputs). | Collected to support verification and judging. | Artifact, Hygiene Check |
| Executor | The component that runs task steps and produces artifacts (e.g., opencodecli, codex). | Executes changes, runs checks, and generates outputs. | Agent, Verifier |
| Factory Policy | Global behavior configuration applied to all tasks and roles. | Controls defaults like formatting, safety rules, and retries. | Constitution, Role |
| Gate | A checkpoint before or after execution (e.g., preflight gate, hygiene gate). | Ensures constraints are met at defined boundaries. | Preflight, Hygiene Check |
| Gateway | The HTTP API server responsible for orchestration and core scheduling. | Routes requests and coordinates Board, Executor, and Verifier. | Board, Event System |
| Goal | A natural-language statement describing what the task should accomplish. | Drives task planning, decomposition, and acceptance criteria. | Prompt, Contract |
| Pins | File-level access control declarations that constrain reads/writes. | Defines what paths a task is allowed to touch. | Scope, Gate |
| Role | A named capability and permission set for an agent. | Determines what actions an agent may perform. | Permission Matrix, Scope |
| SSOT | Single Source of Truth; the uniquely trusted reference for a fact or rule. | Prevents conflicting guidance across documents/config. | Constitution, Map |
| Submit | The standardized completion output containing artifacts and metadata. | Passed to verifier and judge for evaluation. | Evidence, Verdict |
| Task | A unit of work with goal, constraints, and acceptance criteria. | The primary object tracked on the Board. | Board, Contract |
| Verdict | The final decision outcome for a submission (e.g., DONE/RETRY/ESCALATE). | Emitted by the judge based on evidence and policy. | Judge, Retry |

### 17.2.4 ID体系规范（OID/ULID）

#### ULID 规范

```
01ARZ3NDEKTSV4RRFFQ69G5FAV
└┬┘└──────┬──────┘└──────┬──────┘
 │        │              │
 │        │              └── 随机数 (80 bits)
 │        └───────────────── 时间戳 (48 bits)
 └────────────────────────── Crockford's Base32
```

**特性**:
- 长度: 26字符
- 编码: Crockford's Base32（大写）
- 时间精度: 毫秒级（48 bits）
- 随机部分: 80 bits
- 字典排序: 按时间排序
- 冲突概率: ~1 in 2^80

**Crockford's Base32 字符集**:
```
0123456789ABCDEFGHJKMNPQRSTVWXYZ
注意: 排除 I, L, O, U 避免混淆
```

#### OID 分层实体标识符

**格式**: `oid:<Layer>:<Kind>:<ULID>`

**示例**:
- `oid:L2:Task:01ARZ3NDEKTSV4RRFFQ69G5FAV`
- `oid:L4:Role:01ARZ3NDEKTSV4RRFFQ69G5FAV`
- `oid:L17:Entity:01ARZ3NDEKTSV4RRFFQ69G5FAV`

### 17.2.5 文档治理规范

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/01_conventions/DOCFLOW_SSOT__v0.1.0.md` | 文档流SSOT规范 | 文档创建→审核→发布→归档的完整流程 |
| `ssot/01_conventions/DOC_REGISTRY__v0.1.0.md` | 文档注册表规范 | 文档元数据结构、注册、查询规范 |
| `ssot/01_conventions/SINGLE_TRUTH_PRIORITY__v0.1.0.md` | 单一事实优先级 | 定义SSOT优先级的规则 |

#### 文档生命周期状态机

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│  DRAFT  │ → │  REVIEW │ → │ APPROVED│ → │PUBLISHED│ → │ARCHIVED │
│  草稿   │    │  审核中 │    │  已批准 │    │  已发布 │    │  已归档 │
└─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘
     ↑                                              ↓
     └────────────── 退回修改 ←─────────────────────┘
```

#### 单一事实优先级规则

```
优先级从高到低：
1. PostgreSQL object_index (运行时权威)
2. 内联YAML frontmatter (文档自描述)
3. 文件路径/命名约定
4. SSOT registry 缓存

冲突解决：低优先级必须向高优先级对齐
```

### 17.2.6 最佳实践（Best Practices）

#### 任务分解原则

1. 保持每个**原子任务**小巧：目标**< 500行**代码/内容更改
2. 优先**垂直切片（按功能/结果）**而非水平切片（按层级）
3. **父任务**应专注于**规划和协调**，而非实现

**示例**:
- ✅ 垂直切片："Add glossary + best practices + domain KB docs for Prompt OS."
- ❌ 水平切片："Update all docs headings everywhere"（太宽泛，验收不明确）

#### 提示词编写

**目标必须包含**:
1. **背景**: 为什么需要这个变更
2. **具体需求**: 必须创建/修改什么
3. **验收标准**: 如何评判

**格式指导**:
- 优先使用**Markdown**，包含标题、列表和代码块
- 为模糊需求包含**前后对比**示例
- 使用一致的术语（参见术语表）

#### 测试顺序

**推荐序列**:
1. **存在性测试**: 确认文件已生成/更新
2. **内容测试**: 确认关键字符串/部分存在
3. **集成测试**: 确认多个文件协同工作（链接、引用、共享词汇）

#### 错误恢复

**如果 CI_FAILED**:
1. 首先读取 `selftest.log`
2. 修复根本原因
3. 重新运行最小的相关检查

**如果 SCOPE_CONFLICT**:
1. 重新检查 **pins** allowlist
2. 确保没有更改范围外的文件
3. 如果需要额外文件，触发升级并清楚列出缺失路径

### 17.2.7 领域知识库（Domain KB）

#### SCC架构概览

SCC由具有明确职责的协作组件组成：

- **Gateway**: HTTP API服务器和核心编排器。接受请求、分发工作并协调其他组件
- **Board**: 任务状态管理。存储任务并管理生命周期转换
- **Executor**: 任务执行引擎（例如 `opencodecli`, `codex`），执行更改并生成产物
- **Verifier**: 验证输出是否符合约束和验收测试（pins、格式、必需产物）
- **Judge**: 根据验证器结果和策略发布最终结果（DONE/RETRY/ESCALATE）

#### 任务生命周期

```
backlog → ready → in_progress → [done | failed | blocked]
                                     ↓
                                 [retry → in_progress]
                                     ↓
                                 [escalate → quarantine/dlq]
```

- **backlog**: 已捕获的工作；可能缺少先决条件
- **ready**: 所有先决条件已满足；符合调度条件
- **in_progress**: 正在由agent/执行器执行
- **done**: 被验证器/裁决者接受
- **failed**: 执行失败；如果可修复可以重试
- **blocked**: 由于缺少范围、缺少输入或外部依赖而无法继续

#### 角色系统

**7个核心角色**:

1. **Requester**: 提交目标、约束和验收标准
2. **Planner**: 将目标分解为原子任务并定义门/测试
3. **Executor**: 在范围内实现更改并生成产物
4. **Reviewer**: 执行人类风格的推理检查（逻辑、清晰度、完整性）
5. **Verifier**: 针对产物和约束运行自动化检查
6. **Judge**: 产生最终裁决（DONE/RETRY/ESCALATE）和原因代码
7. **Operator**: 维护平台健康（熔断器、降级策略、队列管理）

**权限矩阵**:

| 角色 | 创建任务 | 修改仓库 | 运行测试 | 更改Pins | 发布裁决 |
|------|----------|----------|----------|----------|----------|
| Requester | Yes | No | No | No | No |
| Planner | Yes | No | No | No | No |
| Executor | No | Yes (范围内) | Yes (允许) | No | No |
| Reviewer | No | No | No | No | No |
| Verifier | No | No | Yes | No | No |
| Judge | No | No | No | No | Yes |
| Operator | Yes | Yes (仅运维) | Yes | Yes (策略) | No |

#### 事件系统

**常见事件类型**:

- **TASK_CREATED**: 新任务添加到看板/待办
- **TASK_READY**: 任务先决条件已满足；符合分发条件
- **TASK_STARTED**: 执行器开始工作；转换为 `in_progress`
- **TASK_PROGRESS**: 执行期间的定期更新（可选）
- **TASK_BLOCKED**: 执行无法继续（缺少输入/范围/工具）
- **TASK_FAILED**: 执行失败；包括原因代码和证据指针
- **TASK_RETRIED**: 重试尝试已计划或开始
- **TASK_ESCALATED**: 任务移至升级路径（隔离/DLQ）
- **TASK_COMPLETED**: 已生成提交；等待验证/裁决
- **VERIFICATION_PASSED**: 所有必需检查通过
- **VERIFICATION_FAILED**: 至少一项检查失败
- **VERDICT_ISSUED**: 裁决者发出 DONE/RETRY/ESCALATE

---

## 17.3 核心功能与脚本

### 17.3.1 OID管理功能

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| OID生成 | 通过HTTP API生成OID | `oid_generator.py` | `python tools/scc/ops/oid_generator.py new --path <path> --kind md --layer CANON` |
| OID验证 | 验证OID格式和注册表 | `oid_validator.py` | `python tools/scc/ops/oid_validator.py --oid 01ARZ3NDEKTSV4RRFFQ69G5FAV` |
| OID迁移 | 处理文件移动/重命名 | `oid_migrate.py` | `python tools/scc/ops/oid_migrate.py --from <old_path> --to <new_path>` |
| 注册表查询 | 查询PostgreSQL注册表 | `oid_query.py` | `python tools/scc/ops/oid_query.py --path <path>` |

### 17.3.2 Unit管理功能

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| Unit验证 | 验证Unit是否注册 | `unit_validator.py` | `python tools/scc/ops/unit_validator.py --unit A.EXECUTOR` |
| Unit查询 | 查询Unit定义 | `unit_query.py` | `python tools/scc/ops/unit_query.py --stream A` |
| 注册表更新 | 更新Unit Registry | `unit_registry_update.py` | `python tools/scc/ops/unit_registry_update.py --add A.NEW_UNIT` |

### 17.3.3 文档治理功能

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 文档注册 | 将新文档加入注册表 | `doc_registry.py` | `python tools/scc/ops/doc_registry.py register --file <path> --type spec` |
| 文档查询 | 按条件查询文档 | `doc_query.py` | `python tools/scc/ops/doc_query.py --type spec --status PUBLISHED` |
| 状态流转 | 变更文档状态 | `doc_transition.py` | `python tools/scc/ops/doc_transition.py --oid <oid> --to APPROVED` |
| 一致性检查 | 检查SSOT一致性 | `ssot_consistency_check.py` | `python tools/scc/ops/ssot_consistency_check.py --all` |

---

## 17.4 脚本使用示例

### 17.4.1 OID生成与验证

```bash
# 1. 生成新OID（用于新文档）
python tools/scc/ops/oid_generator.py new \
  --path "docs/CANONICAL/GOALS.md" \
  --kind md \
  --layer CANON \
  --primary_unit G.GOAL_INPUT \
  --tags '["S.CANONICAL_UPDATE"]' \
  --stable_key "docs/CANONICAL/GOALS.md"
# 输出: {"oid": "01KGCV31F255AQQB7JQXKHWB05", "issued": true}

# 2. 验证OID有效性（格式 + 注册表）
python tools/scc/ops/oid_validator.py \
  --oid 01KGCV31F255AQQB7JQXKHWB05 \
  --check-postgres \
  --verbose

# 3. 通过路径查询OID
python tools/scc/ops/oid_query.py \
  --path "docs/CANONICAL/GOALS.md" \
  --format json

# 4. 处理文件重命名（OID迁移）
python tools/scc/ops/oid_migrate.py \
  --from "docs/old_name.md" \
  --to "docs/new_name.md" \
  --update-path-only
```

### 17.4.2 Unit查询与验证

```bash
# 1. 查询所有Agent角色Unit
python tools/scc/ops/unit_query.py \
  --stream A \
  --format table

# 2. 验证Unit是否有效
python tools/scc/ops/unit_validator.py \
  --unit A.EXECUTOR \
  --check-primary

# 3. 验证文档的Unit标签
python tools/scc/ops/unit_validator.py \
  --file "docs/ssot/01_conventions/OID_SPEC__v0.1.0.md" \
  --check-all-tags
```

### 17.4.3 文档治理操作

```bash
# 1. 注册新文档到SSOT
python tools/scc/ops/doc_registry.py register \
  --file "docs/new_spec.md" \
  --type spec \
  --owner "dev-team@example.com" \
  --auto-generate-oid

# 2. 查询所有已发布的规范文档
python tools/scc/ops/doc_query.py \
  --type spec \
  --status PUBLISHED \
  --format table \
  --sort updated_at:desc

# 3. 将文档从审核中转为已批准
python tools/scc/ops/doc_transition.py \
  --oid 01KGCV31F255AQQB7JQXKHWB05 \
  --to APPROVED \
  --approver "lead@example.com" \
  --reason "Review passed"

# 4. 检查SSOT一致性（全系统）
python tools/scc/ops/ssot_consistency_check.py \
  --all \
  --fix-auto \
  --report inconsistencies.json
```

---

## 17.5 关键文件针脚

```yaml
L17_ontology_layer:
  ssot_partition: "01_conventions"
  chapter: 2
  description: "知识与本体层 - 提供术语、ID体系、实体关系定义"
  
  core_spec_files:
    - path: scc-top/docs/ssot/01_conventions/OID_SPEC__v0.1.0.md
      oid: 01KGCV31F255AQQB7JQXKHWB05
      primary_unit: V.OID_VALIDATOR
      description: "OID/ULID规范定义"
    - path: scc-top/docs/ssot/01_conventions/UNIT_REGISTRY__v0.1.0.md
      oid: 01KGCV31G462QJYM5HBWGSSDN3
      primary_unit: N.EVENTS
      description: "Unit注册表，定义13个Stream和40+Unit"
    - path: scc-top/docs/ssot/01_conventions/DOCFLOW_SSOT__v0.1.0.md
      description: "文档流SSOT规范"
    - path: scc-top/docs/ssot/01_conventions/DOC_REGISTRY__v0.1.0.md
      description: "文档注册表规范"
    - path: scc-top/docs/ssot/01_conventions/SINGLE_TRUTH_PRIORITY__v0.1.0.md
      description: "单一事实优先级规则"
  
  related_files:
    - path: scc-top/docs/ssot/04_contracts/OID_SPEC__v0.1.0.md
      note: "Contracts分区的OID_SPEC跳转文件，指向01_conventions版本"
  
  tools:
    oid_management:
      - tools/scc/ops/oid_generator.py
      - tools/scc/ops/oid_validator.py
      - tools/scc/ops/oid_migrate.py
      - tools/scc/ops/oid_query.py
    unit_management:
      - tools/scc/ops/unit_validator.py
      - tools/scc/ops/unit_query.py
      - tools/scc/ops/unit_registry_update.py
    doc_governance:
      - tools/scc/ops/doc_registry.py
      - tools/scc/ops/doc_query.py
      - tools/scc/ops/doc_transition.py
      - tools/scc/ops/ssot_consistency_check.py
  
  postgresql_tables:
    - objects: "OID权威注册表"
    - oid_events: "OID事件日志（ISSUED/MIGRATED/COLLISION）"
  
  related_chapters:
    - technical_manual/chapter_02_ontology_layer.md
```

---

## 17.6 本章小结

### 17.6.1 核心概念

| 概念 | 说明 | 来源文件 |
|------|------|----------|
| OID | 对象标识符，即ULID | OID_SPEC__v0.1.0.md |
| ULID | 26字符Crockford's Base32编码 | OID_SPEC__v0.1.0.md |
| Unit | 功能单元标识，格式为Stream.Unit | UNIT_REGISTRY__v0.1.0.md |
| Stream | 13个业务流程流 | UNIT_REGISTRY__v0.1.0.md |
| primary_unit | 每个对象必须有且只有一个 | OID_SPEC__v0.1.0.md |
| tags | 可选的多选Unit标签 | OID_SPEC__v0.1.0.md |
| object_index | PostgreSQL中的权威注册表 | OID_SPEC__v0.1.0.md |

### 17.6.2 关键规则

1. **OID唯一性**: 所有OID必须由SCC OID Generator生成，禁止自行生成
2. **PostgreSQL权威**: object_index表是OID的唯一权威来源
3. **Unit验证**: 所有primary_unit和tags必须存在于Unit Registry
4. **SSOT优先级**: PostgreSQL > 内联YAML > 文件路径 > 缓存
5. **文档生命周期**: DRAFT → REVIEW → APPROVED → PUBLISHED → ARCHIVED

### 17.6.3 依赖关系

```
L17 知识与本体层（基础层）
    │
    ├─ 提供OID/ULID体系给 → L1-L16所有层
    ├─ 提供Unit定义给 → L6 Agent层, L11 调度层
    ├─ 提供文档治理给 → L3 文档层
    └─ 提供实体关系给 → L8 证据层, L14 质量层
```

---

**导航**: [← L16](./L16_observability_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L1](./L1_code_layer.md)