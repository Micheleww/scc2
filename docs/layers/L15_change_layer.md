# L15 变更与发布层

> **对应SSOT分区**: `05_runbooks/`, `02_architecture/`  
> **对应技术手册**: 第18章  
> **层定位**: 变更管理、发布流程、版本控制

---

## 15.1 层定位与职责

### 15.1.1 核心职责

L15是SCC架构的**变更管理层**，为全系统提供：

1. **变更管理** - 变更请求的处理和追踪
2. **发布流程** - 标准化发布流程
3. **版本控制** - 版本号管理和变更日志
4. **回滚策略** - 失败发布的回滚机制
5. **降级规则** - TOP文档的降级管理

### 15.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L15 变更与发布层                              │
│ ├─ 变更管理（变更请求）                       │
│ ├─ 发布流程（标准化发布）                     │
│ ├─ 版本控制（版本/变更日志）                  │
│ └─ 降级规则（TOP降级）                        │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L3 文档层, L14 质量层, L16 观测层            │
└─────────────────────────────────────────────┘
```

---

## 15.2 来自05_runbooks/和02_architecture/的核心内容

### 15.2.1 降级规则（来自SCC_TOP）

```
如果TOP的任何部分超过80行或约800字符：
- 将完整内容移到docs/ssot/下的适当叶文档
- 在TOP中替换为1句话摘要+链接
- 在变更日志中记录"Moved/Demoted"
```

### 15.2.2 版本控制规范

#### 语义化版本（SemVer）

```
版本格式: MAJOR.MINOR.PATCH

MAJOR: 不兼容的API变更
MINOR: 向后兼容的功能添加
PATCH: 向后兼容的问题修复

示例: v1.2.3
```

#### 文档命名版本

```
规范型文档: NAME__v0.1.0.md
报告型文档: REPORT__TOPIC__v0.1__YYYYMMDD.md
```

### 15.2.3 ADR工作流（架构决策记录）

#### ADR生命周期

```
1. 提出决策
   - 识别需要决策的技术问题
   - 创建ADR文档（状态：PROPOSED）
   - 分配给相关利益方审查

2. 审查讨论
   - 收集反馈和替代方案
   - 评估各方案利弊
   - 更新ADR（状态：UNDER_REVIEW）

3. 决策批准
   - 达成共识或决策权批准
   - 更新ADR（状态：ACCEPTED）
   - 记录拒绝的方案及原因

4. 实施追踪
   - 关联实施任务
   - 监控实施进度
   - 必要时更新ADR（状态：DEPRECATED/SUPERSEDED）
```

#### ADR文档模板

```markdown
# ADR-XXX: 决策标题

- 状态: PROPOSED | UNDER_REVIEW | ACCEPTED | DEPRECATED | SUPERSEDED
- 日期: YYYY-MM-DD
- 作者: [作者名]

## 背景
[问题描述和上下文]

## 决策
[选定的方案]

## 后果
[正面和负面影响]

## 替代方案
[被拒绝的方案及原因]
```

### 15.2.4 Git分支策略

#### 分支模型

| 分支 | 用途 | 保护规则 | 生命周期 |
|------|------|----------|----------|
| **main** | 生产代码 | 禁止直接推送，需PR审查 | 永久 |
| **develop** | 集成开发 | 禁止直接推送，需PR审查 | 永久 |
| **feature/*** | 功能开发 | 无 | 合并后删除 |
| **hotfix/*** | 紧急修复 | 需审查 | 合并后删除 |
| **release/*** | 发布准备 | 禁止直接推送 | 发布后删除 |

#### 工作流

```
标准功能开发:
main ← develop ← feature/new-feature

紧急修复:
main ← hotfix/critical-fix → develop

发布流程:
develop → release/v1.2.0 → main + tag
```

#### 提交规范

```
<type>(<scope>): <subject>

<body>

<footer>

类型:
- feat: 新功能
- fix: 修复
- docs: 文档
- style: 格式
- refactor: 重构
- test: 测试
- chore: 构建/工具
```

### 15.2.5 Hotfix/紧急变更流程

#### 触发条件

- 生产环境严重故障
- 安全漏洞需要立即修复
- 数据丢失风险

#### 流程步骤

```
1. 紧急评估 (5分钟内)
   - 确认故障严重性
   - 评估影响范围
   - 决定是否启动Hotfix

2. 快速修复 (30分钟内)
   - 从main创建hotfix分支
   - 实施最小修复（非重构）
   - 简化审查流程（1人快速审查）

3. 验证部署 (15分钟内)
   - 运行核心CI门（跳过非关键检查）
   - 部署到预发布环境验证
   - 部署到生产环境

4. 后续跟进
   - 记录Hotfix详情
   - 同步修复到develop分支
   - 事后审查（Post-mortem）
   - 更新相关文档
