# SCC Backend 文件分层映射文档

> 根据 START_HERE L1-L17 分层规范整理
> 整理日期: 2026-02-10

---

## 文件夹分类映射

### L1 代码层 (L1_code_layer) - 顶层治理层
**职责**: 系统整体架构、全局配置、网关入口、部署配置

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `config/` | `L1_code_layer/config/` | 运行时配置 |
| `docker/` | `L1_code_layer/docker/` | Docker部署配置 |
| `ui/` | `L1_code_layer/ui/` | Web界面 |
| `gateway/` | `L1_code_layer/gateway/` | 主网关入口 |
| `factory_policy/` | `L1_code_layer/factory_policy/` | 工厂策略 |

**Docker 相关文档** (2026-02-10 新增):
| 文档路径 | 说明 |
|----------|------|
| `L1_code_layer/docker/DOCKER_NORMALIZATION.md` | Docker 归一化文档 |
| `L1_code_layer/docker/VERSION_POLICY.md` | Docker 版本管理规范 |
| `L1_code_layer/docker/BUILD_GUIDE.md` | Docker 构建指南 |

### L2 任务层 (L2_task_layer) - 任务管理层
**职责**: 任务定义、契约管理、任务生命周期、Pins构建

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `context_pack/` | `L2_task_layer/context_pack/` | 上下文打包 |
| `contracts/` | `L2_task_layer/contracts/` | 契约Schema定义 |
| `patterns/` | `L2_task_layer/patterns/` | 任务模式定义 |
| `pins/` | `L2_task_layer/pins/` | Pins构建器 |

### L3 文档层 (L3_documentation_layer) - 文档治理层
**职责**: 文档治理、资源检查、导航验证

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `docs_governance/` | `L3_documentation_layer/docs_governance/` | 文档治理工具集 |

### L4 提示词层 (L4_prompt_layer) - 角色与技能层
**职责**: 提示词模板、角色定义、技能规范

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `prompts/` | `L4_prompt_layer/prompts/` | 提示词文件 |
| `prompt_registry/` | `L4_prompt_layer/prompt_registry/` | 提示词注册表 |
| `role_system/` | `L4_prompt_layer/role_system/` | 角色系统 |
| `roles/` | `L4_prompt_layer/roles/` | 角色定义 |
| `skills/` | `L4_prompt_layer/skills/` | 技能定义 |
| `skills_drafts/` | `L4_prompt_layer/skills_drafts/` | 技能草稿 |

### L5 模型层 (L5_model_layer) - 模型管理层
**职责**: 模型配置、模型选择策略、能力映射

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `models/` | `L5_model_layer/models/` | 模型适配器和路由 |

### L6 Agent层 (L6_agent_layer) - Agent执行层
**职责**: Agent执行、Agent路由、Agent协作

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `executors/` | `L6_agent_layer/executors/` | 执行器模块 |
| `orchestrators/` | `L6_agent_layer/orchestrators/` | 编排器 |
| `runtime/` | `L6_agent_layer/runtime/` | 运行时环境 |

### L7 工具层 (L7_tool_layer) - 工具管理层
**职责**: 工具定义、工具执行、工具发现

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `scripts/` | `L7_tool_layer/scripts/` | 脚本工具 |
| `capabilities/` | `L7_tool_layer/capabilities/` | 能力模块 |
| `lib/` | `L7_tool_layer/lib/` | 工具库 |
| `ops/` | `L7_tool_layer/ops/` | 运维工具 |

### L8 证据层 (L8_evidence_layer) - 证据管理层
**职责**: 证据收集、裁决判定、验证结果

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `verdict/` | `L8_evidence_layer/verdict/` | 验证裁决 |

### L9 状态层 (L9_state_layer) - 状态管理层
**职责**: 会话状态、工作记忆、上下文管理

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `state_stores/` | `L9_state_layer/state_stores/` | 状态存储 |

### L11 路由层 (L11_routing_layer) - 路由调度层
**职责**: 任务路由、调度策略、负载均衡

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `routing/` | `L11_routing_layer/routing/` | 路由系统 |

