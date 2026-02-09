# L13 安全与权限层

> **对应SSOT分区**: `04_contracts/`, `03_agent_playbook/`  
> **对应技术手册**: 第6章  
> **层定位**: 权限控制、安全策略、门禁检查

---

## 13.1 层定位与职责

### 13.1.1 核心职责

L13是SCC架构的**安全控制层**，为全系统提供：

1. **权限控制** - 基于角色的访问控制（RBAC）
2. **安全策略** - 安全执行策略定义
3. **门禁检查** - 13道CI门的执行
4. **技能守卫** - 工具调用门禁检查
5. **审计日志** - 安全事件的审计追踪

### 13.1.2 在架构中的位置

```
┌─────────────────────────────────────────────┐
│ L13 安全与权限层                              │
│ ├─ 权限控制（RBAC）                           │
│ ├─ 安全策略（执行策略）                       │
│ ├─ 门禁检查（13道CI门）                       │
│ └─ 技能守卫（skill_call_guard）               │
└──────────────────┬──────────────────────────┘
                   │ 被依赖
                   ▼
┌─────────────────────────────────────────────┐
│ L6 Agent层, L7 工具层, L8 证据层             │
└─────────────────────────────────────────────┘
```

---

## 13.2 来自04_contracts/和03_agent_playbook/的核心内容

### 13.2.1 13道CI门

#### 门禁列表

| 门 | 名称 | 说明 | 检查内容 |
|----|------|------|----------|
| G1 | ContractGate | 契约验证 | 契约完整性、字段合规 |
| G2 | EventGate | 事件验证 | 事件格式、顺序合规 |
| G3 | SecretsGate | 密钥验证 | 密钥不泄露、安全存储 |
| G4 | ReleaseGate | 发布验证 | 发布流程合规 |
| G5 | ConnectorGate | 连接器验证 | 外部连接器安全 |
| G6 | SemanticContextGate | 语义上下文 | 上下文一致性 |
| G7 | DocLinkGate | 文档链接 | 链接有效性 |
| G8 | MapGate | 映射验证 | 映射完整性 |
| G9 | SchemaGate | 模式验证 | JSON Schema合规 |
| G10 | SSOTGate | SSOT验证 | SSOT一致性 |
| G11 | SSOT_MAP_Gate | SSOT映射 | SSOT映射正确 |
| G12 | TraceGate | 追踪验证 | 追踪链完整 |
| G13 | VerifierJudgeGate | 裁决验证 | 裁决合规 |

### 13.2.2 技能守卫（Skill Call Guard）

