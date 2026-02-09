# L3 文档层

> **对应SSOT分区**: `01_conventions/`（约定规范 - 文档治理部分）  
> **对应技术手册**: 第8章  
> **层定位**: 文档生命周期、SSOT治理、文档注册表

---

## 3.1 层定位与职责

### 3.1.1 核心职责

L3是SCC架构的**文档治理层**，为全系统提供：

1. **文档生命周期管理** - DRAFT→REVIEW→APPROVED→PUBLISHED→ARCHIVED
2. **SSOT治理** - 单一事实来源优先级规则
3. **文档注册表** - 文档元数据管理和索引
4. **文档流规范** - 文档创建→审核→发布→归档的完整流程
5. **目录分层** - 统一的文档落点规范

### 3.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L3 文档层                                     │
│ ├─ 文档生命周期（状态机）                     │
│ ├─ SSOT治理（优先级规则）                     │
│ ├─ 文档注册表（索引）                         │
│ └─ 目录分层规范                               │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L1, L2, L17 等所有涉及文档的层               │
└─────────────────────────────────────────────┘
```

---

## 3.2 来自01_conventions/的核心内容

### 3.2.1 文档流SSOT规范

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/01_conventions/DOCFLOW_SSOT__v0.1.0.md` | 文档流SSOT规范 | 唯一入口、目录分层、命名规则、一致性门禁 |
| `ssot/01_conventions/DOC_REGISTRY__v0.1.0.md` | 文档注册表规范 | 权威索引文件、使用方式、维护规则 |

#### 唯一入口（不再增加新的入口页）

```
允许的SSOT入口：
├── docs/START_HERE.md                          ← 总入口
├── docs/arch/00_index.md                       ← 架构/运维入口
├── docs/arch/project_navigation__v0.1.0__...   ← 项目导航入口
├── docs/INPUTS/README.md                       ← 外部输入入口
└── docs/INPUTS/WEBGPT/index.md                 ← WebGPT输入入口
    └── docs/INPUTS/WEBGPT/memory.md            ← WebGPT记忆

其余README/报告只能链接到以上入口，不得成为新的"主入口"。
```

#### 目录分层（落点统一）

| 目录 | 用途 | 内容类型 | 变更频率 |
|------|------|----------|----------|
| `docs/arch/` | 规范/设计/协议 | 系统应该如何运作 | 低，必须稳定 |
| `docs/spec/` | 机器可读合约 | JSON Schema、接口规范 | 中 |
| `docs/INPUTS/` | 外部输入 | 需求原文、会议纪要 | 高，增量更新 |
| `artifacts/` | 事实源 | SQLite、jsonl、logs | 运行时生成 |
| `evidence/` | 证据 | 回执、状态文件 | 审计追踪 |

#### 命名规则

**规范型文档（强制版本化）**:
```
格式: NAME__v0.1.0.md 或 NAME__v0.1.0__YYYYMMDD.md
必须包含:
- 目标
- 范围
- 入口链接
- 落点约定
- 验收/失败模式
```

**报告型文档（可生成）**:
```
格式: REPORT__TOPIC__v0.1__YYYYMMDD.md
规则: 只能引用规范与证据，不得替代规范
```

**外部输入文档**:
```
位置: docs/INPUTS/...
必须包含:
- source（来源）
- captured_at（时间戳）
- page_url（若适用）
禁止: 把推理结果混进原文
```

#### 一致性门禁（最低要求）

任何新增/修改规范型文档必须满足：
1. 从 `docs/START_HERE.md` 或 `docs/arch/00_index.md` 可到达（可发现）
2. 指向明确的事实源（例如 `artifacts/...`、schema、脚本入口）
3. 不引入第二个"主入口"页面

### 3.2.2 文档注册表规范

#### 权威索引文件

```
文件: docs/ssot/registry.json（alias: docs/ssot/_registry.json）

用途:
- 机器可读索引
- 让本地模型/agent稳定拼装上下文
- 确保"权威路径唯一"
```

