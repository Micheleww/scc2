# SCC2 工程改进指令

> 本文件是发给执行模型（GPT-5.3 Codex / Claude Opus）的**完整上下文包**。
> 系统设计目标：**通过总任务分解，协作多个强模型完成任务；整个过程自协作、自迭代、自稳定。**

---

## 一、系统现状概要

SCC2 是一个 AI 驱动的代码工厂（Code Factory），核心组件：

| 组件 | 路径 | 语言 | 行数 | 状态 |
|------|------|------|------|------|
| Gateway（网关 + 调度器 + 一切） | `oc-scc-local/src/gateway.mjs` | Node.js ESM | **13,603** | God-file，需拆分 |
| Prompt Registry | `oc-scc-local/src/prompt_registry.mjs` | Node.js ESM | 331 | 良好 |
| Role System | `oc-scc-local/src/role_system.mjs` | Node.js ESM | 221 | 良好 |
| Verdict Judge | `oc-scc-local/src/verifier_judge_v1.mjs` | Node.js ESM | 89 | 缺测试 |
| Preflight Gate | `oc-scc-local/src/preflight_v1.mjs` | Node.js ESM | 274 | 缺测试 |
| Factory Policy | `oc-scc-local/src/factory_policy_v1.mjs` | Node.js ESM | 63 | 缺测试 |
| Map Builder | `oc-scc-local/src/map_v1.mjs` | Node.js ESM | 886 | 良好 |
| Pins Builder | `oc-scc-local/src/pins_builder_v1.mjs` | Node.js ESM | ~600 | 缺测试 |
| Python Runtime | `tools/scc/runtime/` | Python | ~2000 | 0% 测试，有注入风险 |
| Python Gates | `tools/scc/gates/` | Python | ~800 | 0% 测试 |
| UI | `oc-scc-local/ui/sccdev/` | HTML+JS | 320 | 只有表格，功能很基础 |
| 契约 Schemas | `contracts/` | JSON Schema | 50+ 文件 | 过于宽松 |
| Selfcheck 脚本 | `oc-scc-local/scripts/selfcheck_*.mjs` | Node.js ESM | 23 个 | 只有 smoke 级别 |

---

## 二、工程改进目标与方法

### 目标 G1：拆分 God-File `gateway.mjs`

**为什么**：13,603 行单文件包含 15+ 种职责，无法测试、无法审查、一个 bug 全系统崩溃。

**目标结构**：

```
oc-scc-local/src/
├── gateway.mjs           ← 只保留 HTTP server 启动 + 路由分发，目标 < 500 行
├── router.mjs            ← 路由表：pathname → handler 映射
├── scheduler.mjs         ← 任务调度：queue, priority, dispatch, schedule()
├── board.mjs             ← 任务板 CRUD：createBoardTask, getBoardTask, putBoardTask, listBoardTasks, saveBoard, loadBoard
├── jobs.mjs              ← Job 生命周期：newJobId, jobs Map, runJob, finishJob, saveState, loadState
├── workers.mjs           ← Worker 注册/心跳/租约/外部调度
├── executor.mjs          ← execCodex, occliRunSingle, codexRunSingle, codexHealth
├── circuit_breaker.mjs   ← 熔断器状态、quarantine 逻辑、repoHealth
├── degradation.mjs       ← 降级矩阵计算、WIP 限制调整（复用 factory_policy_v1.mjs）
├── instinct.mjs          ← 故障聚类：simhash, taxonomy, buildInstinctSnapshot, pattern clustering
├── playbook_engine.mjs   ← Playbook 匹配/应用/rollback
├── flow_manager.mjs      ← 流控：bottleneck 检测、factory_manager task 创建
├── hooks.mjs             ← 所有自动触发钩子：audit_trigger, feedback_hook, learned_patterns_hook, token_cfo_hook, five_whys_hook, instinct_hook, radius_audit_hook
├── ledger.mjs            ← Parent ledger: task_ledger, progress_ledger, stall detection
├── ci_gate.mjs           ← CI gate 执行、anti-forgery、fixup task 创建
├── ssot_sync.mjs         ← SSOT 同步/自动 apply/PR bundle
├── designer.mjs          ← Designer state, split logic, two-phase pins
├── config.mjs            ← configRegistry, parseEnvText, readRuntimeEnv, writeRuntimeEnv, loadFeatures
├── utils.mjs             ← sendJson, sendText, readRequestBody, readJsonBody, readJsonlTail, appendJsonl, sha256Hex, sha1, stableStringify, toYaml
├── prompt_registry.mjs   ← （已独立，保持不变）
├── role_system.mjs       ← （已独立，保持不变）
├── factory_policy_v1.mjs ← （已独立，保持不变）
├── verifier_judge_v1.mjs ← （已独立，保持不变）
├── preflight_v1.mjs      ← （已独立，保持不变）
├── map_v1.mjs            ← （已独立，保持不变）
└── pins_builder_v1.mjs   ← （已独立，保持不变）
```

