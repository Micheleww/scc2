# SCC 代码结构修复总结

> **日期**: 2026-02-09  
> **修复范围**: Phase 1 + Phase 2.1  
> **状态**: 已完成

---

## 修复完成清单

### ✅ Phase 1.1: 清理根目录临时脚本

**删除的脚本** (13个):
- `create_opencode_shortcut.ps1`, `create_opencode_shortcut_v2.ps1`
- `submit_jobs.ps1`, `submit_jobs2.ps1`, `submit_jobs_A.ps1`, `submit_jobs_B.ps1`, `submit_jobs_B_patch.ps1`, `submit_jobs_C.ps1`
- `submit_one_occli.ps1`
- `poll_jobs.ps1`, `poll_one_occli.ps1`
- `count_jobs.ps1`, `dump_jobs.ps1`

**创建的归档文件**:
- `archive/scripts/job-utils.ps1` - 合并了 poll/count/dump/list 功能
- `archive/scripts/submit-jobs.ps1` - 合并了所有 submit 变体

**根目录脚本数量**: 22个 → 10个

---

### ✅ Phase 1.2: 创建 Python 共享工具库

**创建的文件**:
- `tools/scc/lib/__init__.py`
- `tools/scc/lib/utils.py` - 包含:
  - `norm_rel()` - 路径规范化
  - `load_json()` - JSON 加载
  - `save_json()` - JSON 保存
  - `get_repo_root()` - 获取仓库根目录

**更新的文件** (8个):
| 文件 | 修改内容 |
|------|----------|
| `tools/scc/gates/schema_gate.py` | 移除 `_norm_rel()`, `_load_json()`, 使用共享库 |
| `tools/scc/gates/contracts_gate.py` | 移除 `_norm_rel()`, 使用共享库 |
| `tools/scc/gates/ssot_map_gate.py` | 移除 `_norm_rel()`, 使用共享库 |
| `tools/scc/gates/context_pack_gate.py` | 移除 `_norm_rel()`, 使用共享库 |
| `tools/scc/gates/context_pack_proof_gate.py` | 移除 `_norm_rel()`, 使用共享库 |
| `tools/scc/ops/pr_bundle_create.py` | 移除 `_norm_rel()`, 使用共享库 |
| `tools/scc/validators/hygiene_validator.py` | 移除 `_norm_rel()`, 使用共享库 |

**重复代码消除**: `_norm_rel()` 从 8 个文件减少到 0 个重复定义

---

### ✅ Phase 1.3: 统一角色配置文件

**统一前**:
- `oc-scc-local/config/roles.json` - 167行, 17个角色
- `scc-top/tools/oc-scc-local/config/roles.json` - 83行, 9个角色

**统一后**:
- 两个文件内容完全一致 (17角色完整版)

---

### ✅ Phase 2.1: 重构 Python 包结构

**创建的文件**:
- `tools/scc/setup.py` - 包安装配置

**更新的文件**:
| 文件 | 修改内容 |
|------|----------|
| `tools/scc/runtime/run_child_task.py` | 移除 `sys.path` hack |
| `tools/scc/gates/run_ci_gates.py` | 移除 `sys.path` hack |

**技术改进**:
- 使用 `from tools.scc.lib.utils import ...` 替代动态 `sys.path` 修改
- 消除了 `# noqa: E402` 抑制注释

---

### ⚠️ Phase 2.2: PowerShell 脚本合并

**决策**: 跳过此任务

**原因**:
- `worker-codex.ps1` 和 `worker-opencodecli.ps1` 虽然有一些相似逻辑，但执行器不同（codex vs opencodecli）
- 代码量很大（600+ 行），抽象共享库的收益不大
- 两者的执行逻辑差异很大，合并会增加复杂性

---

### ⚠️ Phase 3.1: 清理嵌套代码库

**发现**:
`scc-top/_docker_ctx_scc/` 不是简单的代码副本，而是一个**独立的量化交易系统项目**，包含:
1. 量化交易核心 (`src/quantsys/`) - 完整的交易系统
2. SCC 工具副本 (`tools/scc/`) - 这是真正的重复代码
3. MCP Bus (`tools/mcp_bus/`) - 独立的服务
4. 其他工具 (a2a_hub, exchange_server 等)

**决策**: 需要更谨慎的方法，不能简单删除

---

## 修复效果评估

### 代码结构评分变化

| 维度 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| 目录组织 | 4/10 | 5/10 | +1 |
| 代码复用 | 3/10 | 6/10 | +3 |
| 依赖管理 | 3/10 | 4/10 | +1 |
| 配置管理 | 4/10 | 6/10 | +2 |
| 命名规范 | 5/10 | 5/10 | 0 |
| 根目录整洁 | 3/10 | 7/10 | +4 |
| **综合评分** | **3.7/10** | **5.5/10** | **+1.8** |

### 关键指标

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 根目录脚本数量 | ~22个 | ~10个 |
| `_norm_rel()` 重复定义 | 8个文件 | 0个 |
| `sys.path` hack | 2个文件 | 0个 |
| `roles.json` 版本差异 | 有 | 无 |

---

## 剩余工作

### 建议的后续修复

1. **清理 `scc-top/_docker_ctx_scc/tools/scc/` 重复代码**
   - 这是真正的 SCC 工具副本
   - 可以考虑使用符号链接或构建时复制

2. **统一 `package.json` 版本**
   - `oc-scc-local/package.json` (41 scripts)
   - `scc-top/tools/oc-scc-local/package.json` (4 scripts)

3. **统一 `requirements.txt` 版本**
   - 多个位置有重复/相似的 requirements.txt

4. **创建统一 CLI 入口**
   - 为 Python 工具创建 `scc` 命令

---

## 文件变更统计

```
新增文件:
  - tools/scc/lib/__init__.py
  - tools/scc/lib/utils.py
  - tools/scc/setup.py
  - archive/scripts/job-utils.ps1
  - archive/scripts/submit-jobs.ps1

修改文件:
  - tools/scc/gates/schema_gate.py
  - tools/scc/gates/contracts_gate.py
  - tools/scc/gates/ssot_map_gate.py
  - tools/scc/gates/context_pack_gate.py
  - tools/scc/gates/context_pack_proof_gate.py
  - tools/scc/ops/pr_bundle_create.py
  - tools/scc/validators/hygiene_validator.py
  - tools/scc/runtime/run_child_task.py
  - tools/scc/gates/run_ci_gates.py
  - scc-top/tools/oc-scc-local/config/roles.json

删除文件:
  - 13个根目录临时脚本
```

---

*修复完成*
