# L1 代码层

> **对应SSOT分区**: `02_architecture/`（架构文档）  
> **对应技术手册**: 第17章  
> **层定位**: 系统顶层架构与治理

---

## 1.1 层定位与职责

### 1.1.1 核心职责

L1是SCC架构的**顶层治理层**，为全系统提供：

1. **北极星目标** - 系统整体目标定义
2. **全局结构** - 坐标系统、注册表、必要不变量
3. **更新与降级协议** - 如何保持TOP的权威性
4. **变更日志** - 显式的增/改/移/除记录

### 1.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L1 代码层（顶层治理）                         │
│ ├─ North Star（北极星目标）                  │
│ ├─ 全局结构/注册表                           │
│ ├─ 更新与降级协议                            │
│ └─ 变更日志                                  │
└──────────────────┬──────────────────────────┘
                   │ 指导
                   ▼
┌─────────────────────────────────────────────┐
│ L2-L17 所有其他层级                          │
└─────────────────────────────────────────────┘
```

---

## 1.2 来自02_architecture/的核心内容

### 1.2.1 SCC_TOP 顶层治理文档

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/02_architecture/SCC_TOP.md` | SCC顶层治理宪法 | 北极星目标、闭环阶段、SSOT权威链 |
| `ssot/02_architecture/PROJECT_GROUP__v0.1.0.md` | 项目组定义 | workspace_id、project_group、project_catalog |
| `ssot/02_architecture/SYSTEM_OVERVIEW.md` | 系统概览 | 系统整体架构描述 |

#### SCC_TOP 核心内容

**北极星目标**:
```
SCC是一个完全自动化的代码工厂，由文档流驱动：
Goal Intake → Task Derivation → Contract → Execute+Verify → Review → Synthesize Canonical → Feedback to Raw

人机协作规则：
- Web chat是最高优先级的目标输入源（最新意图）
- 自主驱动：仅允许在现有契约/待办事项内；不得覆盖人类目标
```

**闭环7阶段（S1-S7）**:

| 阶段 | 名称 | 说明 |
|------|------|------|
| S1 | Raw Intake | 原始输入接收 |
| S2 | Task Derivation | 任务派生 |
| S3 | Contract | 契约定义 |
| S4 | Execute + Verify | 执行与验证 |
| S5 | Review / Audit | 审查/审计 |
| S6 | Synthesize Canonical | 合成规范 |
| S7 | Feedback to Raw | 反馈到原始输入 |

**SSOT权威链**:
```
权威导航链（必须遵循）：
docs/START_HERE.md → docs/ssot/00_index.md → docs/ssot/_registry.json

SSOT Trunk是唯一规范的治理文档载体：
- conventions/architecture/playbook/contracts/runbooks/index
- 所有新治理内容必须落在 docs/ssot/ 下
- 必须可通过 START_HERE + registry.json 访问
- CI/verdict 必须运行 top_validator，故障关闭
```

### 1.2.2 项目组与工作空间

#### 工作空间身份（规范）

```yaml
workspace:
  workspace_id: "scc-top"
  workspace_root: "<REPO_ROOT>"
  # 注意：仓库目录名可变，但工作区身份以 workspace_id 为准

project_group:
  project_group_id: "scc-top-products"
  projects:
    - quantsys:      "量化金融（现有主工程）"
    - yme:           "YME连锁餐饮（产物项目）"
    - math_modeling: "数模竞赛（产物项目）"

# 权威机器索引
catalog: "docs/ssot/02_architecture/project_catalog.json"
```

#### 规则（必须）

1. 每个契约必须声明其 `project_id`（来自catalog）

### 1.2.3 降级规则（强制）

```
如果TOP的任何部分超过80行或约800字符：
- 将完整内容移到 docs/ssot/ 下的适当叶文档
- 在TOP中替换为1句话摘要+链接
- 在变更日志中记录"Moved/Demoted"，包括从TOP移除的内容和移动位置
```

### 1.2.4 本地融合编排（OC × SCC Local Gateway）

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `tools/oc-scc-local/` | 本地融合代码 | OpenCode UI/Server与SCC融合 |
| `docs/oc-scc-local/NAVIGATION.md` | 本地运行手册 | 镜像部署指南 |

#### 统一入口（默认端口18788）

```
用于把 OpenCode UI/Server 与 SCC 的任务分解/模型路由/执行器
在本机融合成一个入口（默认端口 18788）

核心端点:
- GET /config, POST /config/set - 配置管理
- GET /pools - 队长监控
- GET /executor/debug/metrics?hours=6 - 执行器指标
```

#### 配置入口

```bash
# 读取配置
GET http://127.0.0.1:18788/config

# 设置配置（写入tools/oc-scc-local/config/runtime.env，重启daemon生效）
POST http://127.0.0.1:18788/config/set
```

#### 监控端点

