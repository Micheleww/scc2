# SCC 代码结构修复计划

> **日期**: 2026-02-09  
> **基于**: CODE_STRUCTURE_AUDIT_20260209.md  
> **目标**: 将代码结构评分从 3.7/10 提升到 7+/10

---

## 执行摘要

### 修复阶段

| 阶段 | 时间 | 目标评分 | 主要任务 |
|------|------|----------|----------|
| **Phase 1** | 1-2天 | 5.0/10 | 清理根目录、创建共享库、统一配置 |
| **Phase 2** | 3-5天 | 6.0/10 | 消除重复代码、重构导入 |
| **Phase 3** | 1-2周 | 7.0/10 | 清理嵌套代码库、建立正确依赖 |

---

## Phase 1: 立即修复（1-2天）

### 任务 1.1: 清理根目录临时脚本

**目标**: 移除根目录下 ~15 个临时脚本

**文件清单**:
```
submit_jobs.ps1, submit_jobs2.ps1
submit_jobs_A.ps1, submit_jobs_B.ps1, submit_jobs_B_patch.ps1, submit_jobs_C.ps1
spawn_occli.ps1, submit_one_occli.ps1, poll_one_occli.ps1
create_opencode_shortcut.ps1, create_opencode_shortcut_v2.ps1, create_opencode_shortcut_fixed.ps1
poll_jobs.ps1, count_jobs.ps1, dump_jobs.ps1
```

**执行步骤**:
1. 确定每个脚本的最新有效版本
2. 合并功能到 `oc-scc-local/scripts/` 或归档到 `archive/scripts/`
3. 删除根目录下的旧版本
4. 更新任何引用这些脚本的文档

**决策矩阵**:

| 脚本 | 保留版本 | 处理方式 |
|------|----------|----------|
| submit_jobs*.ps1 | 最新版本 | 移动到 `scripts/` 目录 |
| create_opencode_shortcut*.ps1 | _fixed 版本 | 重命名为 `create_opencode_shortcut.ps1`，其余删除 |
| spawn_occli.ps1 | 保留 | 移动到 `oc-scc-local/scripts/` |
| poll_*.ps1 | 合并 | 合并为 `job_utils.ps1` |
| count_jobs.ps1, dump_jobs.ps1 | 保留 | 移动到 `scripts/` |

---

### 任务 1.2: 创建 Python 共享工具库

**目标**: 消除 `_norm_rel()` 和 `_load_json()` 的重复定义

**执行步骤**:

1. **创建共享库文件**:
```bash
mkdir -p tools/scc/lib/
touch tools/scc/lib/__init__.py
touch tools/scc/lib/utils.py
```

2. **实现 `tools/scc/lib/utils.py`**:
```python
"""Shared utilities for SCC tools."""
import json
import pathlib
from typing import Any


def norm_rel(p: str) -> str:
    """Normalize path to use forward slashes and remove leading ./"""
    return p.replace("\\", "/").lstrip("./")


def load_json(path: pathlib.Path) -> Any:
    """Load JSON file with UTF-8 encoding."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: pathlib.Path, data: Any) -> None:
    """Save data to JSON file with UTF-8 encoding."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_repo_root() -> pathlib.Path:
    """Get repository root path."""
    return pathlib.Path(__file__).resolve().parents[3]
```

3. **批量替换重复代码**:

使用脚本自动化替换以下文件中的重复函数:
- `tools/scc/gates/schema_gate.py`
- `tools/scc/gates/contracts_gate.py`
- `tools/scc/gates/ssot_map_gate.py`
- `tools/scc/gates/context_pack_gate.py`
- `tools/scc/gates/context_pack_proof_gate.py`
- `tools/scc/runtime/unified_diff_guard.py`
- `tools/scc/ops/pr_bundle_create.py`
- `tools/scc/validators/hygiene_validator.py`

**替换模式**:
```python
# 删除旧代码:
def _norm_rel(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")

def _load_json(path: pathlib.Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# 添加新导入:
from tools.scc.lib.utils import norm_rel, load_json
```

---

### 任务 1.3: 统一角色配置文件

**目标**: 消除 `roles.json` 的两个版本

**当前状态**:
- `oc-scc-local/config/roles.json` (167行, 17角色) - 完整版
- `scc-top/tools/oc-scc-local/config/roles.json` (83行, 9角色) - 简化版

**执行步骤**:

1. **确定权威版本**: 使用完整版 (17角色)

2. **替换简化版**:
```bash
cp oc-scc-local/config/roles.json scc-top/tools/oc-scc-local/config/roles.json
```