**方法**：
1. 先创建 `utils.mjs`，把所有纯工具函数搬出去（`sendJson`、`readJsonlTail`、`appendJsonl`、`sha256Hex`、`sha1`、`stableStringify`、`toYaml`、`readRequestBody`、`readJsonBody` 等）
2. 然后按职责逐个提取模块，每提取一个模块就跑一次 `npm run smoke` 确认不破坏
3. `gateway.mjs` 最终只保留：`import` 所有模块 → 创建 HTTP server → `createServer((req, res) => router.handle(req, res))` → `server.listen()`
4. 每个模块用 `export` 暴露 API，内部状态用闭包或 class 封装

**约束**：
- 不改变任何 HTTP API 的请求/响应格式
- 不改变任何 env var 的名称或默认值
- 不引入新的 npm 依赖
- 保持 ESM（`import`/`export`），不转 CommonJS

---

### 目标 G2：修复已知结构性 Bug

#### Bug 1：`validateSubmitSchema` 和 `validateVerdictSchema` 嵌套定义

**位置**：`gateway.mjs:2222-2274`

**问题**：`validateSubmitSchema` 函数缺少一个 `}` 闭合，导致 `validateVerdictSchema` 被定义在它内部。目前能运行是因为 JavaScript hoisting，但语义完全错误——`validateVerdictSchema` 只在 `validateSubmitSchema` 被首次调用后才可用。

**修复方法**：
```js
// 修复前（伪代码）：
function validateSubmitSchema(submit) {
  // ... 逻辑 ...
  if (!submitSchemaValidate) {
    try {
      // ... 编译 schema ...
    } catch (e) {
      // ... 处理错误 ...
    }                          // ← 这里缺少闭合 }

  // validateVerdictSchema 错误地嵌套在 validateSubmitSchema 内部
  function validateVerdictSchema(verdict) { ... }
  }  // ← 这个 } 闭合的是 validateSubmitSchema

  // 最终的 return 逻辑
}

// 修复后：
function validateSubmitSchema(submit) {
  // ... 逻辑 ...
  if (!submitSchemaValidate) {
    try { ... } catch (e) { ... }
  }  // ← 正确闭合 if
  const ok = Boolean(submitSchemaValidate(submit))
  if (ok) return { ok: true }
  return { ok: false, reason: "invalid_submit_schema", errors: ... }
}  // ← 正确闭合 function

function validateVerdictSchema(verdict) {
  // ... 独立函数 ...
}
```

#### Bug 2：`toYaml()` 输出 literal `\n` 而不是换行符

**位置**：`gateway.mjs:1354-1387`

**问题**：`toYaml` 函数在多处使用了 `"\\n"`（转义后的字面反斜杠 n），应该是 `"\n"`（换行符）。

**受影响行**：1364, 1369, 1379, 1384

**修复**：将所有 `"\\n"` 替换为 `"\n"`（仅在 toYaml 函数内部的 `.join("\\n")` 和字符串拼接中）。

#### Bug 3：`gateway.mjs:1812` instinct schemas YAML 写入 `\\n`

