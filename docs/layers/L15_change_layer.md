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

### 15.2.3 发布流程

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
      description: "包含降级规则"
    - path: scc-top/docs/ssot/05_runbooks/SCC_RUNBOOK__v0.1.0.md
      description: "包含发布流程"
  
  tools:
    - tools/scc/ops/changelog.py
    - tools/scc/ops/release_manager.py
    - tools/scc/ops/demotion_checker.py
    - tools/scc/ops/rollback.py
    - tools/scc/ops/release_validator.py
  
  related_chapters:
    - technical_manual/chapter_18_change_layer.md
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