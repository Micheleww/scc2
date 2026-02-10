# START_HERE - SCC Backend 项目导航

> **所有 AI 助手首先阅读此文档**
> 
> 本文档是 SCC Backend 项目的统一入口，包含：
> - 17层架构导航
> - 文件索引搜索方法
> - 功能分类指南

---

## 🔍 快速文件搜索（所有 AI 必须使用）

### 方法 1: 使用文件索引器（推荐）

```bash
# 构建索引（首次使用）
cd c:\scc\scc-bd
node tools/file_indexer.mjs build

# 搜索文件
node tools/file_indexer.mjs search <关键词>

# 查看特定层
node tools/file_indexer.mjs layer L6
```

**示例：**
```bash
# 搜索父任务相关代码
node tools/file_indexer.mjs search parent

# 搜索执行器
node tools/file_indexer.mjs search executor

# 查看 L6 Agent 层所有文件
node tools/file_indexer.mjs layer L6
```

### 方法 2: 按 17 层架构定位

1. 确定功能所属层级（见下方 17层功能分类）
2. 进入对应层目录查找
3. 使用文件索引确认具体位置

---

## � Git 自动同步到 Docker（重要）

> **AI 助手只需推送 Git，代码会自动同步到 Docker 容器**

### 工作流程

```
本地代码修改
    ↓
git add .
    ↓
git commit -m "描述"
    ↓
git push
    ↓
自动触发 post-push hook
    ↓
Docker 容器执行 scc-sync
    ↓
容器内代码更新完成
```

### 手动同步（如果需要）

```bash
# 在容器内执行同步
docker exec scc-server scc-sync

# 或重启容器
docker restart scc-server
```

### 验证同步状态

```bash
# 检查容器内代码版本
docker exec scc-server git log --oneline -1

# 对比本地和容器
git log --oneline -1
docker exec scc-server git log --oneline -1
```

---

## �📋 文档维护方法

1. **确定功能所属层级** - 查看下方各层功能分类
2. **在对应层创建文档** - 写入该层目录下的对应功能目录
3. **更新层内索引** - 在该层 README.md 中添加文档链接
4. **保持简洁** - 一个功能一个文档，避免冗余

---

## 📁 17层文档针脚

```
scc-bd/
├── L1_code_layer/              ← 代码层：网关、配置、Docker、UI
├── L2_task_layer/              ← 任务层：契约、模式、Pins、上下文
├── L3_documentation_layer/     ← 文档层：文档治理、导航验证
├── L4_prompt_layer/            ← 提示词层：角色、技能、提示词
├── L5_model_layer/             ← 模型层：模型适配、路由
├── L6_agent_layer/             ← Agent层：执行器、编排器、运行时
├── L7_tool_layer/              ← 工具层：脚本、能力、运维
├── L8_evidence_layer/          ← 证据层：验证裁决
├── L9_state_layer/             ← 状态层：状态存储、Board、Jobs
├── L10_workflow_layer/         ← 工作流层：工作流定义
├── L11_routing_layer/          ← 路由层：路由系统、调度
├── L12_collaboration_layer/    ← 协作层：协作工具
├── L13_security_layer/         ← 安全层：门禁、熔断器、预检
├── L14_quality_layer/          ← 质量层：评测、测试、验证
├── L15_change_layer/           ← 变更层：Playbook、发布
├── L16_observability_layer/    ← 观测层：日志、监控、产物
└── L17_ontology_layer/         ← 本体层：地图、OID、归档
```

---

## 📚 17层功能分类

### L1 代码层 - 系统治理
| 功能分类 | 写入路径 |
|---------|---------|
| 网关配置 | `L1_code_layer/gateway/` |
| 运行时配置 | `L1_code_layer/config/` |
| Docker部署 | `L1_code_layer/docker/` |
| Web界面 | `L1_code_layer/ui/` |
| 工厂策略 | `L1_code_layer/factory_policy/` |

### L2 任务层 - 任务管理
| 功能分类 | 写入路径 |
|---------|---------|
| 契约定义 | `L2_task_layer/contracts/` |
| 任务模式 | `L2_task_layer/patterns/` |
| Pins构建 | `L2_task_layer/pins/` |
| 上下文打包 | `L2_task_layer/context_pack/` |

### L3 文档层 - 文档治理
| 功能分类 | 写入路径 |
|---------|---------|
| 文档治理 | `L3_documentation_layer/docs_governance/` |

### L4 提示词层 - 角色技能
| 功能分类 | 写入路径 |
|---------|---------|
| 角色定义 | `L4_prompt_layer/roles/` |
| 技能定义 | `L4_prompt_layer/skills/` |
| 提示词模板 | `L4_prompt_layer/prompts/` |
| 角色系统 | `L4_prompt_layer/role_system/` |

### L5 模型层 - 模型管理
| 功能分类 | 写入路径 |
|---------|---------|
| 模型适配 | `L5_model_layer/models/` |

