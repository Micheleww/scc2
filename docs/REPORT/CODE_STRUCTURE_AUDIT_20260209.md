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
| `tools/scc/selftest/validate_contract_examples.py` | L8 |

**代码示例**:
```python
def _load_json(path: pathlib.Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
```

---

### 2.2 PowerShell脚本重复

**worker-codex.ps1 vs worker-opencodecli.ps1**:

重复代码段（约50行完全相同）:
```powershell
# 两者都有:
$ocRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $ocRoot
$ExecRoot = $repoRoot

# 环境变量处理（完全相同）:
$env:CONTEXT_PACK_V1_REQUIRED = "true"

# 网关地址解析（完全相同）:
$Base = if ($env:SCC_GATEWAY_URL) { $env:SCC_GATEWAY_URL } else { "http://127.0.0.1:18788" }
```

**差异**: 仅执行命令不同（`codex` vs `opencodecli`）

---

### 2.3 Python运行时逻辑重复

**`orchestrator_v1.py` 和 `run_child_task.py`**:

重复逻辑:
```python
# orchestrator_v1.py L15
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# run_child_task.py L18
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
```

两者都实现:
- REPO_ROOT 计算
- JSON文件读写
- 事件日志记录（`state_events.jsonl`）
- WIP限制检查

---

## 3. 导入依赖混乱

### 3.1 动态修改 sys.path（不良实践）

**多处代码使用此hack方式**:

文件: `tools/scc/runtime/run_child_task.py` L18-24
```python
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.scc.runtime.diff_extract import extract_unified_diff  # noqa: E402
from tools.scc.runtime.unified_diff_apply import apply_unified_diff  # noqa: E402
from tools.scc.runtime.unified_diff_guard import guard_diff  # noqa: E402
```

文件: `tools/scc/gates/run_ci_gates.py` L9-30
```python
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.scc.gates import (
    connector_gate,
    context_pack_gate,
    # ... 更多导入
)
```

**问题**:
1. 使用 `# noqa: E402` 抑制导入顺序警告
2. 说明包结构本身有问题
3. 导致测试困难、命名空间冲突

---

### 3.2 跨语言调用混乱

**Python调用Node.js**:

文件: `tools/scc/runtime/run_child_task.py` L226
```python
code, _, _ = _run(["npm", "--prefix", "oc-scc-local", "run", "-s", "map:build"], ...)
```

文件: `tools/scc/runtime/run_child_task.py` L266-267
```python
["node", "oc-scc-local/scripts/pins_build_v1.mjs", "--request", ...]
```

**Node.js调用Python**:

文件: `oc-scc-local/scripts/selfcheck_map_v1.mjs`
```javascript
await execFile('python', ['tools/scc/gates/run_ci_gates.py', ...])
```

**影响**: 依赖关系难以追踪，调试困难

---

### 3.3 循环依赖风险

**gates之间的交叉导入**:

`run_ci_gates.py` 导入13个gate模块:
```python
from tools.scc.gates import (
    connector_gate,
    context_pack_gate,
    context_pack_proof_gate,
    contracts_gate,
    doclink_gate,
    event_gate,
    map_gate,
    release_gate,
    schema_gate,
    semantic_context_gate,
    ssot_gate,
    ssot_map_gate,
    trace_gate,
    verifier_judge,
)
```

这些gate模块可能相互依赖，形成循环依赖。

---

## 4. 配置文件分散和重复

### 4.1 package.json 重复

| 文件 | scripts数量 | 差异 |
|------|-------------|------|
| `oc-scc-local/package.json` | 41个 | 完整版本 |
| `scc-top/tools/oc-scc-local/package.json` | 4个 | 简化版本 |

**主版本scripts示例**:
```json
"scripts": {
  "start": "node src/gateway.mjs",
  "map:build": "node scripts/map_build_v1.mjs",
  "pins:build": "node scripts/pins_builder_v1.mjs",
  "preflight": "node scripts/preflight_v1.mjs",
  // ... 共41个
}
```