### L13 安全层 (L13_security_layer) - 安全控制层
**职责**: 权限控制、安全策略、门禁检查

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `circuit_breaker/` | `L13_security_layer/circuit_breaker/` | 熔断器存储 |
| `gatekeeper/` | `L13_security_layer/gatekeeper/` | 门禁系统 |
| `gates/` | `L13_security_layer/gates/` | 13道CI门 |
| `preflight/` | `L13_security_layer/preflight/` | 预检系统 |

### L14 质量层 (L14_quality_layer) - 质量管理层
**职责**: 质量评估、评测框架、质量报告

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `eval/` | `L14_quality_layer/eval/` | 评测样本集 |
| `selftest/` | `L14_quality_layer/selftest/` | 自检工具 |
| `test/` | `L14_quality_layer/test/` | 测试文件 |
| `validators/` | `L14_quality_layer/validators/` | 验证器 |

### L15 变更层 (L15_change_layer) - 变更管理层
**职责**: Playbook管理、变更控制、发布管理

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `playbooks/` | `L15_change_layer/playbooks/` | Playbook定义 |
| `releases/` | `L15_change_layer/releases/` | 发布记录 |
| `releases_selfcheck/` | `L15_change_layer/releases_selfcheck/` | 自检发布记录 |

### L16 观测层 (L16_observability_layer) - 可观测性层
**职责**: 日志、监控、错误收集、构建产物

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `artifacts/` | `L16_observability_layer/artifacts/` | 构建产物 |
| `logging/` | `L16_observability_layer/logging/` | 日志系统 |

### L17 本体层 (L17_ontology_layer) - 知识本体层
**职责**: 术语定义、ID体系、实体关系、归档

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `archive/` | `L17_ontology_layer/archive/` | 归档文件 |
| `map/` | `L17_ontology_layer/map/` | 代码地图 |
| `map_v1/` | `L17_ontology_layer/map_v1/` | Map v1系统 |
| `oid/` | `L17_ontology_layer/oid/` | OID/ULID管理 |

---

## 散落文件分类映射

### L1 代码层

| 原路径 | 新路径 | 说明 |
|--------|--------|------|
| `README.md` | `L1_code_layer/README.md` | 项目说明文档 |
| `package.json` | `L1_code_layer/package.json` | Node.js包配置 |
| `package-lock.json` | `L1_code_layer/package-lock.json` | 依赖锁定文件 |

---

## 保留在根目录的文件

以下文件保留在项目根目录：

| 文件/目录 | 说明 |
|-----------|------|
| `node_modules/` | Node.js依赖（自动生成） |
| `LAYER_MAPPING.md` | 本映射文档 |

---

## 分层依赖关系

```
L17 本体层 (OID/Map/Archive)
    ↓
L1 代码层 (Gateway/Config/Docker)
    ↓
L2 任务层 (Contracts/Pins/Context)
    ↓
L4 提示词层 (Roles/Skills/Prompts)
    ↓
L5 模型层 (Models)
    ↓
L6 Agent层 (Executors/Orchestrators)
    ↓
L7 工具层 (Scripts/Capabilities/Ops)
    ↓
L8 证据层 (Verdict)
    ↓
L9 状态层 (State/Board/Jobs)
    ↓
L11 路由层 (Router)
    ↓
L13 安全层 (Gates/Preflight/CircuitBreaker)
    ↓
L14 质量层 (Eval/Test/Validators)
    ↓
L15 变更层 (Playbooks/Releases)
    ↓
L16 观测层 (Artifacts/Logging)
```

---

## 整理说明

1. **分类原则**: 根据START_HERE文档的L1-L17分层规范，将文件按功能归类到对应层级
2. **移动方式**: 使用PowerShell的Move-Item命令进行移动，保持文件完整性
3. **保留文件**: node_modules为自动生成目录，保留在根目录
4. **映射文档**: 本文档记录了所有文件的分类映射关系，便于后续查找

---

## 后续建议

1. 更新项目文档中的路径引用
2. 更新package.json中的scripts路径
3. 更新Dockerfile中的COPY路径
4. 更新配置文件中的路径引用
5. 测试所有功能确保路径变更后正常工作