### L6 Agent层 - 执行编排
| 功能分类 | 写入路径 |
|---------|---------|
| 执行器 | `L6_agent_layer/executors/` |
| 编排器 | `L6_agent_layer/orchestrators/` |
| 运行时 | `L6_agent_layer/runtime/` |

### L7 工具层 - 工具运维
| 功能分类 | 写入路径 |
|---------|---------|
| 脚本工具 | `L7_tool_layer/scripts/` |
| 运维工具 | `L7_tool_layer/ops/` |
| 能力模块 | `L7_tool_layer/capabilities/` |

### L8 证据层 - 证据管理
| 功能分类 | 写入路径 |
|---------|---------|
| 验证裁决 | `L8_evidence_layer/verdict/` |

### L9 状态层 - 状态管理
| 功能分类 | 写入路径 |
|---------|---------|
| 状态存储 | `L9_state_layer/state_stores/` |

### L10 工作流层 - 工作流管理
| 功能分类 | 写入路径 |
|---------|---------|
| 工作流定义 | `L10_workflow_layer/workflows/` |

### L11 路由层 - 路由调度
| 功能分类 | 写入路径 |
|---------|---------|
| 路由系统 | `L11_routing_layer/routing/` |

### L12 协作层 - 协作管理
| 功能分类 | 写入路径 |
|---------|---------|
| 协作工具 | `L12_collaboration_layer/collaboration/` |

### L13 安全层 - 门禁控制
| 功能分类 | 写入路径 |
|---------|---------|
| 门禁系统 | `L13_security_layer/gatekeeper/` |
| CI门禁 | `L13_security_layer/gates/` |
| 熔断器 | `L13_security_layer/circuit_breaker/` |

### L14 质量层 - 测试验证
| 功能分类 | 写入路径 |
|---------|---------|
| 评测框架 | `L14_quality_layer/eval/` |
| 测试文件 | `L14_quality_layer/test/` |
| 验证器 | `L14_quality_layer/validators/` |

### L15 变更层 - 变更管理
| 功能分类 | 写入路径 |
|---------|---------|
| Playbook | `L15_change_layer/playbooks/` |
| 发布管理 | `L15_change_layer/releases/` |

### L16 观测层 - 可观测性
| 功能分类 | 写入路径 |
|---------|---------|
| 日志系统 | `L16_observability_layer/logging/` |
| 构建产物 | `L16_observability_layer/artifacts/` |

### L17 本体层 - 知识本体
| 功能分类 | 写入路径 |
|---------|---------|
| 代码地图 | `L17_ontology_layer/map/` |
| OID管理 | `L17_ontology_layer/oid/` |
| 归档文件 | `L17_ontology_layer/archive/` |

---

## 📝 文档模板

```markdown
# [功能名称]

> 所属层级: L[X]_[layer_name]

## 功能说明
[一句话描述]

## 使用方法
[简要说明]

## 相关链接
- [上层文档](../README.md)
```

---

**维护**: 写入文档时同步更新本文件中的功能分类表

---

## 🚀 AI 助手快速开始清单

**开始工作前，请确认：**

- [ ] 已阅读本文档的 "快速文件搜索" 部分
- [ ] 已运行 `node tools/file_indexer.mjs build` 构建索引
- [ ] 使用 `node tools/file_indexer.mjs search <关键词>` 查找相关代码
- [ ] 根据 17层架构定位功能所属层级

**常用搜索关键词：**
- `parent` - 父任务相关
- `executor` - 执行器相关
- `gateway` - 网关相关
- `router` - 路由相关
- `state` - 状态存储相关
- `job` - 任务相关
- `orchestrator` - 编排器相关

---

## ⚠️ AI 助手操作限制（重要）

### 🚫 禁止操作

| 操作 | 状态 | 说明 |
|------|------|------|
| **构建 Docker 镜像** | ❌ 禁止 | 不要执行 `docker build` 或修改 Dockerfile |
| **启动/停止 Docker 容器** | ❌ 禁止 | 不要执行 `docker-compose up/down` |
| **修改 Docker 配置** | ❌ 禁止 | 不要修改 docker-compose.yml 或 entrypoint.sh |

### ✅ 允许操作

| 操作 | 状态 | 说明 |
|------|------|------|
| **推送 Git** | ✅ 允许 | 执行 `git add`, `git commit`, `git push` |
| **修改源代码** | ✅ 允许 | 修改 scc-bd/ 目录下的代码文件 |
| **创建文档** | ✅ 允许 | 添加或修改文档 |

### 📝 为什么禁止 Docker 操作？

Docker 构建和配置由专门的运维流程管理。AI 助手只需：
1. 修改源代码
2. 提交到 Git
3. 代码会自动同步到 Docker 容器（通过 Git Hook）

**需要 Docker 变更？** 请联系运维人员或创建 Issue。