#### AI拼装上下文流程

```
1) 固定先读: docs/START_HERE.md
2) 再读顶层治理: docs/ssot/02_architecture/SCC_TOP.md
3) 再读Docflow规则: docs/ssot/01_conventions/DOCFLOW_SSOT__v0.1.0.md
4) 按_registry.json选择相关leaf docs（按EPIC/CAPABILITY/COMPONENT/JOB/TASK）
5) 注入输入: docs/INPUTS/...
6) 证据只从: artifacts/... / evidence/... 读取与引用
```

#### 维护规则

- `_registry.json` 只记录"权威路径"和"拼装顺序"，不复制长文内容
- 任意新增规范/作业手册，必须：
  - 放入 `docs/ssot/` 的对应分区（canonical）
  - 在 `_registry.json` 登记 doc_id 与 canonical_path
  - 从 `docs/START_HERE.md` 可达（直接或经分区索引）

### 3.2.3 文档策略（Hard Policies）

#### 策略一：禁止直接修改 SSOT

**规则**: 只有 `ssot_curator` 角色可以直接修改 SSOT（单一事实来源）文档。

**违反后果**:
- **立即失败**: 任务标记为 FAILED
- **失败码**: `UNAUTHORIZED_SSOT_ACCESS`
- **审计**: 记录安全事件

**例外**: `designer` 可以通过正式流程提交 SSOT 修改建议，但必须经过 `ssot_curator` 审核并执行。

#### 策略二：禁止超出 Pins 范围修改

**规则**: Executor 只能修改 Pins 明确指定的代码范围。

**违反后果**:
- **立即失败**: 任务标记为 FAILED
- **失败码**: `OUT_OF_SCOPE_MODIFICATION`
- **重试**: 必须重新生成 Pins 并重新执行

**示例**:
```
✅ 允许: Pins 指定 src/utils.js L10-L20，修改 L15
❌ 禁止: Pins 指定 src/utils.js L10-L20，修改 src/other.js
❌ 禁止: Pins 指定 src/utils.js L10-L20，修改 L50
```

#### 策略三：禁止访问 Secrets

**规则**: 除 `auditor`（仅元数据）外，任何角色禁止直接访问 Secrets 值。

**违反后果**:
- **立即失败**: 任务标记为 FAILED
- **失败码**: `UNAUTHORIZED_SECRET_ACCESS`
- **安全事件**: 触发安全告警
- **角色冻结**: 可能暂时冻结角色权限

**合法访问方式**:
- 通过环境变量注入
- 通过 Vault 动态凭证
- 通过只读挂载

#### 策略四：禁止无版本引用

**规则**: 所有文档、代码、契约引用必须包含版本标识。

**违反后果**:
- **CI 失败**: 门禁阻止提交
- **失败码**: `UNVERSIONED_REFERENCE`
- **要求**: 补充版本信息后重新提交

**版本格式**:
```
docs/spec.md@v1.2.0
src/code.js#abc123
contracts/task.json@schema-v2
```

#### 策略五：禁止绕过门禁

**规则**: 任何情况下禁止绕过 CI 门禁和验证流程。

**违反后果**:
- **立即失败**: 任务标记为 FAILED
- **失败码**: `GATE_BYPASS_ATTEMPT`
- **审计**: 记录为严重安全事件
- **系统降级**: 可能触发熔断机制

**无例外**: 即使紧急情况也不允许绕过门禁。

#### 策略六：禁止修改工厂配置

**规则**: 只有 `factory_manager` 角色可以修改工厂配置。

**违反后果**:
- **立即失败**: 任务标记为 FAILED
- **失败码**: `UNAUTHORIZED_FACTORY_CONFIG`
- **回滚**: 自动回滚配置变更

**配置范围**:
- `factory_policy.json`
- 路由规则
- WIP 限制
- 熔断阈值

#### 策略七：禁止执行未验证代码

**规则**: 禁止执行未通过门禁验证的代码或脚本。