**位置**：`gateway.mjs:1812`
```js
fs.writeFileSync(instinctSchemasFile, renderInstinctSchemasYaml() + "\\n", "utf8")
```
应改为 `+ "\n"`

---

### 目标 G3：消除硬编码 Windows 路径

**问题**：至少 15 处硬编码 `"C:/scc"` 或 `"C:/scc/OpenCode/..."` 作为 fallback。

**方法**：
1. 在 `config.mjs` 中统一定义 `SCC_REPO_ROOT`：
```js
// config.mjs
import path from "node:path"
import { fileURLToPath } from "node:url"

const __dirname = path.dirname(fileURLToPath(import.meta.url))
// 从 oc-scc-local/src/ 往上两级就是仓库根目录
export const SCC_REPO_ROOT = process.env.SCC_REPO_ROOT ?? path.resolve(__dirname, "..", "..")
```
2. 所有使用 `"C:/scc"` 的地方改为引用 `SCC_REPO_ROOT`
3. `occliBin` 改为 `process.env.OPENCODE_BIN ?? "opencode-cli"`（依赖 PATH 查找，不硬编码绝对路径）
4. Python 端同理：
```python
SCC_REPO_ROOT = os.environ.get("SCC_REPO_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

**需要修改的文件清单**：
- `gateway.mjs`：`SCC_REPO_ROOT`, `occliBin`, `execRoot`, `docsRoot`, `promptRegistryRoot`, `runtimeEnvFile`, `sccDevUiDir` 等
- `tools/scc/runtime/run_child_task.py`
- `scc-top/tools/unified_server/services/executor_service.py`：删除 `r"C:\Users\Nwe-1\AppData\..."` 硬编码
- 所有 selfcheck 脚本中的 `"C:/scc"` 默认值

---

### 目标 G4：修复 Python 命令注入

**问题**：多处使用 `shell=True` 或未校验的用户输入直接传入 subprocess。

**修复清单**：

| 文件 | 行 | 修复方法 |
|------|-----|---------|
| `scc-top/tools/scc/ops/run_contract_task.py:66` | `subprocess.run(cmd, shell=True)` | 改为 `subprocess.run(shlex.split(cmd))` 或传入列表 |
| `scc-top/tools/scc/ops/contract_runner.py:45` | `subprocess.run(cmd, shell=True)` | 同上 |
| `tools/scc/runtime/run_child_task.py:407-421` | `_run_shell()` 接受 `--executor-cmd` 不校验 | 添加白名单校验：只允许已知的 executor 二进制路径 |

**校验方法**：
```python
import shlex
import re

ALLOWED_EXECUTORS = {"codex", "opencode-cli", "python", "node", "npm"}

def validate_executor_cmd(cmd: str) -> bool:
    tokens = shlex.split(cmd)
    if not tokens:
        return False
    binary = os.path.basename(tokens[0]).lower()
    # 去掉 .exe/.cmd 后缀
    binary = re.sub(r'\.(exe|cmd|bat)$', '', binary)
    return binary in ALLOWED_EXECUTORS
```

---

### 目标 G5：补充单元测试（测试金字塔）

**现状**：0 个 Node.js 单元测试，0 个 Python runtime 测试。selfcheck 只是 smoke 级别。

**目标**：
- Node.js 核心模块：每个模块 15-30 个测试用例
- Python runtime：每个关键路径 10-20 个测试用例
- 总覆盖率目标：关键路径 80%+

**使用 Node.js 内置 test runner**（不引入新依赖）：

```js
// tests/test_verdict.mjs
import { describe, it } from "node:test"
import assert from "node:assert/strict"
import { computeVerdictV1 } from "../src/verifier_judge_v1.mjs"

