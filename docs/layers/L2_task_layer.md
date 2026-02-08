# L2 任务层

> **对应SSOT分区**: `04_contracts/`（契约文档）  
> **对应技术手册**: 第10章  
> **层定位**: 任务定义、契约管理、任务生命周期

---

## 2.1 层定位与职责

### 2.1.1 核心职责

L2是SCC架构的**任务管理层**，为全系统提供：

1. **任务模型** - 任务层级结构（EPIC→CAPABILITY→COMPONENT→TASK）
2. **契约规范** - 可执行任务的最小契约定义
3. **任务生命周期** - 任务状态机管理
4. **任务标识** - task_id生成与绑定规则

### 2.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L2 任务层                                     │
│ ├─ 任务模型（层级结构）                       │
│ ├─ 契约规范（最小字段）                       │
│ ├─ 任务生命周期（状态机）                     │
│ └─ 任务标识（task_id）                        │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L6 Agent层, L11 调度层, L12 成本层           │
└─────────────────────────────────────────────┘
```

---

## 2.2 来自04_contracts/的核心内容

### 2.2.1 任务模型与代码

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/04_contracts/task_model.md` | 任务模型定义 | 层级结构、task_id规则、状态机 |
| `ssot/04_contracts/task_tree.md` | 任务树结构 | EPIC/CAPABILITY/TASK树的具体组织 |
| `ssot/04_contracts/TASK_MODEL_CODES__v0.1.0.md` | 任务模型代码 | 任务代码规范 |

#### 任务层级（强制）

```
层级结构（从上到下）：
┌─────────────┐
│    EPIC     │  ← 长期主题
├─────────────┤
│  CAPABILITY │  ← 可交付能力包
├─────────────┤
│ COMPONENT/  │  ← 系统模块或可重复作业
│    JOB      │
├─────────────┤
│    TASK     │  ← 原子可执行工作项
└─────────────┘
```

#### task_id规则（强制）

```yaml
task_id生成与稳定性:
  - 相同意图的task_id在重试中必须保持稳定
  - 必须从稳定键（source + stable_key）幂等生成
  
跨intake绑定（最小）:
  web_chat: "(conversation_id, message_id) 或引用指令的稳定哈希"
  codexcli: "(run_id, workspace_root, contract_ref)"
  vscode: "(session_id, workspace_root, contract_ref)"
  
去重规则: "多个来源引用相同意图时，必须解析为一个task_id"
```

#### 必需标识符（强制）

| 字段 | 说明 |
|------|------|
| task_id | 唯一标识符 |
| contract_ref | 链接/路径/oid到契约 |
| touched_oids | 修改/创建的对象oid列表 |
| evidence_oids | 产生/使用的证据oid列表 |

#### 任务状态机

```
状态流转：
queued → started → produced → verified(pass|fail) → done | dlq

最小事件类型：
- TASK_QUEUED
- TASK_STARTED
- TASK_PRODUCED（产生diff/log）
- TASK_VERIFIED（记录裁决）
- TASK_DONE
- TASK_DLQ（死信）
```

### 2.2.2 契约最小规范

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/04_contracts/contract_min_spec.md` | 契约最小规范 | 可执行任务的最小字段 |
| `ssot/04_contracts/CONTRACT_MIN_SPEC__v0.1.0.md` | 契约规范（规范版） | 同上，规范格式 |
| `ssot/04_contracts/contract.schema.json` | 契约Schema | 机器可读Schema |

#### 最小字段（强制）

```yaml
契约必须包含：
  goal: "要实现什么"
  project_id: "属于哪个生产项目（必须存在于catalog）"
  scope_allow: "允许的更改（或EMPTY）"
  constraints: "硬约束"
  acceptance: "可执行检查（机器导向；命令+证据期望）"
  stop_condition: "何时停止/故障关闭规则"
  commands_hint: "执行器/验证器的建议命令"

必需引用：
  inputs_ref: "需要的pins/map/paths/oids"
  outputs_expected: "期望的工件/裁决"
