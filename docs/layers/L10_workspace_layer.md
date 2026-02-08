# L10 工作空间层

> **对应SSOT分区**: `06_inputs/`（外部输入）  
> **对应技术手册**: 第16章  
> **层定位**: 工作空间定义、输入管理、环境配置

---

## 10.1 层定位与职责

### 10.1.1 核心职责

L10是SCC架构的**工作空间层**，为全系统提供：

1. **工作空间定义** - workspace_id、project_group结构
2. **输入管理** - 外部输入的统一落点（docs/INPUTS/）
3. **环境配置** - 工作空间环境变量和配置
4. **项目目录** - 项目分类和目录结构
5. **输入规范** - 外部输入的格式和元数据要求

### 10.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L10 工作空间层                                │
│ ├─ 工作空间定义（workspace_id）               │
│ ├─ 输入管理（docs/INPUTS/）                   │
│ ├─ 环境配置（环境变量）                       │
│ └─ 项目目录（project_group）                  │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L2 任务层, L6 Agent层, L7 工具层             │
└─────────────────────────────────────────────┘
```

---

## 10.2 来自06_inputs/的核心内容

### 10.2.1 工作空间身份（规范）

#### 核心文件

| 文件路径 | 说明 | 关键内容 |
|----------|------|----------|
| `ssot/02_architecture/PROJECT_GROUP__v0.1.0.md` | 项目组定义 | workspace_id, project_group, project_catalog |
| `ssot/06_inputs/index.md` | 输入层索引 | 外部输入的落点规范 |

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
2. 每个执行器parent必须使用该项目allowlist roots生成 `allowed_globs[]`（scope gate）
3. 若无法确定 `project_id`，必须STOP并回到S2补齐归类信息，不得猜测

### 10.2.2 外部输入规范

#### 输入落点

| 输入类型 | 落点目录 | 说明 |
|----------|----------|------|
| WebGPT聊天 | `docs/INPUTS/WEBGPT/` | WebGPT对话记录 |
| 需求文档 | `docs/INPUTS/requirements/` | 外部需求文档 |
| 会议纪要 | `docs/INPUTS/meetings/` | 会议记录 |
| 反馈包 | `docs/INPUTS/feedback/` | 审计反馈 |

#### 输入元数据（必须）

```yaml
输入文档必须包含:
  source: "来源标识"
  captured_at: "捕获时间戳"
  page_url: "原始URL（若适用）"
  
禁止:
  - 把推理结果混进原文
  - 在INPUTS目录下直接修改规范
```

---

## 10.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 工作空间验证 | 验证工作空间结构 | `workspace_validator.py` | `workspace_validator.py --id scc-top` |
| 项目目录查询 | 查询项目目录 | `project_catalog.py` | `project_catalog.py list` |
| 输入归档 | 归档外部输入 | `input_archiver.py` | `input_archiver.py --source webgpt --file chat.log` |
| 环境配置 | 管理环境变量 | `env_config.py` | `env_config.py set --key API_KEY --value "..."` |
| 范围检查 | 检查文件是否在允许范围内 | `scope_checker.py` | `scope_checker.py --project quantsys --files '["src/main.py"]'` |

---

## 10.4 脚本使用示例

```bash
# 1. 验证工作空间结构
python tools/scc/ops/workspace_validator.py \
  --id scc-top \
  --check-projects \
  --check-catalog \
  --check-inputs

# 2. 查询所有项目
python tools/scc/ops/project_catalog.py list \
  --format table \
  --include-status \
  --include-paths

# 3. 归档WebGPT输入
python tools/scc/ops/input_archiver.py \
  --source webgpt \
  --conversation-id conv_123 \
  --file chat_export.json \
  --output docs/INPUTS/WEBGPT/2026-02-09/

# 4. 设置环境变量
python tools/scc/ops/env_config.py set \
  --key SCC_MODEL_DEFAULT \
  --value "kimi-k2.5" \
  --scope workspace

# 5. 检查文件是否在项目允许范围内
python tools/scc/ops/scope_checker.py \
  --project quantsys \
  --files '["src/main.py", "src/utils.py", "../secrets.env"]' \
  --fail-closed
