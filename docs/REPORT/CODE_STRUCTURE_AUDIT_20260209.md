# SCC 代码结构审计报告

> **日期**: 2026-02-09  
> **范围**: c:\scc 全仓库代码结构  
> **审计方式**: 直接代码分析（不参考文档）

---

## 执行摘要

| 维度 | 评分 | 状态 |
|------|------|------|
| 目录组织 | 4/10 | 🔴 严重 |
| 代码复用 | 3/10 | 🔴 严重 |
| 依赖管理 | 3/10 | 🔴 严重 |
| 配置管理 | 4/10 | 🔴 严重 |
| 命名规范 | 5/10 | 🟡 警告 |
| 根目录整洁 | 3/10 | 🔴 严重 |
| **综合评分** | **3.7/10** | 🔴 **需要立即修复** |

---

## 1. 目录结构问题

### 1.1 嵌套代码库重复（最严重）

**问题描述**: 存在3层嵌套的代码副本，形成"俄罗斯套娃"结构

```
c:\scc\                       # 主仓库
├── oc-scc-local/             # 主实现（Node.js）
├── tools/scc/                # Python工具集
│
├── scc-top\                  # 子项目目录
│   ├── tools/oc-scc-local/   # 只是导入主实现的"包装器"
│   └── _docker_ctx_scc\      # Docker上下文 - 包含完整代码副本！
│       ├── tools/scc/        # 再次复制Python工具
│       └── tools/oc-scc-local/  # 再次复制Node.js代码
```

**代码证据**:

文件: `scc-top/tools/oc-scc-local/src/gateway.mjs`
```javascript
// Thin wrapper to avoid maintaining two diverging gateways.
// This package is used by SCC "top" tooling, while the primary implementation lives in repo root.
import "../../../../oc-scc-local/src/gateway.mjs"
```

**分析**: 开发者明知有重复，却选择用"包装器"方式处理，而非正确的依赖管理。

**影响**:
- 任何代码修改需要在多个位置同步
- Docker构建时可能使用错误版本
- 代码库体积膨胀

---

### 1.2 目录职责不清晰

| 目录 | 内容 | 问题 |
|------|------|------|
| `tools/scc/` | Python工具 | 命名与 `scc-top/tools/scc/` 冲突 |
| `scc-top/tools/scc/` | 重复的Python工具 | 与主目录功能重叠 |
| `scc-top/tools/unified_server/` | 统一服务器 | 与 `tools/scc/` 边界不清 |
| `scc-top/_docker_ctx_scc/` | Docker上下文 | 包含完整代码副本 |
| `scc-top/tools/mcp_bus/` | MCP总线 | 包含中文文件名（不符合规范） |

---

## 2. 重复代码问题

### 2.1 工具函数重复定义

**`_norm_rel()` 函数重复8次**（完全相同的功能）:

| 文件路径 | 行号 | 代码 |
|----------|------|------|
| `tools/scc/gates/schema_gate.py` | L6 | `def _norm_rel(p: str) -> str: return p.replace("\\", "/").lstrip("./")` |
| `tools/scc/gates/contracts_gate.py` | L14 | 同上 |
| `tools/scc/gates/ssot_map_gate.py` | L7 | 同上 |
| `tools/scc/gates/context_pack_gate.py` | L7 | 同上 |
| `tools/scc/gates/context_pack_proof_gate.py` | L8 | 同上 |
| `tools/scc/runtime/unified_diff_guard.py` | L15 | 同上 |
| `tools/scc/ops/pr_bundle_create.py` | L28 | 同上 |
| `tools/scc/validators/hygiene_validator.py` | L16 | 同上 |

**`_load_json()` 函数重复5次**:

| 文件路径 | 行号 |
|----------|------|
| `tools/scc/gates/ssot_map_gate.py` | L11 |
| `tools/scc/gates/context_pack_proof_gate.py` | L12 |
| `tools/scc/gates/schema_gate.py` | L10 |
| `tools/scc/gates/context_pack_gate.py` | L11 |
| `tools/s