**scc-top版本**:
```json
"scripts": {
  "start": "node src/gateway.mjs",
  "gateway": "node src/gateway.mjs",
  "smoke": "node src/smoke.mjs",
  "test": "echo \"Error: no test specified\" && exit 1"
}
```

---

### 4.2 requirements.txt 重复

| 文件路径 | 内容 |
|----------|------|
| `scc-top/requirements.txt` | pyyaml, pytest, requests, psycopg2-binary |
| `scc-top/tools/unified_server/requirements.txt` | FastAPI相关依赖 |
| `scc-top/_docker_ctx_scc/tools/unified_server/requirements.txt` | 完全相同的副本 |

**分析**: Docker上下文中的requirements.txt与主目录完全相同，属于不必要的复制。

---

### 4.3 角色配置文件版本不一致

**`oc-scc-local/config/roles.json`** (167行):
- 17个角色定义
- 包含完整角色规范

**`scc-top/tools/oc-scc-local/config/roles.json`** (83行):
- 仅9个角色
- 缺失角色:
  - ssot_curator
  - doc_adr_scribe
  - retry_orchestrator
  - stability_controller
  - playbook_publisher
  - eval_curator
  - lessons_miner
  - preflight_gate
  - verifier_judge

**风险**: 不同组件使用不同版本的角色配置，可能导致行为不一致。

---

### 4.4 factory_policy.json 位置问题

文件: `factory_policy.json` (根目录)

问题:
1. 没有对应的schema验证
2. 与 `contracts/factory_policy/factory_policy.schema.json` 的关系不明确
3. 位于根目录而非 `config/` 目录

---

## 5. 脚本文件组织问题

### 5.1 PowerShell脚本分布混乱

| 目录 | 脚本数量 | 用途 |
|------|----------|------|
| `oc-scc-local/scripts/` | ~20个 | 主网关脚本 |
| `scc-top/tools/oc-scc-local/scripts/` | ~15个 | 重复/包装脚本 |
| `scc-top/tools/unified_server/` | ~8个 | 服务器管理脚本 |
| `scc-top/_docker_ctx_scc/tools/mcp_bus/` | ~20个 | MCP总线脚本（含中文文件名） |
| **根目录** | ~15个 | 临时/测试脚本 |

**根目录临时脚本列表**:
```
submit_jobs.ps1, submit_jobs2.ps1
submit_jobs_A.ps1, submit_jobs_B.ps1, submit_jobs_B_patch.ps1, submit_jobs_C.ps1
spawn_occli.ps1, submit_one_occli.ps1, poll_one_occli.ps1
create_opencode_shortcut.ps1, create_opencode_shortcut_v2.ps1, create_opencode_shortcut_fixed.ps1
poll_jobs.ps1, count_jobs.ps1, dump_jobs.ps1
```

**分析**: 这些脚本是迭代开发的产物，应该合并或清理。

---

### 5.2 Node.js脚本命名不一致

**命名规范混用**:

| 文件名 | 分隔符 |
|--------|--------|
| `map_build_v1.mjs` | `_` |
| `pins_build_v1.mjs` | `_` |
| `selfcheck_map_v1.mjs` | `_` |
| `daemon-start.ps1` | `-` |
| `restart-when-idle.ps1` | `-` |
| `start-opencode.ps1` | `-` |

---

### 5.3 Python脚本缺乏统一入口

**tools/scc/ 结构**:
```
tools/scc/
├── gates/          # CI gates - 13个独立脚本
├── runtime/        # 运行时 - 5个脚本
├── ops/            # 运维操作 - 15+个脚本
├── validators/     # 验证器 - 2个脚本
├── map/            # Map相关 - 3个脚本
├── selftest/       # 自测 - 5个脚本
├── models/         # 模型 - 6个文件
```

**问题**:
1. 没有统一的CLI入口
2. 每个脚本独立处理参数解析
3. 重复的路径计算逻辑（REPO_ROOT）

---

## 6. 版本碎片化问题

### 6.1 Schema版本重复

**pins_result 两个版本**:
- `contracts/pins/pins_result.schema.json` (v1)
- `contracts/pins/pins_result_v2.schema.json` (v2)

**分析**: 代码需要同时处理两个版本，增加复杂性。