> **完整技能定义**: 详见 [L4 提示词层 - 技能规范](./L4_prompt_layer.md#422-技能规范skillspec)
> **工具层执行机制**: 详见 [L7 工具层 - 技能守卫](./L7_tool_layer.md#722-技能守卫skill-call-guard)

L13关注安全维度：确保技能调用通过门禁检查并留下审计痕迹。

#### 安全门禁规则

- 任何声称DONE的任务必须能通过适当的guard(s)验证
- 技能/工具使用必须通过工件和/或结构化日志**可审计**
- 违反技能守卫的任务标记为 `POLICY_VIOLATION`

---

## 13.3 核心功能与脚本

| 功能 | 说明 | 脚本/工具 | 命令示例 |
|------|------|-----------|----------|
| 门禁运行 | 运行13道CI门 | `gates_runner.py` | `gates_runner.py --all` |
| 技能守卫 | 验证技能调用 | `skill_call_guard.py` | `skill_call_guard.py --task-code TASK-001 --skill SHELL_WRITE` |
| 权限检查 | RBAC检查 | `rbac_check.py` | `rbac_check.py --user alice --action write --resource task` |
| 安全审计 | 安全审计 | `security_audit.py` | `security_audit.py --full` |
| 密钥管理 | 密钥管理 | `secret_manager.py` | `secret_manager.py set --key API_KEY --value "..."` |

---

## 13.4 脚本使用示例

```bash
# 1. 运行所有CI门
python tools/scc/ops/gates_runner.py \
  --all \
  --fail-closed \
  --report gates_report.json

# 2. 运行单个门禁
python tools/scc/ops/gates_runner.py \
  --gate ContractGate \
  --contract contracts/task_001.json

# 3. 验证技能调用
python tools/ci/skill_call_guard.py \
  --task-code TASK-001 \
  --skill SHELL_WRITE \
  --scope-allow '["src/*", "tests/*"]' \
  --actual-paths '["src/main.py"]' \
  --fail-closed

# 4. RBAC权限检查
python tools/scc/ops/rbac_check.py \
  --user alice \
  --role executor \
  --action write \
  --resource task \
  --task-id TASK-001

# 5. 安全审计
python tools/scc/ops/security_audit.py \
  --full \
  --include-secrets \
  --include-permissions \
  --output audit_report.json

# 6. 密钥管理
python tools/scc/ops/secret_manager.py set \
  --key API_KEY \
  --value "sk-..." \
  --encrypt \
  --access-roles '["executor", "verifier"]'
```

---

## 13.5 关键文件针脚

```yaml
L13_security_layer:
  ssot_partition: "04_contracts, 03_agent_playbook"
  chapter: 6
  description: "安全与权限层 - 提供权限控制、安全策略、门禁检查"
  
  core_spec_files:
    - path: scc-top/docs/ssot/03_agent_playbook/SKILL_SPEC__v0.1.0.md
      oid: 01F1257545743A4185AAF7EA6436
      description: "技能规范，定义门禁规则"
    - path: scc-top/docs/ssot/04_contracts/contract_min_spec.md
      oid: 01D433B7D4D22F47AAA7AF4E9706
      description: "契约规范，定义安全相关字段"
  
  gates:
    - G1: ContractGate
    - G2: EventGate
    - G3: SecretsGate
    - G4: ReleaseGate
    - G5: ConnectorGate
    - G6: SemanticContextGate
    - G7: DocLinkGate
    - G8: MapGate
    - G9: SchemaGate
    - G10: SSOTGate
    - G11: SSOT_MAP_Gate
    - G12: TraceGate
    - G13: VerifierJudgeGate
  
  tools:
    - path: tools/scc/ops/gates_runner.py
      oid: 0152D7C801CC9149AC93A64C0628
    - path: tools/ci/skill_call_guard.py
      oid: 01C5892325A29A4ABDBCA8674FE0
    - path: tools/scc/ops/rbac_check.py
      oid: 01E42EB96555F945C2A93DDFFEA8
    - path: tools/scc/ops/security_audit.py
      oid: 014A39463002A14BBCA94358873E
    - path: tools/scc/ops/secret_manager.py
      oid: 01A7FEAC9F6792456CA263805240
  
  related_chapters:
    - chapter: technical_manual/chapter_06_security_layer.md
      oid: 018D40076E85FB4FDC9F1FAA5398
```

---

## 13.6 本章小结

### 13.6.1 核心概念

| 概念 | 说明 |
|------|------|
| 13道CI门 | 从契约到裁决的完整门禁链 |
| 技能守卫 | 验证技能调用合规性 |
| RBAC | 基于角色的访问控制 |
| 故障关闭 | 无法验证时默认拒绝 |

### 13.6.2 关键规则

1. **门禁强制**: 所有任务必须通过适用的CI门
2. **技能守卫**: 每个DONE任务必须通过guard验证
3. **故障关闭**: 无法验证时默认拒绝
4. **审计追踪**: 所有安全事件必须记录

### 13.6.3 依赖关系

```
L13 安全与权限层
    │
    ├─ 依赖 → L4提示词层（技能定义）
    ├─ 依赖 → L2任务层（契约定义）
    │
    ├─ 提供门禁给 → L6 Agent层
    ├─ 提供守卫给 → L7 工具层
    └─ 提供审计给 → L8 证据层
```

---


---

**导航**: [← L12](./L12_cost_layer.md) | [↑ 返回导航](../START_HERE.md) | [→ L14](./L14_quality_layer.md)