describe("computeVerdictV1", () => {
  it("returns DONE when submit=DONE + exit_code=0 + CI pass", () => {
    const v = computeVerdictV1({
      taskId: "t1",
      submit: { status: "DONE", exit_code: 0, tests: { passed: true } },
      job: { status: "done" },
      ciGate: { required: true, ran: true, ok: true },
    })
    assert.equal(v.verdict, "DONE")
  })
  it("returns RETRY when CI gate fails", () => { ... })
  it("returns ESCALATE on NEED_INPUT", () => { ... })
  it("returns ESCALATE on patch_scope_violation", () => { ... })
  it("handles missing task_id", () => { ... })
  it("handles null submit gracefully", () => { ... })
  // ... 至少 20 个用例
})
```

**需要测试的模块与用例方向**：

| 模块 | 测试文件 | 重点用例 |
|------|---------|---------|
| `verifier_judge_v1.mjs` | `tests/test_verdict.mjs` | DONE/RETRY/ESCALATE 所有路径、gates 组合、null 输入、边界条件 |
| `preflight_v1.mjs` | `tests/test_preflight.mjs` | 路径遍历攻击、glob 匹配、shellSplit 边界、缺失文件、写作用域 |
| `factory_policy_v1.mjs` | `tests/test_factory_policy.mjs` | 降级矩阵匹配、WIP 限制调整、stop_the_bleeding 过滤 |
| `prompt_registry.mjs` | `tests/test_prompt_registry.mjs` | 模板替换、路径逃逸防护、缺失 block、JSON/text 渲染 |
| `role_system.mjs` | `tests/test_role_system.mjs` | 角色加载、技能矩阵校验、schema 校验失败 |
| `map_v1.mjs` | `tests/test_map.mjs` | queryMapV1 搜索、symbol 提取、env key 提取 |
| `utils.mjs`（拆分后） | `tests/test_utils.mjs` | readJsonlTail、toYaml、stableStringify、sha256Hex |
| `scheduler.mjs`（拆分后） | `tests/test_scheduler.mjs` | 优先级排序、dispatch idempotency、lane 路由 |
| `circuit_breaker.mjs`（拆分后） | `tests/test_circuit_breaker.mjs` | trip/cooldown/reset 状态机 |

**在 `package.json` 中添加**：
```json
{
  "scripts": {
    "test": "node --test tests/test_*.mjs",
    "test:coverage": "node --test --experimental-test-coverage tests/test_*.mjs"
  }
}
```

---

### 目标 G6：收紧 JSON Schema 契约

**问题**：当前 schema 过于宽松，无法真正起到校验作用。

**修复清单**：

| Schema 文件 | 修改 |
|------------|------|
| `contracts/envelope/envelope.schema.json` | `payload` 改为 `oneOf` 引用各协议的子 schema |
| `contracts/event/event.schema.json` | `additionalProperties` 改为 `false` |
| `contracts/verdict/verdict.schema.json` | `actions` items 添加 `required: ["type"]`，`additionalProperties: false` |
| `contracts/child_task/child_task.schema.json` | `files` 加 `maxItems: 64`，`allowedTests` 加 `maxItems: 16` |
| `contracts/submit/submit.schema.json` | 所有 string 字段加 `maxLength: 4096` |
| 所有 schema | 添加 `description` 字段说明语义 |

---

### 目标 G7：修复 silent error swallowing

**问题**：`gateway.mjs` 中 50+ 处 `catch { // best-effort }` 或 `catch { // ignore }`。

**方法**：
1. 创建一个 `logger.mjs` 模块：
```js
// logger.mjs
import fs from "node:fs"

const LOG_LEVELS = { error: 0, warn: 1, info: 2, debug: 3 }
const currentLevel = LOG_LEVELS[String(process.env.LOG_LEVEL ?? "info").toLowerCase()] ?? 2

export function logError(context, error, meta = {}) {
  if (currentLevel < LOG_LEVELS.error) return
  const entry = {
    t: new Date().toISOString(),
    level: "error",
    context,
    message: String(error?.message ?? error ?? ""),
    ...meta,
  }
  console.error(JSON.stringify(entry))
}

export function logWarn(context, message, meta = {}) { ... }
export function logInfo(context, message, meta = {}) { ... }
```

2. 将所有 `catch { // best-effort }` 改为 `catch (e) { logError("save_state", e) }`
3. 关键路径的状态持久化（`saveBoard`、`saveState`、`saveCircuitBreakerState`）失败时应记录错误并设置内存中的 dirty flag，下次定时重试

---

### 目标 G8：添加可观测性

**方法**：在 gateway 上新增以下 API 端点（供 Electron UI 和外部监控使用）：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/metrics` | GET | Prometheus 格式的 metrics（jobs_total, jobs_active, jobs_failed, queue_depth, circuit_breaker_state 等） |
| `/health` | GET | 已有，但增加详细健康检查（数据库可写、executor 二进制可用、role system loaded） |
| `/debug/state` | GET | 完整内部状态快照（仅限 localhost） |
| `/debug/errors` | GET | 最近 100 条 logError 记录 |

---

### 目标 G9：跨平台兼容

**修复清单**：
- 所有 selfcheck 脚本：将 `cmd.exe /C` 替换为 `process.platform === "win32" ? ["cmd.exe", "/C", ...] : ["sh", "-c", ...]`
- 路径分隔符：统一使用 `path.posix.join` 或 `path.join`，不硬编码 `\\` 或 `/`
- `daemon-start.vbs` / `daemon-stop.vbs`：添加对应的 `daemon-start.sh` / `daemon-stop.sh`
- Python 端：所有 `subprocess.run` 的 `cwd` 参数使用 `os.path.join` 而非字符串拼接

---

### 目标 G10：添加 CI Pipeline

**在 `.github/workflows/ci.yml` 中添加**：

```yaml
name: CI
on: [push, pull_request]
jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 20
      - run: npm --prefix oc-scc-local install
      - run: npm --prefix oc-scc-local test
      - run: npm --prefix oc-scc-local run selfcheck:role-system
      - run: npm --prefix oc-scc-local run selfcheck:verdict-v1
      - run: npm --prefix oc-scc-local run selfcheck:factory-policy-v1
      - run: npm --prefix oc-scc-local run selfcheck:preflight-commands-v1
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install pytest
      - run: pytest tools/scc/tests/ -q
```

---

## 三、前端 UI 改进（Electron 应用）

### 3.1 当前 Web UI 现状

现有 `oc-scc-local/ui/sccdev/` 只有一个简单的监控页面，包含：
- 4 个 KV 卡片（Factory / WIP / Queue / Routing）
- 3 个表格 Tab（Tasks / Workers / Events）
- 2.5 秒轮询 `/sccdev/api/v1/snapshot`

### 3.2 已有 API 端点（可直接用于 Electron UI）

Gateway 已经暴露了丰富的 REST API，以下是可用于 UI 的关键端点：

| 端点 | 方法 | 数据 | 适合的 UI 组件 |
|------|------|------|---------------|
| `/sccdev/api/v1/snapshot` | GET | 完整快照（tasks, jobs, workers, factory, events） | 仪表盘主视图 |
| `/status` | GET | 系统状态摘要 | 顶栏状态指示器 |
| `/health` | GET | 健康检查 | 连接状态灯 |
| `/board/tasks` | GET | 任务板列表 | 任务看板 |
| `/board/tasks/:id` | GET | 单个任务详情 | 任务详情面板 |
| `/board/tasks` | POST | 创建任务 | 任务创建表单 |
| `/board/tasks/:id` | PATCH | 更新任务状态 | 状态切换按钮 |
| `/executor/jobs` | GET | 所有 jobs | 执行器监控视图 |
| `/executor/debug/summary` | GET | 执行器统计 | 执行器统计图表 |
| `/executor/debug/failures` | GET | 失败列表 | 失败分析面板 |
| `/map/v1` | GET | Map 概要 | 代码地图导航器 |
| `/map/v1/query?q=...` | GET | Map 搜索 | 搜索栏 |
| `/map/v1/version` | GET | Map 版本 | 版本信息 |
| `/map/v1/build` | POST | 触发 Map 重建 | 操作按钮 |
| `/pins/v1/build` | POST | 构建 Pins | Pins 构建面板 |
| `/preflight/v1/check` | POST | Preflight 检查 | 预检面板 |
| `/prompts/registry` | GET | Prompt 注册表 | Prompt 管理界面 |
| `/prompts/render` | POST | 渲染 Prompt | Prompt 预览 |
| `/roles` | GET | 角色列表 | 角色管理界面 |
| `/factory/policy` | GET | 工厂策略 | 策略配置面板 |
| `/factory/degradation` | GET | 降级状态 | 降级告警显示 |
| `/config/runtime` | GET/POST | 运行时配置 | 配置管理面板 |
| `/replay/task?task_id=...` | GET | 任务回放 | 任务回放视图 |
| `/instinct/snapshot` | GET | 故障模式快照 | 故障分析仪表盘 |
| `/instinct/patterns` | GET | 故障 patterns | 故障模式列表 |
| `/metrics/router_stats` | GET | 模型路由统计 | 模型性能对比图 |

### 3.3 Electron UI 应实现的功能模块

#### 模块 A：仪表盘（Dashboard）— 最高优先

**数据源**：`/sccdev/api/v1/snapshot`

展示内容：
1. **系统健康指示器**（顶栏）
   - 连接状态灯（绿/黄/红）
   - 当前降级级别（normal / queue_overload / stop_the_bleeding）
   - 熔断器状态（active breakers 数量）
   - Quarantine 是否激活

2. **WIP 仪表盘**（gauge 图表）
   - 当前 WIP / WIP 上限（分 internal/external 显示）
   - 各 lane 的 running 数量（fastlane / mainlane / batchlane）
   - 有效 WIP 限制（经降级调整后的值）

3. **任务流水线**（Kanban 看板）
   - 列：backlog → needs_split → ready → in_progress → done / failed
   - 每张卡片显示：task_id（短）、title、role 徽章、lane 颜色标记、elapsed time
   - 支持拖拽改变状态
   - 点击展开详情（goal, pins, verdict, CI gate result, events）

4. **实时事件流**（event stream）
   - 最近 N 条 state_events
   - 按 event_type 颜色编码（SUCCESS=绿, CI_FAILED=红, PREFLIGHT_FAILED=黄, EXECUTOR_ERROR=橙）
   - 支持筛选（by event_type, by task_id, by executor）

#### 模块 B：执行器监控（Executor Monitor）

**数据源**：`/executor/jobs`, `/executor/debug/summary`, `/executor/debug/failures`

展示内容：
1. **Worker 列表**
   - 每个 worker：ID, 支持的 executors, 当前 running job, last seen, lease 剩余
   - 状态灯（active / idle / stale）

2. **Job 时间线**
   - 水平时间线图，每个 job 是一个 bar
   - 颜色编码状态（queued=灰, running=蓝, done=绿, failed=红, timeout=紫）
   - hover 显示：model, executor, duration, exit_code, task_id

3. **模型路由统计**（`/metrics/router_stats`）
   - 按模型分组的成功率柱状图
   - 按 task_class 分组的成功率热力图

4. **失败分析面板**
   - Top failure reasons（饼图）
   - Top error signatures（表格）
   - Failure rate 趋势线

#### 模块 C：任务详情（Task Detail）

**数据源**：`/board/tasks/:id`, `/replay/task?task_id=...`

展示内容：
1. **任务元信息**：id, title, goal, role, lane, status, task_class_id
2. **Pins 视图**：allowed_paths（树状展示）, forbidden_paths, symbols, max_files
3. **Verdict 历史**：每次 verdict 判决结果 + reasons
4. **CI Gate 结果**：command, exit_code, stdout/stderr preview
5. **Events 时间线**：该任务的所有 state_events
6. **Parent-Child 关系图**：如果是 parent task，显示 children 及其状态
7. **Progress Ledger**：attempts used/total, tokens used/budget, stall detection

#### 模块 D：故障洞察（Instinct Insight）

**数据源**：`/instinct/snapshot`, `/instinct/patterns`

展示内容：
1. **Taxonomy 分布**（树状图/旭日图）
   - infra.fs / infra.shell / executor.contract / model.auth / ci.gate / pins.quality / unknown
2. **Top Failure Patterns**（表格）
   - cluster_key, count, avg_duration, usage_avgs, first/last_seen
   - 点击展开 sample_task_ids（可跳转到任务详情）
3. **Playbook 状态**
   - 已激活的 playbooks 列表
   - 每个 playbook 的匹配次数、最近触发时间

#### 模块 E：配置管理（Config Manager）

**数据源**：`/config/runtime`（GET/POST）, `/factory/policy`

展示内容：
1. **运行时配置编辑器**
   - 所有 configRegistry 中的 key，分组显示（frequent / infrequent）
   - 每个 key 显示：当前值、类型、说明
   - 支持在线修改并保存（POST `/config/runtime`）
2. **Factory Policy 查看器**
   - WIP limits 可视化
   - Degradation matrix 条件 → 动作表格
   - Circuit breakers 规则列表
   - Event routing 规则表格

#### 模块 F：代码地图导航器（Map Navigator）

**数据源**：`/map/v1`, `/map/v1/query`, `/map/v1/version`

展示内容：
1. **模块树**（左侧导航）
   - 按 module root 分层显示
   - 每个模块标注 kind (node/python/go/...)
2. **搜索栏**
   - 输入关键词，实时调用 `/map/v1/query?q=...`
   - 结果按 score 排序，标注 kind（module/entry_point/key_symbol/config）
3. **Symbol 查看器**
   - 选中文件后显示 key_symbols 列表（function/class/const + line number）
4. **Link Report**
   - 缺少 doc_refs 的模块/entry_points 高亮警告

### 3.4 需要修复的 UI 安全问题

| # | 问题 | 修复方法 |
|---|------|---------|
| 1 | `app.js:30-33` 使用 `innerHTML` 注入服务端数据 | 在 Electron 中使用 `textContent` 或 React/Vue 的模板系统（自动转义） |
| 2 | `app.js:2` `esc()` 缺少 `"` 和 `'` 转义 | 添加 `.replaceAll('"', '&quot;').replaceAll("'", '&#39;')` |
| 3 | 2.5 秒轮询无节流 | 改为 WebSocket 或 SSE；如果保持轮询，失败时指数退避（2s → 4s → 8s → 16s） |
| 4 | 无认证 | Electron 本地应用可通过 IPC 直接调用；如需远程访问，添加 token 认证 |

### 3.5 Electron 架构建议

```
electron-app/
├── main.js            ← Electron main process
├── preload.js         ← contextBridge 暴露安全的 API
├── renderer/
│   ├── index.html
│   ├── dashboard.tsx  ← 仪表盘
│   ├── tasks.tsx      ← 任务看板
│   ├── executor.tsx   ← 执行器监控
│   ├── instinct.tsx   ← 故障洞察
│   ├── config.tsx     ← 配置管理
│   ├── map.tsx        ← 代码地图
│   └── components/
│       ├── KanbanBoard.tsx
│       ├── GaugeChart.tsx
│       ├── EventStream.tsx
│       ├── TimelineChart.tsx
│       └── StatusLight.tsx
├── gateway-client.ts  ← 封装所有 gateway API 调用
└── package.json
```

**技术选型建议**：
- 渲染框架：React + TypeScript（Electron 生态最成熟）
- 图表库：Recharts 或 @nivo（轻量，声明式）
- 状态管理：Zustand（比 Redux 简单，适合桌面应用）
- 样式：Tailwind CSS 或 CSS Modules
- 数据获取：使用 `contextBridge` 在 preload 中暴露 `window.api.fetchSnapshot()` 等方法，渲染进程不直接 fetch

---

## 四、自协作/自迭代/自稳定 系统改进

### 4.1 当前架构的自稳定机制（已有，需加强）

| 机制 | 当前实现 | 改进方向 |
|------|---------|---------|
| 降级矩阵 | `degradation_matrix` 只支持 boolean 信号 | 支持数值阈值（如 `queue_depth > 20`） |
| 熔断器 | `circuit_breakers` 基于连续失败次数 | 增加时间窗口（如"5 分钟内 N 次"） |
| Verdict 判决 | DONE/RETRY/ESCALATE 三值 | 增加 `SKIP`（task 已过时不需执行）和 `SPLIT`（需要分解） |
| Preflight 门控 | 检查文件/路径/命令/scope | 增加 token 预算预检（pins token 估算 > budget → fail） |
| Fixup 回路 | CI fixup 最多 N 次 | 增加全局 fixup storm 检测（一分钟内 > 10 个 fixup → 暂停并 escalate） |
| Learned Patterns | 聚类失败模式 | 与 playbook 自动关联：新 pattern → 自动生成 draft playbook |

### 4.2 需要新增的自稳定机制

#### 机制 S1：全局预算守护

```json
// factory_policy.json 新增
{
  "global_budgets": {
    "max_concurrent_tasks": 20,
    "max_daily_token_budget": 5000000,
    "max_daily_api_calls": 10000,
    "max_fixup_storms_per_hour": 5,
    "budget_enforcement": "hard"
  }
}
```

当日预算超限时自动进入 `stop_the_bleeding` 模式，只允许 CI fixup 和 infra repair。

#### 机制 S2：任务依赖图（Task DAG）

当前任务只有 parent-child 关系，缺少兄弟依赖。改进：

```json
{
  "task_id": "t3",
  "depends_on": ["t1", "t2"],
  "blocks": ["t4"]
}
```

调度器在 dispatch 时检查所有 `depends_on` 是否 DONE，否则保持 `blocked`。

#### 机制 S3：自动回滚检测

每个 DONE 的任务，在下一个 CI cycle 中检查其改动是否导致其他任务失败。如果是：
1. 自动创建 `revert_task` 回滚该任务的 patch
2. 将原任务标记为 `regressed`
3. 通知 factory_manager

#### 机制 S4：模型能力路由（Model Capability Routing）

不是所有任务都需要最强模型。根据 task_class 自动选择合适的模型：

```json
{
  "model_routing_rules": [
    { "task_class": "ci_fixup_v1", "preferred_models": ["gpt-4.1-mini", "kimi-k2.5-free"], "reason": "CI fixup is routine, use cheaper model" },
    { "task_class": "architecture_review", "preferred_models": ["gpt-5.3-codex", "claude-opus-4-6"], "reason": "Architecture needs strong reasoning" },
    { "task_class": "doc_update", "preferred_models": ["kimi-k2.5-free"], "reason": "Documentation is low-risk" }
  ]
}
```

---

## 五、执行顺序建议

按照影响和依赖关系，建议执行顺序：

1. **G2**（修复结构性 Bug）— 立即执行，不需要重构
2. **G3**（消除硬编码路径）— 立即执行，改善可移植性
3. **G4**（修复命令注入）— 立即执行，安全问题
4. **G7**（替换 silent catch）— 与 G1 同步执行
5. **G1**（拆分 gateway.mjs）— 核心重构，需要 2-3 轮迭代
6. **G5**（补充单元测试）— 在 G1 拆分过程中同步补充
7. **G6**（收紧 schemas）— 在 G5 完成后执行，确保有测试保护
8. **G10**（CI Pipeline）— 在 G5 完成后立即添加
9. **G8**（可观测性）— 在 G1 完成后添加
10. **G9**（跨平台）— 在 G1 完成后逐步推进
11. **UI 改进** — 与后端改进并行推进

---

## 六、验收标准

每个改进完成后，必须满足：

1. `npm --prefix oc-scc-local run smoke` 通过
2. `npm --prefix oc-scc-local test` 通过（G5 完成后）
3. 所有现有 selfcheck 脚本通过
4. 不引入新的 npm/pip 依赖（除非有充分理由）
5. 不改变任何 HTTP API 的 request/response schema
6. 不改变任何 env var 的名称
7. commit message 包含改进目标编号（如 `[G1] Extract scheduler.mjs from gateway`）