```

#### Hotfix审查简化规则

| 标准流程 | Hotfix简化 |
|----------|-----------|
| 2+人审查 | 1人快速审查 |
| 全量CI门 | 核心CI门 |
| 完整测试 | 回归测试 |
| 文档更新 | 事后补充 |

### 15.2.6 标准发布流程

```
1. 准备发布
   - 更新版本号
   - 更新变更日志
   - 运行所有CI门
   
2. 发布验证
   - 质量门检查
   - 安全审计
   - 文档完整性检查
   
3. 执行发布
   - 打标签
   - 生成发布包
   - 更新注册表
   
4. 发布后验证
   - 验证发布成功
   - 监控指标
   - 准备回滚方案
```

---

## 15.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 变更记录 | 记录变更 | `changelog.py` | `changelog.py add --type feature --desc "..."` |
| 版本发布 | 管理发布 | `release_manager.py` | `release_manager.py prepare --version v1.2.0` |
| 降级检查 | 检查TOP降级 | `demotion_checker.py` | `demotion_checker.py --check` |
| 回滚执行 | 执行回滚 | `rollback.py` | `rollback.py --to-version v1.1.9` |
| 发布验证 | 验证发布 | `release_validator.py` | `release_validator.py --version v1.2.0` |

---

## 15.4 脚本使用示例

```bash
# 1. 添加变更记录
python tools/scc/ops/changelog.py add \
  --type feature \
  --desc "添加用户认证模块" \
  --task-id TASK-001 \
  --author "dev-team"

# 2. 生成变更日志
python tools/scc/ops/changelog.py generate \
  --version v1.2.0 \
  --format markdown \
  --output CHANGELOG.md

# 3. 准备发布
python tools/scc/ops/release_manager.py prepare \
  --version v1.2.0 \
  --check-gates \
  --check-quality

# 4. 检查TOP降级
python tools/scc/ops/demotion_checker.py \
  --check \
  --max-lines 80 \
  --max-chars 800 \
  --auto-demotion

# 5. 执行发布
python tools/scc/ops/release_manager.py publish \
  --version v1.2.0 \
  --tag \
  --notify

# 6. 执行回滚
python tools/scc/ops/rollback.py \
  --to-version v1.1.9 \
  --reason "Critical bug in v1.2.0" \
  --notify-team
```

---

## 15.5 关键文件针脚

```yaml
L15_change_layer:
  ssot_partition: "05_runbooks, 02_architecture"
  chapter: 18
  description: "变更与发布层 - 提供变更管理、发布流程、版本控制"
  
  core_spec_files:
    - path: scc-top/docs/ssot/02_architecture/SCC_TOP.md
      oid: 014896F22E01F3478FA6C1D5018A
      description: "包含降级规则"
    - path: scc-top/docs/ssot/05_runbooks/SCC_RUNBOOK__v0.1.0.md
      oid: 01A59804D5FC0E40A18859B17FDD
      description: "包含发布流程"
  
  tools:
    - path: tools/scc/ops/changelog.py
      oid: 01CD0CC1A6E0464333B31B936C82
    - path: tools/scc/ops/release_manager.py
      oid: 010D7C47222FA746148F63BE3B15
    - path: tools/scc/ops/demotion_checker.py
      oid: 01C60F02CB04D345EBA54BFA6B45
    - path: tools/scc/ops/rollback.py
      oid: 01CE3EFEE9A3344DFCB3EFAFC881
    - path: tools/scc/ops/release_validator.py
      oid: 01F34B1A46820B406AA3A4A05C19
  
  related_chapters:
    - chapter: technical_manual/chapter_18_change_layer.md
      oid: 01B44BD2FC4CE94A1CA999F722DE
```

---

## 15.6 本章小结

### 15.6.1 核心概念

| 概念 | 说明 |
|------|------|
| 降级规则 | TOP超过80行必须降级到叶文档 |
| SemVer | 语义化版本控制 |
| 发布流程 | 准备→验证→发布→验证 |
| 回滚策略 | 失败发布的快速回滚 |

### 15.6.2 关键规则

1. **降级强制**: TOP超过80行必须降级
2. **版本规范**: 使用SemVer格式
3. **发布检查**: 发布前必须通过所有CI门
4. **回滚准备**: 每个发布必须有回滚方案

### 15.6.3 依赖关系

```
L15 变更与发布层
    │
    ├─ 依赖 → L3文档层（文档生命周期）
    ├─ 依赖 → L14质量层（质量门）
    │
    ├─ 提供变更给 → L16 观测层
    └─ 提供版本给 → L17 本体层
```

---


---

**导航**: [← L14](./L14_quality_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L16](./L16_observability_layer.md)