3. **创建符号链接方案**（可选）:
```bash
# 删除重复文件
rm scc-top/tools/oc-scc-local/config/roles.json

# 创建符号链接（Windows）
cd scc-top/tools/oc-scc-local/config
mklink roles.json ..\..\..\..\oc-scc-local\config\roles.json
```

4. **添加一致性检查**:
在 CI 中添加检查，确保两个文件一致:
```python
# tools/scc/selftest/check_config_consistency.py
import json
import sys

def check_roles_consistency():
    with open("oc-scc-local/config/roles.json") as f:
        main = json.load(f)
    with open("scc-top/tools/oc-scc-local/config/roles.json") as f:
        sub = json.load(f)
    
    if main != sub:
        print("ERROR: roles.json versions are inconsistent!")
        sys.exit(1)
    print("OK: roles.json is consistent")
```

---

### Phase 1 完成标准

- [ ] 根目录无临时脚本
- [ ] `tools/scc/lib/utils.py` 创建并可用
- [ ] 8个文件中的 `_norm_rel()` 被替换
- [ ] 5个文件中的 `_load_json()` 被替换
- [ ] `roles.json` 两个版本内容一致

---

## Phase 2: 短期修复（3-5天）

### 任务 2.1: 重构 Python 包结构

**目标**: 消除 `sys.path` 动态修改

**当前问题**:
```python
# 不良实践
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tools.scc.runtime.diff_extract import extract_unified_diff  # noqa: E402
```

**解决方案**: 使用相对导入或安装为可编辑包

**执行步骤**:

1. **创建 `tools/scc/setup.py`**:
```python
from setuptools import setup, find_packages

setup(
    name="scc-tools",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "pyyaml",
        "requests",
    ],
)
```

2. **安装为可编辑包**:
```bash
cd tools/scc
pip install -e .
```

3. **修改导入语句**:

将:
```python
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from tools.scc.runtime.diff_extract import extract_unified_diff  # noqa: E402
```

改为:
```python
from scc.runtime.diff_extract import extract_unified_diff
```

4. **批量修改文件**:
- `tools/scc/runtime/run_child_task.py`
- `tools/scc/gates/run_ci_gates.py`
- 其他使用 `sys.path.insert` 的文件

---

### 任务 2.2: 合并 PowerShell 重复脚本

**目标**: 抽象 `worker-codex.ps1` 和 `worker-opencodecli.ps1` 的通用逻辑

**执行步骤**:

1. **创建共享库** `oc-scc-local/scripts/lib/WorkerUtils.ps1`:
```powershell
# Worker utilities for SCC

function Get-ExecRoot {
    param([string]$ScriptRoot)
    $ocRoot = Split-Path -Parent $ScriptRoot
    $repoRoot = Split-Path -Parent $ocRoot
    return $repoRoot
}

function Get-GatewayUrl {
    param([string]$DefaultUrl = "http://127.0.0.1:18788")
    if ($env:SCC_GATEWAY_URL) {
        return $env:SCC_GATEWAY_URL
    }
    return $DefaultUrl
}

function Set-ContextPackRequired {
    $env:CONTEXT_PACK_V1_REQUIRED = "true"
}

function Invoke-Worker {
    param(
        [string]$Executor,
        [string]$TaskId,
        [string]$BaseUrl
    )
    # Common worker logic
    # ...
}
```

2. **重构 worker-codex.ps1**:
```powershell
. $PSScriptRoot/lib/WorkerUtils.ps1

$ExecRoot = Get-ExecRoot -ScriptRoot $PSScriptRoot
$Base = Get-GatewayUrl
Set-ContextPackRequired

# Executor-specific logic only
& codex --task $TaskId --gateway $Base
```

3. **重构 worker-opencodecli.ps1**:
```powershell
. $PSScriptRoot/lib/WorkerUtils.ps1

$ExecRoot = Get-ExecRoot -ScriptRoot $PSScriptRoot
$Base = Get-GatewayUrl
Set-ContextPackRequired

# Executor-specific logic only
& opencodecli --task $TaskId --gateway $Base
```

---

### 任务 2.3: 统一命名规范

**目标**: 统一使用 `_` 或 `-` 作为分隔符

**决策**: 统一使用 `-`（更符合PowerShell/Node.js惯例）

**重命名清单**:

| 旧名称 | 新名称 |
|--------|--------|
| `map_build_v1.mjs` | `map-build-v1.mjs` |
| `pins_build_v1.mjs` | `pins-build-v1.mjs` |
| `selfcheck_map_v1.mjs` | `selfcheck-map-v1.mjs` |
| `pins_builder_v1.mjs` | `pins-builder-v1.mjs` |
| `context_pack_v1.mjs` | `context-pack-v1.mjs` |
| `preflight_v1.mjs` | `preflight-v1.mjs` |