### 6.2 脚本版本迭代遗留

**create_opencode_shortcut 三个版本**:
- `create_opencode_shortcut.ps1`
- `create_opencode_shortcut_v2.ps1`
- `create_opencode_shortcut_fixed.ps1`

**submit_jobs 多个版本**:
- `submit_jobs.ps1`, `submit_jobs2.ps1`
- `submit_jobs_A.ps1`, `submit_jobs_B.ps1`, `submit_jobs_C.ps1`

---

## 7. 具体问题清单

### 7.1 高优先级（立即修复）

| 序号 | 问题 | 文件/位置 | 影响 |
|------|------|-----------|------|
| 1 | 嵌套代码库重复 | `scc-top/_docker_ctx_scc/` | 维护困难，体积膨胀 |
| 2 | 工具函数重复 | 8个文件有 `_norm_rel()` | 违反DRY原则 |
| 3 | sys.path动态修改 | `run_child_task.py`, `run_ci_gates.py` | 不良实践，测试困难 |
| 4 | 角色配置版本不一致 | `roles.json` 两个版本 | 行为不一致风险 |
| 5 | 根目录临时脚本堆积 | 根目录 ~15个ps1文件 | 混乱，难以维护 |

### 7.2 中优先级（计划修复）

| 序号 | 问题 | 文件/位置 | 影响 |
|------|------|-----------|------|
| 6 | PowerShell脚本重复 | `worker-*.ps1` | 应该抽象通用逻辑 |
| 7 | 命名规范不一致 | 多处 `-` vs `_` | 可读性下降 |
| 8 | Python缺乏统一入口 | `tools/scc/` | 使用不便 |
| 9 | package.json重复 | 两个版本 | 维护成本 |
| 10 | requirements.txt重复 | 3个副本 | 维护成本 |

### 7.3 低优先级（可选优化）

| 序号 | 问题 | 文件/位置 | 影响 |
|------|------|-----------|------|
| 11 | 跨语言调用混乱 | Python/Node.js互相调用 | 调试困难 |
| 12 | factory_policy.json位置 | 根目录 | 不符合配置规范 |
| 13 | Schema版本重复 | pins_result v1/v2 | 代码复杂度 |

---

## 8. 附录：重复代码详细对比

### 8.1 `_norm_rel()` 函数对比

```python
# tools/scc/gates/schema_gate.py
def _norm_rel(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")

# tools/scc/gates/contracts_gate.py  
def _norm_rel(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")

# tools/scc/gates/ssot_map_gate.py
def _norm_rel(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")

# ... 其他5个文件完全相同
```

**建议**: 提取到 `tools/scc/lib/utils.py`

---

### 8.2 `_load_json()` 函数对比

```python
# tools/scc/gates/schema_gate.py
def _load_json(path: pathlib.Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# tools/scc/gates/context_pack_gate.py
def _load_json(path: pathlib.Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
```

**建议**: 提取到共享库

---

## 9. 总结

### 9.1 核心问题

1. **架构债务严重**: 3层嵌套代码副本，维护成本极高
2. **违反DRY原则**: 工具函数重复定义8次以上
3. **包结构缺陷**: 必须使用sys.path hack才能导入
4. **配置碎片化**: 同一配置多个版本，内容不一致
5. **根目录失控**: 临时脚本没有清理机制

### 9.2 风险等级

| 风险 | 等级 | 说明 |
|------|------|------|
| 维护成本 | 🔴 高 | 修改需在多处同步 |
| 行为不一致 | 🔴 高 | 配置版本不同 |
| 引入bug | 🟡 中 | 重复代码更新遗漏 |
| 新人 onboarding | 🔴 高 | 目录结构混乱 |
| 构建失败 | 🟡 中 | Docker上下文可能用错版本 |

### 9.3 建议优先级

1. **立即**: 清理根目录临时脚本，创建共享工具库
2. **短期**: 统一配置文件，消除重复版本
3. **中期**: 重构包结构，消除sys.path hack
4. **长期**: 清理嵌套代码库，建立正确的依赖关系

---

*报告结束*