```bash
# 队长监控
GET http://127.0.0.1:18788/pools

# 执行器指标（最近6小时）
GET http://127.0.0.1:18788/executor/debug/metrics?hours=6
```

#### 完整API端点列表

**Control Plane**
- `/config` / `/config/set` - 配置管理
- `/models` / `/models/set` - 模型管理
- `/prompts/registry` / `/prompts/render` - 提示词注册表/渲染
- `/designer/state` / `/designer/freeze` - Designer状态
- `/designer/context_pack` - 上下文包
- `/scc/context/render` / `/scc/context/validate` - SCC上下文
- `/factory/policy` / `/factory/wip` / `/factory/degradation` / `/factory/health` - 工厂策略
- `/verdict?task_id=...` - 裁决查询
- `/routes/decisions` - 路由决策
- `/events` - 事件流

**Maps & Pins**
- `/map` / `/axioms` / `/task_classes` - 结构化索引
- `/map/v1` / `/map/v1/version` / `/map/v1/query?q=...` - Map v1
- `POST /pins/v1/build` - Pins Builder v1
- `POST /pins/v2/build` - Pins Builder v2（Audited）
- `POST /preflight/v1/check` - Preflight Gate v1

**Executor**
- `POST /executor/jobs/atomic` - 原子任务执行
- `GET /executor/prompt?task_id=...` - 获取提示词
- `GET /executor/leader` - 队长信息
- `GET /executor/debug/summary` - 执行器摘要
- `GET /executor/debug/failures` - 失败查询
- `GET /executor/workers` - Worker列表

**Upstreams**
- SCC: `/desktop` `/scc` `/dashboard` `/viewer` `/mcp/*`
- OpenCode: `/opencode/*` `/opencode/global/health`

#### CI/门禁

| 门禁 | 路径 | 说明 |
|------|------|------|
| 最小门禁 | `tools/scc/gates/run_ci_gates.py` | Contracts/Hygiene/Secrets/Events/SSOT/SSOT_MAP/DocLink/Map/Schema/Connectors/SemanticContext/Release |
| 硬合同门禁 | `tools/scc/gates/contracts_gate.py` | submit/preflight/pins/replay_bundle 必须存在且过 schema |
| 事件门禁 | `tools/scc/gates/event_gate.py` | 每个任务必须有 `artifacts/<task_id>/events.jsonl` |
| 密钥门禁 | `tools/scc/gates/secrets_gate.py` | 禁止明文 token/key |
| 出货门禁 | `tools/scc/gates/release_gate.py` | release record 必须过 schema |
| 连接器门禁 | `tools/scc/gates/connector_gate.py` | `connectors/registry.json` 必须存在且结构化合法 |

---

## 1.3 SCC Constitution（最高原则）

> **版本**: v1.0.0  
> **效力**: 最高，不可违反  
> **说明**: 所有其他规范、策略、合同必须服从这些原则

### 原则一：Pins-First 原则

**定义**: Executor 必须 pins-first，缺少 pins 直接失败，禁止自由扫描仓库。

**具体要求**:
1. 执行任务前必须提供有效的 pins
2. pins 必须包含路径、符号、行窗范围
3. 禁止基于模糊匹配或关键词搜索定位代码
4. 禁止"让我先看看代码结构"之类的自由探索

**违反后果**: 任务立即标记为 FAILED，失败码 `PINS_INSUFFICIENT`

### 原则二：Fail-Closed 原则

**定义**: 不确定时关闭而非开放，宁可失败也不冒险。

**具体要求**:
1. 权限检查失败 → 拒绝访问
2. 输入验证失败 → 拒绝处理
3. 依赖缺失 → 拒绝执行
4. 结果不确定 → 标记为 NEEDS_REVIEW

### 原则三：Evidence-Based 原则

**定义**: 所有决策必须基于可验证的证据，不接受解释性说明。

**具体要求**:
1. 所有裁决必须有证据支持
2. 证据必须包含文件路径、行号、内容片段
3. 禁止基于"我认为"、"应该可以"等主观判断
4. 证据必须可哈希验证

### 原则四：Versioned References 原则

**定义**: 所有引用必须带版本和哈希，确保可追溯、可回放。

**引用格式**:
```
docs/prompt_os/constitution.md@v1.0.0#abc123
roles/executor.json@v2.1.0#def456
```

### 原则五：Minimal Context 原则

**定义**: 只加载必要的上下文，通过 Compiler + Router 控制注入内容。

**上下文层级**:
- **Always-on**: legal_prefix + refs_index + io_digest
- **Conditional**: 根据任务类型动态注入
- **Never-on**: 长篇制度原文（默认不注入）

### 原则六：Binding Semantics 原则

**定义**: 所有规范必须具有语义效力，明确优先级和违规后果。

**效力层级**:
1. **Constitution** - 不可违反
2. **Hard Policies** - 违反即失败
3. **Contracts** - 违反即重试/升级
4. **Soft Policies** - 偏好，不阻断