**执行步骤**:
1. 批量重命名文件
2. 更新所有引用这些文件的代码
3. 更新 `package.json` 中的 scripts

---

### 任务 2.4: 统一 package.json

**目标**: 消除 `package.json` 的两个版本

**方案**: 让 scc-top 版本继承主版本

**执行步骤**:

1. **修改 `scc-top/tools/oc-scc-local/package.json`**:
```json
{
  "name": "oc-scc-local-top",
  "version": "0.1.0",
  "description": "SCC gateway wrapper for scc-top",
  "main": "src/gateway.mjs",
  "scripts": {
    "start": "node src/gateway.mjs",
    "gateway": "node src/gateway.mjs",
    "smoke": "node src/smoke.mjs"
  },
  "dependencies": {},
  "peerDependencies": {
    "oc-scc-local": "file:../../../oc-scc-local"
  }
}
```

2. **或者创建符号链接**:
```bash
cd scc-top/tools/oc-scc-local
rm package.json
mklink package.json ..\..\..\oc-scc-local\package.json
```

---

### Phase 2 完成标准

- [ ] 无 `sys.path` 动态修改
- [ ] `pip install -e tools/scc` 成功
- [ ] PowerShell 共享库创建
- [ ] 命名规范统一为 `-`
- [ ] `package.json` 版本一致

---

## Phase 3: 中期修复（1-2周）

### 任务 3.1: 清理嵌套代码库

**目标**: 消除 `scc-top/_docker_ctx_scc/` 中的代码副本

**当前结构**:
```
scc-top/_docker_ctx_scc/
├── tools/scc/              # Python工具副本
├── tools/oc-scc-local/     # Node.js代码副本
└── tools/unified_server/   # 服务器代码副本
```

**解决方案**: 使用 Docker 构建上下文而非维护副本

**执行步骤**:

1. **删除代码副本**:
```bash
rm -rf scc-top/_docker_ctx_scc/tools/scc
rm -rf scc-top/_docker_ctx_scc/tools/oc-scc-local
rm -rf scc-top/_docker_ctx_scc/tools/unified_server
```

2. **修改 Dockerfile**:
```dockerfile
# 从仓库根目录构建
COPY ../../../tools/scc /app/tools/scc
COPY ../../../oc-scc-local /app/oc-scc-local
```

3. **或者使用构建脚本**:
```powershell
# docker-build.ps1
$context = "scc-top/_docker_ctx_scc"

# 复制所需文件（不维护副本）
Copy-Item -Recurse tools/scc $context/tools/
Copy-Item -Recurse oc-scc-local $context/

# 构建 Docker
docker build $context

# 清理
Remove-Item -Recurse $context/tools/scc
Remove-Item -Recurse $context/oc-scc-local
```

---

### 任务 3.2: 创建统一 CLI 入口

**目标**: 为 Python 工具创建统一命令行接口

**设计**:
```bash
# 统一入口
scc gate run-all
scc gate schema
scc gate contracts
scc runtime orchestrate
scc ops pr-bundle
scc map query
```

**执行步骤**:

1. **创建 `tools/scc/cli.py`**:
```python
#!/usr/bin/env python3
"""SCC unified CLI."""
import click
from scc.gates import run_ci_gates
from scc.runtime import orchestrator_v1


@click.group()
def cli():
    """SCC Tools CLI"""
    pass


@cli.group()
def gate():
    """CI gate commands"""
    pass


@gate.command()
def run_all():
    """Run all CI gates"""
    run_ci_gates.main()


@gate.command()
def schema():
    """Run schema gate"""
    from scc.gates import schema_gate
    schema_gate.main()


@cli.group()
def runtime():
    """Runtime commands"""
    pass


@runtime.command()
@click.argument('task_id')
def orchestrate(task_id):
    """Orchestrate a task"""
    orchestrator_v1.run(task_id)


if __name__ == '__main__':
    cli()
```

2. **更新 setup.py**:
```python
setup(
    # ...
    entry_points={
        'console_scripts': [
            'scc=scc.cli:cli',
        ],
    },
)
```

3. **安装后使用**:
```bash
pip install -e tools/scc
scc --help
```

---

### 任务 3.3: 重构跨语言调用

**目标**: 减少 Python/Node.js 互相调用

**当前问题**:
- Python 调用 Node.js: `npm run map:build`
- Node.js 调用 Python: `python tools/scc/gates/run_ci_gates.py`