```

#### 验证器规则（强制）

```
验证器必须仅根据acceptance结果进行裁决。
禁止不带检查的"looks good"裁决。
```

#### 契约模板

```yaml
goal:
project_id:
scope_allow:
constraints:
acceptance:
stop_condition:
commands_hint:
inputs_ref:
outputs_expected:
```

### 2.2.4 Task Bundle 结构

Task Bundle是可执行的最小任务单元：

```
task_bundle/
├── task_contract.json      # 任务合同（Goal/Non-goal/Done/Stop/Scope）
├── pins.json               # 代码定位信息
├── allowlist.txt           # 允许修改列表
├── acceptance.md           # 验收标准
├── tool_allowlist.json     # 允许工具
└── input/                  # 输入文件
```

#### Task Bundle 组件说明

| 文件 | 说明 | 必需 |
|------|------|------|
| task_contract.json | 任务合同，定义目标、范围、约束 | 是 |
| pins.json | 代码定位，精确到文件/行/符号 | 是 |
| allowlist.txt | 允许修改的文件路径列表 | 是 |
| acceptance.md | 验收标准和检查清单 | 是 |
| tool_allowlist.json | 允许使用的工具列表 | 否 |
| input/ | 输入文件目录 | 否 |

### 2.2.5 任务生命周期

```
Created → Ready → In Progress → Selftest → Verification → Done
   ↑          ↓         ↓           ↓            ↓
   └──── Blocked ←─────┴──── Failed ←───────────┘