**违反后果**:
- **立即失败**: 任务标记为 FAILED
- **失败码**: `UNVERIFIED_CODE_EXECUTION`
- **隔离**: 相关代码被隔离审查

#### 策略八：禁止删除审计日志

**规则**: 审计日志不可删除、不可修改，只能归档。

**违反后果**:
- **系统故障**: 视为系统级故障
- **失败码**: `AUDIT_LOG_TAMPERING`
- **人工介入**: 必须人工调查

---

### 3.2.4 AI拼装上下文流程

按固定顺序拼装上下文（从"规则"到"事实"）：

1. **读取分区索引**（START_HERE.md → SSOT Trunk）
2. **读取相关 leaf docs**（规范/合约/作业手册）
   - 机器可读索引：`docs/ssot/registry.json`
3. **注入外部输入**（`docs/INPUTS/`）
4. **只从 `artifacts/`/`evidence/` 取事实与证据**

#### SSOT Trunk（7分区固定结构）

| 分区 | 路径 | 内容 | 对应层 |
|------|------|------|--------|
| SCC_TOP | `docs/ssot/02_architecture/SCC_TOP.md` | 顶层宪法、North Star | L1 |
| 01 Conventions | `docs/ssot/01_conventions/` | 约定规范、OID/ULID | L3, L17 |
| 02 Architecture | `docs/ssot/02_architecture/` | 架构文档、项目组 | L1, L5, L10, L11 |
| 03 Agent Playbook | `docs/ssot/03_agent_playbook/` | 角色/技能/交接模板 | L4, L6, L9 |
| 04 Contracts | `docs/ssot/04_contracts/` | 任务模型、契约规范 | L2, L13 |
| 05 Runbooks | `docs/ssot/05_runbooks/` | 运行手册、Manager Tools | L7, L12, L14, L15, L16 |
| 06 Inputs | `docs/ssot/06_inputs/` | 外部输入 | L10 |
| 07 Reports | `docs/ssot/07_reports_evidence/` | 报告与证据 | L8, L14, L16 |

---

### 3.2.5 冲突优先级规则（Conflict Order）

#### 优先级层级（从高到低）

| 层级 | 来源 | 优先级 | 冲突处理 | 示例 |
|------|------|--------|----------|------|
| **L0** | Constitution | 绝对最高 | 不可违反，违反即系统故障 | Pins-First原则 |
| **L1** | Hard Policies | 极高 | 违反即失败，任务终止 | 禁止直接修改SSOT |
| **L2** | Role Constraints | 高 | 超出角色权限即拒绝 | executor禁止读取SSOT |
| **L3** | Task Contracts | 中高 | 违反即重试或升级 | 验收标准、完成定义 |
| **L4** | Factory Policies | 中 | 违反触发熔断或降级 | WIP限制、泳道规则 |
| **L5** | Soft Policies | 低 | 偏好，不阻断，仅记录 | 优先使用TypeScript |
| **L6** | Best Practices | 最低 | 建议性，仅供参考 | 代码风格建议 |

#### 冲突解决流程

```
检测到冲突
    ↓
识别冲突双方层级
    ↓
层级不同？
    ├── 是 → 高优先级胜出
    ↓
层级相同？
    ├── 是 → 应用同层级规则（时间/特定/范围优先）
    ↓
记录冲突与决议
    ↓
执行胜出规则
```

#### 同层级冲突规则

- **时间优先**: 后发布的规则覆盖先发布的规则（适用L3-L6）
- **特定优先**: 特定规则覆盖一般规则（适用所有层级）
- **范围优先**: 小范围规则覆盖大范围规则（适用L2-L4）

---

### 3.2.6 清洁策略（Hygiene Policy）

**目标**: 将"整洁"变成机器可判定的门禁，降低复杂度与后期维护成本。

#### 产物与目录