### 原则七：Auditability 原则

**定义**: 所有操作必须可审计，留下不可篡改的痕迹。

**审计范围**: 角色切换、策略变更、代码修改、裁决发布、配置更新

---

## 1.4 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| TOP验证 | 验证SSOT拓扑完整性 | `top_validator.py` | `python tools/scc/ops/top_validator.py --registry docs/ssot/_registry.json` |
| 项目目录查询 | 查询项目目录 | `project_catalog.py` | `python tools/scc/ops/project_catalog.py list` |
| 工作空间验证 | 验证工作空间结构 | `workspace_validator.py` | `python tools/scc/ops/workspace_validator.py --id scc-top` |
| 架构缺口分析 | 分析架构实现进度 | `gap_analyzer.py` | `python tools/scc/ops/gap_analyzer.py --report` |

---

## 1.5 脚本使用示例

```bash
# 1. 验证SSOT拓扑完整性（CI门）
python tools/scc/ops/top_validator.py \
  --registry docs/ssot/_registry.json \
  --fail-closed \
  --verbose

# 2. 查询所有项目
python tools/scc/ops/project_catalog.py list \
  --format table \
  --include-status

# 3. 验证工作空间结构
python tools/scc/ops/workspace_validator.py \
  --id scc-top \
  --check-projects \
  --check-catalog

# 4. 生成架构缺口报告
python tools/scc/ops/gap_analyzer.py \
  --layer L1 \
  --report gaps.json \
  --suggest-priority
```

---

## 1.6 关键文件针脚

```yaml
L1_code_layer:
  ssot_partition: "02_architecture"
  chapter: 17
  description: "代码层（顶层治理）- 提供北极星目标、全局结构、治理协议"
  
  core_spec_files:
    - path: scc-top/docs/ssot/02_architecture/SCC_TOP.md
      oid: 01KGCV31J4D83WP3REZ575RJC3
      layer: ARCH
      primary_unit: S.CANONICAL_UPDATE
      description: "SCC顶层治理宪法"
    - path: scc-top/docs/ssot/02_architecture/PROJECT_GROUP__v0.1.0.md
      oid: 01KGFC6MC4G3812V8S25DY7V5N
      layer: ARCH
      primary_unit: W.WORKSPACE
      description: "项目组与工作空间定义"
    - path: scc-top/docs/ssot/02_architecture/SYSTEM_OVERVIEW.md
      oid: 01KGEJFT7DR82D3EM3CK2HMWGE
      layer: ARCH
      primary_unit: A.PLANNER
      description: "系统整体架构概览"
  
  related_files:
    - path: scc-top/docs/ssot/02_architecture/project_catalog.json
      oid: 012A85A390CEE94D18B7A432F700
      description: "项目目录机器索引"
    - path: scc-top/docs/ssot/02_architecture/canonical_truth.md
      oid: 015D746D506A7C4BB8AA76AAEE71
      description: "规范事实集与冲突优先级"
  
  tools:
    - path: tools/scc/ops/top_validator.py
      oid: 01F7990535B115436DA55995B0B5
    - path: tools/scc/ops/project_catalog.py
      oid: 0164B8A20CB396483D92014890DE
    - path: tools/scc/ops/workspace_validator.py
      oid: 01CBDF68D023834FE783E6FE0B51
    - path: tools/scc/ops/gap_analyzer.py
      oid: 01137FCA4A3F884F2197F91ACFE9
  
  related_chapters:
    - chapter: technical_manual/chapter_17_code_layer.md
      oid: 01AE3CDCA10EDD4C17A3B4F42065
```

---

## 1.7 本章小结

### 1.7.1 核心概念

| 概念 | 说明 |
|------|------|
| **SCC_TOP** | 顶层治理文档，包含宪法和核心原则 |
| **Project Group** | 项目组，包含多个产物项目 |
| **SSOT** | 单一事实来源，所有规范的权威来源 |
| **Pins-First** | 执行器只消费Pins JSON，禁止自由读仓 |
| **Connector** | 外部系统连接器（gateway.local, codex.cli等） |

### 1.7.2 关键规则

1. **每个契约必须声明其 `project_id`**（来自catalog）
2. **执行器parent必须使用allowlist roots生成 `allowed_globs[]`**
3. **若无法确定 `project_id`，必须STOP并回到S2补齐归类信息**
4. **TOP超过80行必须降级到SSOT叶文档**
5. **所有OID必须注册到registry**

### 1.7.3 依赖关系

```
L1 代码层
├─ 依赖 → L3 文档层（SSOT规范）
├─ 依赖 → L10 工作空间层（workspace定义）
├─ 依赖 → L17 本体层（OID/ULID体系）
└─ 被依赖 → L2 任务层（契约结构）
     └─ 被依赖 → L4-L16（所有执行层）
```

---


---

**导航**: [← L17](./L17_ontology_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L2](./L2_task_layer.md)