```

---

## 10.5 关键文件针脚

```yaml
L10_workspace_layer:
  ssot_partition: "06_inputs"
  chapter: 16
  description: "工作空间层 - 提供工作空间定义、输入管理、环境配置"
  
  core_spec_files:
    - path: scc-top/docs/ssot/02_architecture/PROJECT_GROUP__v0.1.0.md
      oid: 01KGFC6MC4G3812V8S25DY7V5N
      layer: ARCH
      primary_unit: W.WORKSPACE
      description: "项目组与工作空间定义"
    - path: scc-top/docs/ssot/06_inputs/index.md
      description: "输入层索引，外部输入落点规范"
  
  related_files:
    - path: scc-top/docs/ssot/02_architecture/project_catalog.json
      description: "项目目录机器索引"
    - path: scc-top/docs/INPUTS/WEBGPT/index.md
      description: "WebGPT输入入口"
    - path: scc-top/docs/INPUTS/WEBGPT/memory.md
      description: "WebGPT记忆"
  
  tools:
    - tools/scc/ops/workspace_validator.py
    - tools/scc/ops/project_catalog.py
    - tools/scc/ops/input_archiver.py
    - tools/scc/ops/env_config.py
    - tools/scc/ops/scope_checker.py
  
  related_chapters:
    - technical_manual/chapter_16_workspace_layer.md
```

---

## 10.6 本章小结

### 10.6.1 核心概念

| 概念 | 说明 |
|------|------|
| workspace_id | 工作空间身份标识 |
| project_group | 项目组定义 |
| project_id | 项目标识（必须在catalog中） |
| scope_allow | 允许修改的文件范围 |
| INPUTS目录 | 外部输入的统一落点 |

### 10.6.2 关键规则

1. **project_id强制**: 每个契约必须声明有效的project_id
2. **范围检查**: 执行器只能修改allowlisted文件
3. **输入分离**: 外部输入必须放在docs/INPUTS/，不得混入规范
4. **工作空间身份**: 以workspace_id为准，目录名可变

### 10.6.3 依赖关系

```
L10 工作空间层
    │
    ├─ 依赖 → L1代码层（project定义）
    │
    ├─ 提供工作空间给 → L2任务层
    ├─ 提供范围给 → L6 Agent层
    └─ 提供环境给 → L7 工具层
```

### 10.2.5 WorkspaceSpec（来自SSOT）

**目标**: 定义SCC使用的最小工作空间不变量

**最小不变量**:
- `workspace_id`: `scc-top`
- 仓库根包含 `docs/START_HERE.md` (唯一入口)
- SSOT主干在 `docs/ssot/` 下
- 输入在 `docs/INPUTS/` 下
- 派生（可再生）输出在 `docs/DERIVED/` 下
- 证据/输出在 `artifacts/` 和 `evidence/` 下（首选append-only）

**多项目工作空间**:
- 每个合同必须声明 `project_id`
- 分发必须从项目目录派生 `allowed_globs[]`，然后进一步按 `contract.scope_allow` 缩小

### 10.2.6 Project Group（来自SSOT）

**目标**: 定义SCC的"工作区(workspace) + 项目组(project group) + 项目(projects)"最小结构

**Workspace身份**:
- `workspace_id`: `scc-top`
- `workspace_root`: `<REPO_ROOT>`

**项目组**:
- `project_group_id`: `scc-top-products`
- 项目列表:
  - `quantsys` — 量化金融（现有主工程）
  - `yme` — YME连锁餐饮（产物项目）
  - `math_modeling` — 数模竞赛（产物项目）

**规范项目目录**:
- 权威机器索引: `docs/ssot/02_architecture/project_catalog.json`
- 每个合同必须声明其 `project_id`（来自catalog）
- 每个执行器parent必须使用该项目allowlist roots生成 `allowed_globs[]`
- 若无法确定 `project_id`，必须STOP并回到S2补齐归类信息

---


---

**导航**: [← L9](./L9_state_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L11](./L11_routing_layer.md)