```

#### 状态说明

| 状态 | 说明 | 转换条件 |
|------|------|----------|
| Created | 任务已创建 | 初始状态 |
| Ready | 准备就绪 | 契约验证通过 |
| In Progress | 执行中 | Agent开始执行 |
| Selftest | 自测阶段 | 执行完成，运行测试 |
| Verification | 验证阶段 | 自测通过，等待验证 |
| Done | 完成 | 验证通过 |
| Blocked | 阻塞 | 依赖未满足或需要输入 |
| Failed | 失败 | 执行失败或验证失败 |

### 2.2.6 Task Bundle 规范详情

#### 目录结构

```
task_bundle/
├── task_contract.json          # 任务合同（必需）
├── pins.json                   # 代码定位（必需）
├── allowlist.txt               # 允许修改列表（必需）
├── acceptance.md               # 验收标准（必需）
├── tool_allowlist.json         # 允许工具（必需）
├── context_budget.json         # 上下文预算（可选）
└── input/                      # 输入文件（可选）
```

#### task_contract.json 结构

```json
{
  "contract_id": "oid:L2:Contract:01ARZ...",
  "task_id": "oid:L2:Task:01ARZ...",
  "version": "v1.0.0",
  "goal": "实现用户认证功能",
  "non_goals": ["不实现OAuth", "不实现多因素认证"],
  "done_definition": ["通过所有测试", "通过代码审查"],
  "stop_conditions": ["超过预算", "发现设计缺陷"],
  "scope": {
    "included": ["src/auth/*.js"],
    "excluded": ["src/auth/oauth.js"]
  },
  "constraints": {
    "max_files": 5,
    "max_lines": 200,
    "tech_stack": ["nodejs", "typescript"]
  }
}
```

### 2.2.7 Pins 规范

**Pins** 是任务范围内的文件访问控制声明。

#### Pins 结构

```json
{
  "allowed_paths": ["src/gateway.mjs", "src/utils/*.mjs", "docs/**"],
  "forbidden_paths": ["**/secrets/**", "node_modules/**"]
}
```

#### 字段语义

- `allowed_paths`: 授予访问权限的路径模式列表
- `forbidden_paths`: 明确拒绝访问的路径模式列表
- 如果 `allowed_paths` 为空，**无论 `forbidden_paths` 如何，都无法访问任何文件**

#### Glob 语法

- `*` 匹配单个目录段内的内容（例如：`src/*.ts` 匹配 `src/a.ts` 但不匹配 `src/x/a.ts`）
- `**` 匹配跨多个目录段的内容（例如：`docs/**` 匹配 `docs/a.md` 和 `docs/x/a.md`）

### 2.2.8 Task Contract 规范

任务合同定义了执行Agent与SCC系统运行时之间的规范性"任务合同"。

#### 合同结构

```
Task Contract = {
  task_id:           唯一标识符
  goal:              任务目标（自然语言）
  role:              执行角色
  pins:              允许的文件路径（范围边界）
  allowed_tests:     必须通过测试/命令
  allowed_models:    可使用的模型列表
  allowed_executors: 可运行任务的执行器列表
  timeout:           时间限制
  max_attempts:      最大重试次数
}
```

#### 字段语义

| 字段 | 含义 | 验证期望 |
|------|------|----------|
| `task_id` | 用于审计和可追溯性的全局唯一标识符 | 必须存在且在重试期间保持稳定 |
| `goal` | 预期结果，用自然语言编写 | 必须足够具体以确定完成情况 |
| `role` | 用于执行的权限/行为配置文件 | 必须与通道允许的角色匹配 |
| `pins` | 范围边界：Agent可以读/写的路径 | 由策略强制执行；违规即违约 |
| `allowed_tests` | 定义质量门的命令 | 必须由系统执行并记录 |
| `allowed_models` | 允许的模型标识符 | 系统必须强制执行；Agent必须遵守 |
| `timeout` | 合同处于活动状态的最大挂钟预算 | 由系统终止强制执行 |
| `max_attempts` | 升级或中止前的重试次数限制 | 由系统编排强制执行 |

---

## 2.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 任务创建 | 基于模板创建任务 | `task_creator.py` | `python tools/scc/ops/task_creator.py --epic <epic_id> --goal "..."` |
| 任务查询 | 查询任务树 | `task_query.py` | `python tools/scc/ops/task_query.py --task-id <task_id>` |
| 契约验证 | 验证契约完整性 | `contract_validator.py` | `python tools/scc/ops/contract_validator.py --contract <path>` |
| 契约生成 | 从目标生成契约 | `contract_generator.py` | `python tools/scc/ops/contract_generator.py --goal "..." --project <id>` |
| 状态流转 | 更新任务状态 | `task_transition.py` | `python tools/scc/ops/task_transition.py --task-id <id> --to started` |
| task_id生成 | 生成稳定task_id | `task_id_generator.py` | `python tools/scc/ops/task_id_generator.py --source web_chat --stable-key "..."` |

---

## 2.4 脚本使用示例

```bash
# 1. 创建新任务（在EPIC下）
python tools/scc/ops/task_creator.py \
  --epic EPIC-001 \
  --capability CAP-001 \
  --goal "实现用户认证模块" \
  --project-id quantsys \
  --auto-generate-task-id

# 2. 查询任务树（从EPIC到TASK）
python tools/scc/ops/task_query.py \
  --epic EPIC-001 \
  --depth 3 \
  --format tree \
  --include-status

# 3. 验证契约完整性
python tools/scc/ops/contract_validator.py \
  --contract contracts/task_001.yaml \
  --check-project \
  --check-acceptance \
  --verbose

# 4. 从自然语言目标生成契约
python tools/scc/ops/contract_generator.py \
  --goal "修复登录页面的CSS样式问题" \
  --project-id yme \
  --scope-allow "frontend/css" \
  --output contract.yaml

# 5. 更新任务状态（带证据）
python tools/scc/ops/task_transition.py \
  --task-id TASK-001 \
  --to verified \
  --verdict pass \
  --evidence-oids '["EVID-001", "EVID-002"]' \
  --touched-oids '["FILE-001"]'

# 6. 生成稳定task_id
python tools/scc/ops/task_id_generator.py \
  --source web_chat \
  --conversation-id conv_123 \
  --message-id msg_456 \
  --intent-hash "fix login css"
```

---

## 2.5 关键文件针脚

```yaml
L2_task_layer:
  ssot_partition: "04_contracts"
  chapter: 10
  description: "任务层 - 提供任务模型、契约规范、任务生命周期管理"
  
  core_spec_files:
    - path: scc-top/docs/ssot/04_contracts/task_model.md
      oid: 01KGCV31SY172FN22A81WSMR13
      layer: CANON
      primary_unit: D.TASKTREE
      description: "任务模型定义，层级结构、task_id规则、状态机"
    - path: scc-top/docs/ssot/04_contracts/contract_min_spec.md
      oid: 01KGCV31RXZTJZS7V7VEP80C9X
      layer: CANON
      primary_unit: K.CONTRACT_DOC
      description: "契约最小规范，可执行任务的最小字段"
    - path: scc-top/docs/ssot/04_contracts/task_tree.md
      description: "任务树结构详细说明"
    - path: scc-top/docs/ssot/04_contracts/CONTRACT_MIN_SPEC__v0.1.0.md
      description: "契约规范（规范格式版）"
  
  schema_files:
    - path: scc-top/docs/ssot/04_contracts/contract.schema.json
      description: "契约Schema（机器可读）"
  
  tools:
    - tools/scc/ops/task_creator.py
    - tools/scc/ops/task_query.py
    - tools/scc/ops/contract_validator.py
    - tools/scc/ops/contract_generator.py
    - tools/scc/ops/task_transition.py
    - tools/scc/ops/task_id_generator.py
  
  related_chapters:
    - technical_manual/chapter_10_task_layer.md
```

---

## 2.6 本章小结

### 2.6.1 核心概念

| 概念 | 说明 | 来源文件 |
|------|------|----------|
| EPIC | 长期主题 | task_model.md |
| CAPABILITY | 可交付能力包 | task_model.md |
| COMPONENT/JOB | 系统模块或可重复作业 | task_model.md |
| TASK | 原子可执行工作项 | task_model.md |
| task_id | 稳定任务标识符 | task_model.md |
| contract_ref | 契约引用 | contract_min_spec.md |
| acceptance | 可执行检查 | contract_min_spec.md |

### 2.6.2 关键规则

1. **层级强制**: 所有工作必须定位在 EPIC→CAPABILITY→COMPONENT→TASK 层次结构中
2. **task_id稳定**: 相同意图的task_id在重试中必须保持稳定
3. **契约必须字段**: goal, project_id, scope_allow, constraints, acceptance, stop_condition, commands_hint
4. **验证器规则**: 必须仅根据acceptance结果进行裁决
5. **完成回填**: 每个完成的TASK必须回填contract_ref, touched_oids, evidence_oids, verdict

### 2.6.3 依赖关系

```
L2 任务层
    │
    ├─ 依赖 → L1代码层（project_id必须在catalog中）
    ├─ 依赖 → L17本体层（task_id生成使用OID体系）
    │
    ├─ 提供任务定义给 → L6 Agent层
    ├─ 提供契约给 → L4提示词层, L11调度层
    ├─ 提供task_id给 → L8证据层, L12成本层
    └─ 提供acceptance给 → L14质量层
```

### 2.2.9 Task Model与Codes（来自SSOT）

**层级结构（强制）**:
- **EPIC**: 长期主题
- **CAPABILITY**: 可交付能力包
- **COMPONENT/JOB**: 系统模块或可重复作业
- **TASK**: 原子可执行工作项

**task_id规则（强制）**:
- 同一意图在重试间必须稳定
- 必须从稳定密钥（source + stable_key）幂等生成
- 跨来源绑定：Web chat用`(conversation_id, message_id)`，codexcli用`(run_id, workspace_root, contract_ref)`

**必需标识符**:
- `task_id`: 唯一
- `contract_ref`: 合同链接/路径/oid
- `touched_oids`: 修改/创建的对象oid列表
- `evidence_oids`: 产生/使用的证据oid列表

**状态机**:
```
queued → started → produced → verified(pass|fail) → done | dlq
```

**最小事件类型**:
- TASK_QUEUED, TASK_STARTED, TASK_PRODUCED, TASK_VERIFIED, TASK_DONE, TASK_DLQ

---


---

**导航**: [← L1](./L1_code_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L3](./L3_documentation_layer.md)