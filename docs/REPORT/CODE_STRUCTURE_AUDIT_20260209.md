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

### 2.2 SQLite查询模块重复（新发现）

**问题描述**: 两个文件几乎完全相同，只是函数名和 main() 逻辑有差异

- **文件1**: `tools/scc/map/map_query_sqlite_v1.py`
- **文件2**: `tools/scc/map/map_query_sqlite_batch_v1.py`

**重复代码片段**:
```python
# 两个文件都有完全相同的辅助函数
def _default_repo_root() -> str:
    return str(pathlib.Path(__file__).resolve().parents[3])

def _connect(path: pathlib.Path) -> sqlite3.Connection:
    return sqlite3.connect(str(path))

def _score(kind: str) -> float:
    if kind == "key_symbol":
        return 3.0
    if kind == "entry_point":
        return 2.0
    # ... 完全相同的评分逻辑
```

**修复建议**: 将公共函数提取到共享模块 `tools/scc/map/common.py`

---

### 2.3 测试辅助函数重复

- **文件**: `scc-top/tools/gatekeeper/tests/test_signature_verification_simple.py` 和 `scc-top/tools/gatekeeper/tests/test_signature_verifier.py`

**重复代码**:
```python
def calculate_file_hash(file_path):
    """计算文件的SHA256哈希值"""
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
```

**修复建议**: 将辅助函数提取到 `tests/common.py` 或 `test_utils.py`

---

### 2.4 PowerShell脚本重复

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

### 2.5 Python运行时逻辑重复

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

**发现 100+ 处 sys.path 修改**，这是一个严重的架构问题。

**主要受影响文件**:
| 文件路径 | 出现次数 |
|---------|---------|
| `projects/quantsys/services/mcp_bus/server/main.py` | 5 |
| `scc-top/tools/unified_server/services/service_wrappers.py` | 2 |
| `scc-top/tools/unified_server/exchange_server_integration.py` | 2 |
| `scc-top/tools/unified_server/mcp_bus_integration.py` | 3 |

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

## 4. 硬编码路径问题（新发现）

### 4.1 硬编码的绝对路径

**文件**: `scc-top/tools/scc/ops/evidence_antiforgery_audit.py` 第56行
```python
ap.add_argument("--repo", default=r"C:\scc", help="Repo umbrella root (default: C:\\scc)")
```

**修复建议**: 
```python
import os
default_repo = os.getenv("SCC_REPO_ROOT", os.getcwd())
ap.add_argument("--repo", default=default_repo, help="Repo umbrella root")
```

---

### 4.2 硬编码的 Windows 路径

**文件**: `scc-top/tools/gatekeeper/tests/test_signature_verification_simple.py` 第15行
**文件**: `scc-top/tools/gatekeeper/tests/test_signature_verifier.py` 第16行

```python
sys.path.insert(0, "d:/quantsys")
```

**修复建议**: 使用相对路径或环境变量

---

## 5. 配置文件分散和重复

### 5.1 package.json 重复

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

### 5.2 requirements.txt 重复

| 文件路径 | 内容 |
|----------|------|
| `scc-top/requirements.txt` | pyyaml, pytest, requests, psycopg2-binary |
| `scc-top/tools/unified_server/requirements.txt` | FastAPI相关依赖 |
| `scc-top/_docker_ctx_scc/tools/unified_server/requirements.txt` | 完全相同的副本 |

**分析**: Docker上下文中的requirements.txt与主目录完全相同，属于不必要的复制。

---

### 5.3 角色配置文件版本不一致

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

### 5.4 重复配置文件（新发现）

**完全相同的配置文件**:
- **文件1**: `projects/quantsys/services/mcp_bus/config/config.example.json`
- **文件2**: `scc-top/tools/mcp_bus/config/config.example.json`

**内容**: 两个文件完全相同 (34行 JSON 配置)

**修复建议**: 
- 删除其中一个，使用符号链接
- 或将配置提取到共享位置，两个项目引用同一文件

---

### 5.5 factory_policy.json 位置问题

文件: `factory_policy.json` (根目录)

问题:
1. 没有对应的schema验证
2. 与 `contracts/factory_policy/factory_policy.schema.json` 的关系不明确
3. 位于根目录而非 `config/` 目录

---

## 6. 脚本文件组织问题

### 6.1 PowerShell脚本分布混乱

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

### 6.2 Node.js脚本命名不一致

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

### 6.3 Python脚本缺乏统一入口

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

## 7. 大型文件问题（新发现）

### 7.1 超大型文件列表