- 运行产物仅允许落在 `artifacts/<task_id>/...`，默认 gitignore
- **必备产物**: `report.md`, `selftest.log`, `evidence/`, `patch.diff`, `submit.json`
- **禁止**在仓库根/源码目录生成: `tmp/`, `*.bak`, `*copy*`, `debug*`, 临时脚本等
- **TTL**: 产物默认保留 30 天，可归档/清理

#### 改动半径

- 每个任务必须声明 `write_allow_paths` / `read_allow_paths`（pins + contract）
- **CI 校验**: 改动超出 allowlist → 失败；新增文件必须有归属（manifest/submit.changed_files）

#### 协议与版本

- 控制面统一使用 JSON 信封，集中在 `contracts/`，带 `schema_version` 和 `kind`
- 破坏性变更必须新版本，旧版兼容（只增不删字段）

#### 依赖与 ADR

- 新增依赖/目录/协议变更必须写 ADR（`docs/adr/ADR-YYYYMMDD-<slug>.md`，6 行：Context/Decision/Alternatives/Consequences/Migration/Owner）

#### 清洁检查（CI/Preflight）

- `workspace_clean_check`: git 状态需干净（仅允许本任务改动），无垃圾文件
- `hygiene_validator`: 校验产物路径、allowlist 越界、临时文件、ADR 触发条件

#### 执行器合同补充

- 必须回传: `submit_json`（status/changed_files/tests/artifacts/exit_code/needs_input）
- 必须提供 changed_files、新增文件列表；无测试或仅 task_selftest 直接 fail-close

---

### 3.2.7 单一事实优先级

> **完整单一事实优先级定义**: 详见 [L17 知识与本体层 - 规范事实集](./L17_ontology_layer.md)
>
> L3关注文档流程中的优先级应用，完整的优先级规范在L17的canonical_truth.md中定义。

---

## 3.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 文档注册 | 将新文档加入注册表 | `doc_registry.py` | `doc_registry.py register --file <path> --type spec` |
| 文档查询 | 按条件查询文档 | `doc_query.py` | `doc_query.py --type spec --status PUBLISHED` |
| 状态流转 | 变更文档状态 | `doc_transition.py` | `doc_transition.py --oid <oid> --to APPROVED` |
| 一致性检查 | 检查SSOT一致性 | `ssot_consistency_check.py` | `ssot_consistency_check.py --all` |
| 文档流审计 | 快速自检 | `docflow_audit.ps1` | `docflow_audit.ps1 --check-links` |
| 入口验证 | 验证从START_HERE可达 | `entry_validator.py` | `entry_validator.py --all-docs` |

---

## 3.4 脚本使用示例

```bash
# 1. 注册新文档到SSOT
python tools/scc/ops/doc_registry.py register \
  --file "docs/arch/new_feature.md" \
  --type spec \
  --version "v0.1.0" \
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
  --oid 01KGCV31DYYFG8CWSKY61JC40J \
  --to APPROVED \
  --approver "lead@example.com" \
  --reason "Review passed"

# 4. 检查SSOT一致性（全系统）
python tools/scc/ops/ssot_consistency_check.py \
  --all \
  --check-registry \
  --check-links \
  --fix-auto \
  --report inconsistencies.json

# 5. 运行文档流审计
powershell tools/scc/ops/docflow_audit.ps1 \
  -CheckLinks \
  -CheckNaming \
  -CheckEntrypoints

# 6. 验证文档可从START_HERE到达
python tools/scc/ops/entry_validator.py \
  --doc-path "docs/arch/new_feature.md" \
  --start-from "docs/START_HERE.md"
```

---

## 3.5 关键文件针脚