**解决方案**: 使用 HTTP API 或消息队列

**执行步骤**:

1. **定义清晰的接口边界**:
```
Python (tools/scc/)          Node.js (oc-scc-local/)
     |                              |
     |<----- HTTP API ----->|       |
     |                              |
   gates/                     gateway.mjs
   runtime/                   scripts/
   ops/
```

2. **Python 提供服务**:
```python
# tools/scc/api/server.py
from fastapi import FastAPI
from scc.gates import run_ci_gates

app = FastAPI()

@app.post("/gates/run-all")
def run_all_gates():
    return run_ci_gates.main()
```

3. **Node.js 调用 API**:
```javascript
// oc-scc-local/scripts/api-client.mjs
async function runGates() {
    const res = await fetch('http://localhost:18789/gates/run-all', {
        method: 'POST'
    });
    return res.json();
}
```

---

### Phase 3 完成标准

- [ ] `scc-top/_docker_ctx_scc/` 无代码副本
- [ ] `scc` CLI 可用
- [ ] 跨语言调用通过 API 而非直接执行

---

## 附录：自动化脚本

### A.1 批量替换 `_norm_rel()`

```python
#!/usr/bin/env python3
"""Replace _norm_rel with shared import."""
import re
from pathlib import Path

FILES = [
    "tools/scc/gates/schema_gate.py",
    "tools/scc/gates/contracts_gate.py",
    "tools/scc/gates/ssot_map_gate.py",
    "tools/scc/gates/context_pack_gate.py",
    "tools/scc/gates/context_pack_proof_gate.py",
    "tools/scc/runtime/unified_diff_guard.py",
    "tools/scc/ops/pr_bundle_create.py",
    "tools/scc/validators/hygiene_validator.py",
]

OLD_PATTERN = r'def _norm_rel\(p: str\) -> str:\s+return p\.replace\("\\\\\\\\", "/"\)\.lstrip\("\./"\)'

for file_path in FILES:
    path = Path(file_path)
    content = path.read_text()
    
    if '_norm_rel' in content:
        # Remove old function
        content = re.sub(OLD_PATTERN, '', content)
        # Add import at top
        if 'from tools.scc.lib.utils import' not in content:
            content = 'from tools.scc.lib.utils import norm_rel\n' + content
        # Replace _norm_rel with norm_rel
        content = content.replace('_norm_rel(', 'norm_rel(')
        
        path.write_text(content)
        print(f"Updated: {file_path}")
```

### A.2 检查配置一致性

```python
#!/usr/bin/env python3
"""Check configuration file consistency."""
import json
import sys
from pathlib import Path

CONFIG_PAIRS = [
    ("oc-scc-local/config/roles.json", "scc-top/tools/oc-scc-local/config/roles.json"),
    ("oc-scc-local/package.json", "scc-top/tools/oc-scc-local/package.json"),
]

def check_consistency():
    errors = []
    
    for main_path, sub_path in CONFIG_PAIRS:
        main = Path(main_path)
        sub = Path(sub_path)
        
        if not main.exists():
            errors.append(f"Missing: {main_path}")
            continue
        if not sub.exists():
            errors.append(f"Missing: {sub_path}")
            continue
            
        main_data = json.loads(main.read_text())
        sub_data = json.loads(sub.read_text())
        
        if main_data != sub_data:
            errors.append(f"Inconsistent: {main_path} vs {sub_path}")
    
    if errors:
        print("Configuration inconsistencies found:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)
    else:
        print("All configurations are consistent.")
        sys.exit(0)

if __name__ == "__main__":
    check_consistency()
```

---

## 总结

### 修复优先级

| 优先级 | 任务 | 预期收益 |
|--------|------|----------|
| P0 | 清理根目录脚本 | 根目录整洁度 3→8 |
| P0 | 创建共享工具库 | 代码复用 3→7 |
| P1 | 重构包结构 | 依赖管理 3→6 |
| P1 | 统一配置 | 配置管理 4→7 |
| P2 | 清理嵌套代码库 | 目录组织 4→7 |
| P2 | 创建统一CLI | 可用性提升 |

### 预期最终评分

| 维度 | 当前 | 目标 |
|------|------|------|
| 目录组织 | 4/10 | 7/10 |
| 代码复用 | 3/10 | 7/10 |
| 依赖管理 | 3/10 | 6/10 |
| 配置管理 | 4/10 | 7/10 |
| 命名规范 | 5/10 | 8/10 |
| 根目录整洁 | 3/10 | 8/10 |
| **综合** | **3.7/10** | **7.2/10** |

---

*计划结束*