| 文件路径 | 行数 | 风险等级 |
|---------|------|---------|
| `projects/quantsys/services/mcp_bus/server/main.py` | **7,269** | 极高 |
| `scc-top/tools/unified_server/core/app_factory.py` | **4,855** | 极高 |
| `scc-top/tools/scc/orchestrators/cc_like.py` | 估计 800+ | 高 |
| `scc-top/tools/scc/orchestrators/fullagent_loop.py` | 估计 600+ | 高 |

### 7.2 主要问题

**文件**: `projects/quantsys/services/mcp_bus/server/main.py` (7,269 行)
- 包含多个 TODO 注释
- 混合了业务逻辑、API 端点、工具函数
- 难以维护和测试

**修复建议**:
1. 按功能拆分为多个模块:
   - `routes/` - API 路由
   - `services/` - 业务逻辑
   - `models/` - 数据模型
   - `tools/` - 工具函数

---

## 8. TODO/FIXME 注释（新发现）

### 8.1 高频 TODO 文件

**文件**: `projects/quantsys/services/mcp_bus/server/main.py`

发现 **40+** 个 TODO 注释，包括:

```python
# TODO: Implement actual performance attribution logic
# TODO: Implement actual VaR calculation
# TODO: Implement actual CVaR calculation
# TODO: Implement actual strategy optimization logic
# TODO: 从存储中读取组合列表
# TODO: 实现再平衡逻辑
# TODO: 从配置或历史记录获取初始资金
# TODO: 实现按策略或品种分解盈亏
# TODO: 实现盈亏归因分析
# TODO: 实现风险归因分析
# TODO: 实现因子暴露分析
# TODO: 实现成本分析
# TODO: 实现VaR计算
# TODO: 实现CVaR计算
# TODO: 实现压力测试逻辑
# TODO: 实现策略参数优化逻辑
# TODO: 实现因子参数优化逻辑
```

**修复建议**: 
- 创建 GitHub Issues 或任务追踪
- 按优先级分类处理
- 对于占位符实现，添加更明确的文档说明

---

## 9. 未使用的导入（新发现）

### 9.1 已发现的未使用导入

**文件**: `tools/scc/ops/eval_replay.py`
```python
from typing import Any, Dict, List  # List 和 Dict 可能未完全使用
```

**文件**: `tools/scc/map/map_query_sqlite_batch_v1.py`
```python
from typing import Any, Dict, List, Tuple  # Tuple 未使用
```

**文件**: `tools/scc/map/map_query_sqlite_v1.py`
```python
from typing import Any, Dict, List, Tuple  # Tuple 和 Any 未使用
```

**修复建议**: 使用 `flake8` 或 `pylint` 自动检测并清理未使用的导入

---

## 10. 版本碎片化问题

### 10.1 Schema版本重复

**pins_result 两个版本**:
- `contracts/pins/pins_result.schema.json` (v1)
- `contracts/pins/pins_result_v2.schema.json` (v2)

**分析**: 代码需要同时处理两个版本，增加复杂性。

---

### 10.2 脚本版本迭代遗留

**create_opencode_shortcut 三个版本**:
- `create_opencode_shortcut.ps1`
- `create_opencode_shortcut_v2.ps1`
- `create_opencode_shortcut_fixed.ps1`

**submit_jobs 多个版本**:
- `submit_jobs.ps1`, `submit_jobs2.ps1`
- `submit_jobs_A.ps1`, `submit_jobs_B.ps1`, `submit_jobs_C.ps1`

---

## 11. 其他问题（新发现）

### 11.1 混合语言注释

**文件**: `scc-top/tools/unified_server/core/app_factory.py`

文件开头有乱码注释 (可能是编码问题):
```python
"""
搴旂敤宸ュ巶妯″潡
...
"""
```

**修复建议**: 统一使用 UTF-8 编码，修复乱码注释

---

### 11.2 已存在的自检工具

发现项目已有自检工具:
- `tools/scc/selftest/selfcheck_no_hardcoded_paths.py` - 检测硬编码路径
- `tools/scc/selftest/selfcheck_no_shell_true.py` - 检测 shell=True

但这些工具本身也需要改进，例如硬编码路径检测工具只检测特定模式，未覆盖所有情况。

---

## 12. 具体问题清单

### 12.1 高优先级（立即修复）