```yaml
L3_documentation_layer:
  ssot_partition: "01_conventions"
  chapter: 8
  description: "文档层 - 提供文档生命周期、SSOT治理、文档注册表管理"
  
  core_spec_files:
    - path: scc-top/docs/ssot/01_conventions/DOCFLOW_SSOT__v0.1.0.md
      oid: 01KGCV31DYYFG8CWSKY61JC40J
      layer: DOCOPS
      primary_unit: S.CANONICAL_UPDATE
      description: "文档流SSOT规范，定义唯一入口、目录分层、命名规则"
    - path: scc-top/docs/ssot/01_conventions/DOC_REGISTRY__v0.1.0.md
      oid: 01KGEJFSP1YPV36VREP02TV54A
      layer: DOCOPS
      primary_unit: V.GUARD
      description: "文档注册表规范，定义权威索引文件和维护规则"
    - path: scc-top/docs/ssot/01_conventions/SINGLE_TRUTH_PRIORITY__v0.1.0.md
      oid: 01KGEJFSVJJC0KRCWQFGTPR0VJ
      layer: DOCOPS
      primary_unit: V.GUARD
      description: "单一事实优先级（已迁移到canonical_truth.md）"
  
  related_files:
    - path: scc-top/docs/ssot/02_architecture/canonical_truth.md
      oid: 01DFD8B9435F10410289743C65D7
      description: "规范事实集与冲突优先级（单一事实优先级的权威版本）"
    - path: scc-top/docs/ssot/registry.json
      oid: 01F24671BF70BA4E62B9283434F2
      description: "权威机器可读索引（alias: _registry.json）"
    - path: scc-top/docs/START_HERE.md
      oid: 01BF91ED2148924D359168758B8D
      description: "总入口"
    - path: scc-top/docs/arch/00_index.md
      oid: 01AFFEB401F90043FABB2D56E919
      description: "架构/运维入口"
  
  tools:
    - path: tools/scc/ops/doc_registry.py
      oid: 01D680CA819052462D9D6C2D8111
    - path: tools/scc/ops/doc_query.py
      oid: 0197C35D0C8CDE4389B50475EBCD
    - path: tools/scc/ops/doc_transition.py
      oid: 01C0F9631FF53F43C2B64EBBE9A6
    - path: tools/scc/ops/ssot_consistency_check.py
      oid: 017D8322D3018147E2942CC2126C
    - path: tools/scc/ops/docflow_audit.ps1
      oid: 0147DAAAB986EC4655A1B7C61A8B
    - path: tools/scc/ops/entry_validator.py
      oid: 0125A4BD5099F9471A859BF15E91
  
  related_chapters:
    - chapter: technical_manual/chapter_08_documentation_layer.md
      oid: 01F69BAE6DA23344698A6606D2D8
```

---

## 3.6 本章小结

### 3.6.1 核心概念

| 概念 | 说明 | 来源文件 |
|------|------|----------|
| 唯一入口 | START_HERE.md等5个固定入口 | DOCFLOW_SSOT__v0.1.0.md |
| 目录分层 | docs/arch/, docs/spec/, docs/INPUTS/, artifacts/, evidence/ | DOCFLOW_SSOT__v0.1.0.md |
| 版本化命名 | NAME__v0.1.0.md格式 | DOCFLOW_SSOT__v0.1.0.md |
| 注册表 | registry.json/_registry.json | DOC_REGISTRY__v0.1.0.md |
| SSOT优先级 | PostgreSQL > YAML > 路径 > 缓存 | canonical_truth.md |

### 3.6.2 关键规则

1. **唯一入口**: 只允许5个固定入口，不得增加新的主入口
2. **目录分层**: docs/只做入口与索引，不作为事实源
3. **命名强制**: 规范型文档必须版本化（__v0.1.0.md）
4. **一致性门禁**: 新文档必须从START_HERE可达
5. **证据分离**: 证据只存artifacts/和evidence/，不存docs/

### 3.6.3 依赖关系

```
L3 文档层
    │
    ├─ 依赖 → L17本体层（OID体系用于文档标识）
    │
    ├─ 提供文档治理给 → L1代码层（SCC_TOP维护）
    ├─ 提供注册表给 → L2任务层（契约文档注册）
    ├─ 提供目录规范给 → L10工作空间层
    └─ 提供SSOT规则给 → 所有其他层
```

---

**导航**: [← L2](./L2_task_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L4](./L4_prompt_layer.md)