| 序号 | 问题 | 文件/位置 | 影响 | 状态 |
|------|------|-----------|------|------|
| 1 | 嵌套代码库重复 | `scc-top/_docker_ctx_scc/` | 维护困难，体积膨胀 | ✅ 已删除 |
| 2 | 工具函数重复 | 8个文件有 `_norm_rel()` | 违反DRY原则 | ✅ 已提取到共享库 |
| 3 | sys.path动态修改 | `run_child_task.py`, `run_ci_gates.py` 等100+处 | 不良实践，测试困难 | ⚠️ 部分修复 |
| 4 | 角色配置版本不一致 | `roles.json` 两个版本 | 行为不一致风险 | ✅ 已删除重复 |
| 5 | 根目录临时脚本堆积 | 根目录 ~15个ps1文件 | 混乱，难以维护 | ⏳ 待处理 |
| 6 | 超大型文件 | `main.py` 7269行, `app_factory.py` 4855行 | 维护困难 | ⚠️ 部分拆分 |
| 7 | 硬编码路径 | 多处 `C:cc`, `d:/quantsys` | 可移植性差 | ✅ 已修复 |

### 12.2 中优先级（计划修复）

| 序号 | 问题 | 文件/位置 | 影响 | 状态 |
|------|------|-----------|------|------|
| 8 | PowerShell脚本重复 | `worker-*.ps1` | 应该抽象通用逻辑 | ⏳ 待处理 |
| 9 | SQLite查询模块重复 | `map_query_sqlite_*.py` | 代码重复 | ✅ 已提取公共函数 |
| 10 | 命名规范不一致 | 多处 `-` vs `_` | 可读性下降 | ⏳ 待处理 |
| 11 | Python缺乏统一入口 | `tools/scc/` | 使用不便 | ✅ 已创建 cli.py |
| 12 | package.json重复 | 两个版本 | 维护成本 | ✅ 确认合理（包装器） |
| 13 | requirements.txt重复 | 3个副本 | 维护成本 | ✅ 确认合理（不同依赖） |
| 14 | 重复配置文件 | `config.example.json` | 维护成本 | ✅ 已删除重复 |

### 12.3 低优先级（可选优化）

| 序号 | 问题 | 文件/位置 | 影响 |
|------|------|-----------|------|
| 15 | 跨语言调用混乱 | Python/Node.js互相调用 | 调试困难 |
| 16 | factory_policy.json位置 | 根目录 | 不符合配置规范 |
| 17 | Schema版本重复 | pins_result v1/v2 | 代码复杂度 |
| 18 | TODO注释清理 | 40+个TODO | 技术债务 |
| 19 | 未使用的导入 | 多处 | 代码整洁 |
| 20 | 乱码注释 | `app_factory.py` | 可读性 |

---

## 13. 附录：重复代码详细对比

### 13.1 `_norm_rel()` 函数对比

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

### 13.2 `_load_json()` 函数对比

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

## 14. 总结与建议优先级

### 14.1 核心问题

1. **架构债务严重**: 3层嵌套代码副本，维护成本极高
2. **违反DRY原则**: 工具函数重复定义8次以上
3. **包结构缺陷**: 必须使用sys.path hack才能导入（100+处）
4. **配置碎片化**: 同一配置多个版本，内容不一致
5. **根目录失控**: 临时脚本没有清理机制
6. **超大型文件**: 7000+行的Python文件难以维护
7. **硬编码路径**: 多处Windows绝对路径

### 14.2 风险等级

| 风险 | 等级 | 说明 |
|------|------|------|
| 维护成本 | 🔴 高 | 修改需在多处同步 |
| 行为不一致 | 🔴 高 | 配置版本不同 |
| 引入bug | 🟡 中 | 重复代码更新遗漏 |
| 新人 onboarding | 🔴 高 | 目录结构混乱 |
| 构建失败 | 🟡 中 | Docker上下文可能用错版本 |
| 可移植性 | 🔴 高 | 硬编码Windows路径 |

### 14.3 建议优先级

| 优先级 | 问题类型 | 影响 | 修复复杂度 |
|-------|---------|------|-----------|
| P0 | sys.path hack (100+处) | 高 | 中 |
| P0 | 超大型文件 (7000+行) | 极高 | 高 |
| P0 | 硬编码路径 | 中 | 低 |
| P1 | 重复代码模式 | 中 | 低 |
| P1 | SQLite查询模块重复 | 中 | 低 |
| P1 | 重复配置文件 | 低 | 低 |
| P2 | 未使用的导入 | 低 | 低 |
| P2 | TODO 注释清理 | 中 | 中 |
| P3 | 乱码注释修复 | 低 | 低 |

**建议立即处理的问题**:
1. 统一项目结构，消除 `sys.path` 修改
2. 拆分 `main.py` 和 `app_factory.py` 为更小的模块
3. 修复硬编码的 Windows 路径
4. 清理未使用的导入

---

*报告结束 - 2026-02-09*
