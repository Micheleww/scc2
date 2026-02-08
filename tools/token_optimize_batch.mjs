#!/usr/bin/env node
/**
 * Token Optimization — Batch Task Submission Script
 *
 * 向 SCC Gateway 提交 1 个 parent task + 6 个 atomic child tasks，
 * 针对 gateway.mjs 和 map_v1.mjs 的 token 优化改造。
 *
 * ⚠️ 角色约束：现有 engineer 角色 deny_paths 包含 oc-scc-local/**，
 *    需要创建自定义 gateway_engineer 角色或用管理员权限执行。
 *
 * Usage:
 *   node tools/token_optimize_batch.mjs                  # submit to gateway
 *   node tools/token_optimize_batch.mjs --dry-run         # print tasks JSON only
 *   SCC_BASE_URL=http://host:port node tools/token_optimize_batch.mjs
 */

const BASE_URL = process.env.SCC_BASE_URL || "http://127.0.0.1:18788";

async function post(path, body) {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = await res.json();
  if (!res.ok) throw new Error(`POST ${path} => ${res.status}: ${JSON.stringify(json)}`);
  return json;
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ─── Parent Task ─────────────────────────────────────────────────────

const PARENT_TASK = {
  kind: "parent",
  title: "Token Optimization — Gateway & Map Engine",
  goal: `# Token 优化工程

## 目标
对 SCC Gateway (gateway.mjs) 和 Map Engine (map_v1.mjs) 进行 token 用量优化，
预期总体节省 30-60% 的 input token 消耗。

## 6 个优化任务
- TOK-01: Prompt 缓存友好前缀重构 (HIGH, 30-50%)
- TOK-02: Context 按任务类型分级限额 (HIGH, 40-70%)
- TOK-03: Token CFO 自动修正闭环 (MEDIUM)
- TOK-04: JSON 注入紧凑化 (LOW-MED, 10-15%)
- TOK-05: Map 摘要分级 L0/L1/L2 (MEDIUM, 20-40%)
- TOK-06: 静态 Block 注入去重 (LOW)

## ⚠️ 角色约束
所有任务修改 oc-scc-local/** 目录，现有 engineer 角色 deny_paths 禁止写入。
需要：
1. 创建 gateway_engineer 角色（allow oc-scc-local/**），或
2. 由 Claude/GPT-5.3 等特权 agent 直接执行

## 验收标准
- Token CFO snapshot 中 cache_ratio 从 0% 提升至 > 20%
- doc 类型任务的平均 context_bytes 从 220KB 降至 < 50KB
- Token CFO unused_ratio 从 60%+ 降至 < 40%`,
  role: "gateway_engineer",
  lane: "mainlane",
  status: "ready",
  files: ["oc-scc-local/src/gateway.mjs", "oc-scc-local/src/map_v1.mjs"],
  allowedExecutors: ["opencodecli", "codex"],
  allowedModels: ["claude-sonnet", "gpt-4o", "glm-4.7", "kimi-k2.5"],
};

// ─── Child Tasks ─────────────────────────────────────────────────────

function childTasks(parentId) {
  return [

    // ═══════════════════════════════════════════════════════════════
    // TOK-01: Prompt Cache-Friendly Prefix Restructuring (HIGH)
    // ═══════════════════════════════════════════════════════════════
    {
      title: "TOK-01: Prompt Cache-Friendly Prefix Restructuring",
      goal: `# 任务：重构 Prompt 组装顺序，启用 Claude Prompt Caching

## 影响：HIGH — 预计节省 30-50% input tokens

## 背景
Claude API 会自动缓存 system prompt 中的固定前缀。当前 SCC 的 prompt 组装
把变化内容（context_pack）放在前面，静态内容（CI handbook）放在后面，
导致每次调用都无法命中缓存。

当前组装顺序 (gateway.mjs:10721-10738)：
\`\`\`
[变化] context_pack (pinned files, 每任务不同)
[变化] thread history (每任务不同)
[静态] CI handbook (每次都一样)
[变化] task goal (每任务不同)
\`\`\`

## 修改目标

将组装顺序改为"静态前缀 + 动态后缀"：
\`\`\`
[静态] legal_prefix (从 docs/prompt_os/compiler/legal_prefix_v1.txt 读取，如不存在则用内置版)
[静态] CI handbook (getCiHandbookText())
[静态] role capsule (从 docs/prompt_os/roles/{role}.md 读取，如不存在则跳过)
[静态] tool digest (从 docs/prompt_os/compiler/tool_digest_v1.txt 读取，如不存在则跳过)
--- 以上为可缓存前缀 ---
[变化] <context_pack> (pinned files)
[变化] <thread> (history)
[变化] task goal
\`\`\`

## 具体修改

### 1. 修改 gateway.mjs 的 prompt 组装函数

定位到 ~line 10721-10738，当前代码大致是：
\`\`\`javascript
const prefixParts = []
if (current.contextPackId) {
  const ctxText = getContextPack(current.contextPackId)
  if (ctxText) prefixParts.push(\`<context_pack id="\${current.contextPackId}">\\n\${ctxText}\\n</context_pack>\\n\`)
}
if (current.threadId) { /* ... thread injection ... */ }
const injected = prefixParts.length ? prefixParts.join("\\n") + "\\n" + current.prompt : current.prompt
// CI handbook appended at the end
const ciHandbookText = getCiHandbookText()
return ciHandbookText ? \`\${base}\\n\\n\${ciHandbookText}\` : base
\`\`\`

改为：
\`\`\`javascript
// === Static prefix (cacheable) ===
const staticParts = []

// 1. Legal prefix
const legalPath = path.join(docsRoot, "prompt_os/compiler/legal_prefix_v1.txt")
try { const lp = fs.readFileSync(legalPath, "utf8").trim(); if (lp) staticParts.push(lp) } catch {}

// 2. CI handbook
const ciHandbookText = getCiHandbookText()
if (ciHandbookText) staticParts.push(ciHandbookText)

// 3. Role capsule (if exists)
const roleCapsulePath = path.join(docsRoot, \`prompt_os/roles/\${current.role || "engineer"}.md\`)
try { const rc = fs.readFileSync(roleCapsulePath, "utf8").trim(); if (rc) staticParts.push(rc) } catch {}

const staticPrefix = staticParts.join("\\n\\n")

// === Dynamic suffix (varies per task) ===
const dynamicParts = []
if (current.contextPackId) {
  const ctxText = getContextPack(current.contextPackId)
  if (ctxText) dynamicParts.push(\`<context_pack id="\${current.contextPackId}">\\n\${ctxText}\\n</context_pack>\`)
}
if (current.threadId) {
  // ... existing thread injection code ...
}
dynamicParts.push(current.prompt)
const dynamicSuffix = dynamicParts.join("\\n\\n")

// Combine: static prefix + separator + dynamic suffix
const injected = staticPrefix
  ? staticPrefix + "\\n\\n---\\n\\n" + dynamicSuffix
  : dynamicSuffix
\`\`\`

### 2. 在 job 对象上记录前缀大小

\`\`\`javascript
job.staticPrefixBytes = Buffer.byteLength(staticPrefix, "utf8")
\`\`\`

这样 Token CFO 可以追踪缓存效率。

## 测试
1. 启动 gateway，创建 2 个相同 role 的任务
2. 检查第 2 个任务的 \`cached_input_tokens\` > 0
3. 检查 Token CFO snapshot 的 \`cache_ratio\` > 0

## 验收标准
- prompt 组装顺序变为 static → dynamic
- 同角色连续任务的 cache_ratio > 20%
- 无回归：所有现有测试仍然通过`,
      kind: "atomic",
      parentId,
      role: "gateway_engineer",
      lane: "mainlane",
      status: "ready",
      files: ["oc-scc-local/src/gateway.mjs"],
      pins: { allowed_paths: ["oc-scc-local/src/gateway.mjs", "docs/prompt_os/compiler/", "docs/prompt_os/roles/"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli", "codex"],
      allowedModels: ["claude-sonnet", "gpt-4o", "glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "grep -q 'staticPrefix' oc-scc-local/src/gateway.mjs",
        "grep -q 'staticPrefixBytes' oc-scc-local/src/gateway.mjs",
        "node -e \"require('http').get('http://127.0.0.1:18788/health', r => { let d=''; r.on('data',c=>d+=c); r.on('end',()=>{console.log(d);process.exit(JSON.parse(d).ok?0:1)}) })\"",
      ],
      assumptions: [
        "Modify prompt assembly order in gateway.mjs ~lines 10721-10738",
        "Static parts first (legal_prefix, CI handbook, role capsule), then dynamic (context_pack, thread, goal)",
        "Graceful fallback if prompt_os files don't exist yet",
      ],
    },

    // ═══════════════════════════════════════════════════════════════
    // TOK-02: Context Grading by Task Type (HIGH)
    // ═══════════════════════════════════════════════════════════════
    {
      title: "TOK-02: Context Grading by Task Type",
      goal: `# 任务：按任务类型设置差异化 Context 上限

## 影响：HIGH — doc/split 类任务预计节省 40-70%

## 背景
当前所有任务统一使用 220KB context pack 上限 (gateway.mjs:5798)。
但 Token CFO 分析显示，doc 类任务的 context 60%+ 未被使用。

## 具体修改

### 1. 新增 context budget 配置表

在 gateway.mjs 的 context pack 构建函数附近（~line 5790-5800），添加：

\`\`\`javascript
// Context budget by role (bytes). Falls back to DEFAULT if role not listed.
const CONTEXT_BUDGET_BY_ROLE = {
  doc:           50_000,    // 50KB — 只需 goal + 少量参考
  split:         80_000,    // 80KB — map 摘要 + 任务列表
  planner:       80_000,    // 同 split
  designer:      80_000,    // 同 split
  reviewer:     100_000,    // 100KB — patch + 相关代码
  ssot_curator: 100_000,    // 100KB
  engineer:     200_000,    // 200KB — 需要广泛上下文
  integrator:   200_000,    // 同 engineer
  DEFAULT:      220_000,    // 220KB — 当前默认值
}

function getContextBudget(role) {
  return CONTEXT_BUDGET_BY_ROLE[role] ?? CONTEXT_BUDGET_BY_ROLE.DEFAULT
}
\`\`\`

### 2. 在 createContextPackFromPins() 中使用

定位到 gateway.mjs ~line 7437，当前的 hard-coded 限制：
\`\`\`javascript
const maxBytes = 220_000  // ← 改这里
\`\`\`

改为：
\`\`\`javascript
const maxBytes = getContextBudget(task?.role ?? "DEFAULT")
\`\`\`

### 3. 同样修改 createContextPackFromFiles()

~line 5798-5800，同样替换硬编码的 220000。

### 4. 在 Token CFO 中记录实际 budget

在 job 完成时记录 \`job.contextBudget = maxBytes\`，
Token CFO 可以用这个值计算利用率。

## 测试
- 创建 role=doc 的任务，验证 context pack < 50KB
- 创建 role=engineer 的任务，验证 context pack ≤ 200KB
- Token CFO snapshot 中 doc 类 avg context_bytes 应 < 50KB

## 验收标准
- CONTEXT_BUDGET_BY_ROLE 配置表存在
- createContextPackFromPins 和 createContextPackFromFiles 都使用动态 budget
- doc 类任务的 context pack 实际 < 50KB`,
      kind: "atomic",
      parentId,
      role: "gateway_engineer",
      lane: "mainlane",
      status: "ready",
      files: ["oc-scc-local/src/gateway.mjs"],
      pins: { allowed_paths: ["oc-scc-local/src/gateway.mjs"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli", "codex"],
      allowedModels: ["claude-sonnet", "gpt-4o", "glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "grep -q 'CONTEXT_BUDGET_BY_ROLE' oc-scc-local/src/gateway.mjs",
        "grep -q 'getContextBudget' oc-scc-local/src/gateway.mjs",
      ],
      assumptions: [
        "Modify context pack byte limits at gateway.mjs ~lines 5798, 7437",
        "Add role-based budget table",
        "Keep 220KB as DEFAULT fallback",
      ],
    },

    // ═══════════════════════════════════════════════════════════════
    // TOK-03: Token CFO Auto-Correction Feedback Loop (MEDIUM)
    // ═══════════════════════════════════════════════════════════════
    {
      title: "TOK-03: Token CFO Auto-Correction Feedback Loop",
      goal: `# 任务：让 Token CFO 自动修正浪费的 Pins 配置

## 影响：MEDIUM — 累积效应，持续降低浪费

## 背景
Token CFO (gateway.mjs:6252-6325) 每 120 秒扫描一次，检测 unused_ratio >= 0.6 的任务。
当前它只产出报告，不自动修正 — 开环系统。

## 具体修改

### 1. 新增 pins 黑名单存储

在 gateway.mjs 中添加内存存储：

\`\`\`javascript
// Persistent exclusion list: files that are consistently pinned but never touched
// Key = task_class_id, Value = Set of file paths to exclude
const pinsExclusionMap = new Map()

// Persist to disk for recovery
const pinsExclusionFile = path.join(boardDir, "pins_exclusion.json")
function loadPinsExclusion() {
  try {
    const data = JSON.parse(fs.readFileSync(pinsExclusionFile, "utf8"))
    for (const [k, v] of Object.entries(data)) pinsExclusionMap.set(k, new Set(v))
  } catch {}
}
function savePinsExclusion() {
  const obj = {}
  for (const [k, v] of pinsExclusionMap) obj[k] = [...v]
  fs.writeFileSync(pinsExclusionFile, JSON.stringify(obj, null, 2))
}
\`\`\`

### 2. 修改 Token CFO 回调，闭环修正

在 computeTokenCfoSnapshot() (~line 6252) 返回的 top_wasted_contextpacks 中，
对每个高浪费的 task_class 自动更新排除列表：

\`\`\`javascript
function applyTokenCfoCorrections(snapshot) {
  const corrections = []
  for (const w of snapshot.top_wasted_contextpacks) {
    const classId = w.task_class ?? "unknown"
    if (w.unused_ratio < 0.6 || w.included < 3) continue

    let exclusions = pinsExclusionMap.get(classId) || new Set()
    let added = 0
    for (const f of w.sample_unused) {
      if (!exclusions.has(f)) { exclusions.add(f); added++ }
    }
    if (added > 0) {
      pinsExclusionMap.set(classId, exclusions)
      corrections.push({ classId, added, total: exclusions.size })
    }
  }
  if (corrections.length) {
    savePinsExclusion()
    emitEvent("TOKEN_CFO_AUTO_CORRECTION", { corrections })
  }
  return corrections
}
\`\`\`

### 3. 在 context pack 构建时应用排除列表

在 createContextPackFromPins() 中，组装文件列表前检查排除列表：

\`\`\`javascript
// Before reading files into context pack:
const classId = task?.task_class_id ?? "unknown"
const exclusions = pinsExclusionMap.get(classId) || new Set()
const filteredFiles = fileList.filter(f => !exclusions.has(normalizePathish(f)))
\`\`\`

### 4. 在 Token CFO 定时器中触发修正

在 TOKEN_CFO_HOOK (~line 9991-10012) 完成扫描后调用：
\`\`\`javascript
const snapshot = computeTokenCfoSnapshot()
applyTokenCfoCorrections(snapshot)
\`\`\`

## 测试
- 连续创建 5 个相同 task_class 的任务，其中 pin 了 10 个文件但只用了 3 个
- 等待 3 个 CFO 周期（~6 分钟）
- 验证第 6 个同类任务的 context pack 排除了未使用的文件
- 验证 pins_exclusion.json 文件存在且内容正确

## 验收标准
- pinsExclusionMap 存储存在
- Token CFO 扫描后自动调用 applyTokenCfoCorrections
- context pack 构建时应用排除列表
- 排除操作 emit TOKEN_CFO_AUTO_CORRECTION 事件`,
      kind: "atomic",
      parentId,
      role: "gateway_engineer",
      lane: "mainlane",
      status: "ready",
      files: ["oc-scc-local/src/gateway.mjs"],
      pins: { allowed_paths: ["oc-scc-local/src/gateway.mjs"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli", "codex"],
      allowedModels: ["claude-sonnet", "gpt-4o", "glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "grep -q 'pinsExclusionMap' oc-scc-local/src/gateway.mjs",
        "grep -q 'applyTokenCfoCorrections' oc-scc-local/src/gateway.mjs",
        "grep -q 'TOKEN_CFO_AUTO_CORRECTION' oc-scc-local/src/gateway.mjs",
      ],
      assumptions: [
        "Add pins exclusion storage with disk persistence",
        "Modify Token CFO hook to auto-correct",
        "Apply exclusions in context pack builder",
      ],
    },

    // ═══════════════════════════════════════════════════════════════
    // TOK-04: JSON Compaction in Prompt Injection (LOW-MEDIUM)
    // ═══════════════════════════════════════════════════════════════
    {
      title: "TOK-04: JSON Compaction in Prompt Injection",
      goal: `# 任务：将 Prompt 注入中的 JSON 从 pretty-print 改为紧凑格式

## 影响：LOW-MEDIUM — 节省 10-15%（JSON 密集的 prompt）

## 背景
gateway.mjs 中有约 15+ 处使用 JSON.stringify(obj, null, 2) 将 JSON 注入 prompt。
2-space 缩进浪费约 33% 的字节。

## 具体修改

搜索 gateway.mjs 中所有 JSON.stringify 调用，区分两类：

### A类：注入到 prompt 的 JSON — 改为紧凑格式
这些 JSON 会被模型读取，紧凑格式模型同样能理解。

需要修改的位置（搜索 \`JSON.stringify\` 并检查上下文）：
- ~line 1858: snapshot params 注入到 factory_manager prompt
- ~line 4210: task params 注入到 prompt
- ~line 6303: Token CFO snapshot 注入到 prompt
- 其他所有 \`prompt +=\` 或 \`goal +=\` 或 \`params[...] = JSON.stringify\` 的位置

修改方式：
\`\`\`javascript
// ❌ Before:
params.snapshot_json = JSON.stringify(snapshot, null, 2)

// ✅ After:
params.snapshot_json = JSON.stringify(snapshot)
\`\`\`

### B类：写入文件/日志的 JSON — 保持 pretty-print
这些是给人读的，保持可读性。

保留的位置：
- fs.writeFileSync(..., JSON.stringify(..., null, 2)) — 写入磁盘
- console.log(JSON.stringify(..., null, 2)) — 日志输出
- report/evidence 文件写入

### 辨别规则
\`\`\`
如果 JSON.stringify 的结果:
  → 赋值给 params.* 或 拼接到 prompt/goal 字符串 → 用紧凑格式
  → 写入 fs.writeFileSync 或 console.log → 保持 pretty-print
\`\`\`

## 测试
- 对比修改前后同一任务的 prompt 字节数
- 验证 prompt 中不再有缩进的 JSON
- 验证日志文件中的 JSON 仍然有缩进

## 验收标准
- 所有 prompt 注入路径使用 JSON.stringify(obj)（无缩进）
- 所有文件/日志写入路径保持 JSON.stringify(obj, null, 2)
- 无功能回归`,
      kind: "atomic",
      parentId,
      role: "gateway_engineer",
      lane: "batchlane",
      status: "ready",
      files: ["oc-scc-local/src/gateway.mjs"],
      pins: { allowed_paths: ["oc-scc-local/src/gateway.mjs"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli", "codex"],
      allowedModels: ["claude-sonnet", "gpt-4o", "glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "node -e \"const c=require('fs').readFileSync('oc-scc-local/src/gateway.mjs','utf8'); const m=c.match(/JSON\\.stringify\\([^)]+,\\s*null,\\s*2\\)/g)||[]; console.log('pretty-print count:', m.length); process.exit(m.length < 20 ? 0 : 1)\"",
      ],
      assumptions: [
        "Only change JSON in prompt injection paths, not file/log writes",
        "Search for all JSON.stringify(*, null, 2) and classify each",
      ],
    },

    // ═══════════════════════════════════════════════════════════════
    // TOK-05: Map Summarization Levels L0/L1/L2 (MEDIUM)
    // ═══════════════════════════════════════════════════════════════
    {
      title: "TOK-05: Map Summarization Levels L0/L1/L2",
      goal: `# 任务：为 Map 引擎添加 3 级摘要输出

## 影响：MEDIUM — 非 engineer 任务节省 20-40%

## 背景
map_v1.mjs (886 行) 构建代码库的完整符号索引。
当前 map 输出是单一完整版本，包含所有文件的符号、依赖、入口点。
注入到 context 中可能 50-200KB，但 doc/split 任务只需要文件列表。

## 具体修改

### 1. 在 map_v1.mjs 中添加摘要函数

\`\`\`javascript
/**
 * Map 摘要级别：
 * L0: 文件列表 + 入口点 (~2KB) — 用于 doc, split, planner
 * L1: L0 + 函数签名 (~10KB) — 用于 reviewer, designer
 * L2: 完整符号 + 依赖图 (~50KB+) — 用于 engineer
 */
export function summarizeMap(mapData, level = "L2") {
  if (level === "L0") {
    return {
      level: "L0",
      files: mapData.files?.map(f => f.path) ?? [],
      entry_points: mapData.entry_points ?? [],
      total_files: mapData.files?.length ?? 0,
      total_symbols: mapData.symbols?.length ?? 0,
    }
  }

  if (level === "L1") {
    return {
      level: "L1",
      files: mapData.files?.map(f => ({
        path: f.path,
        exports: f.exports?.map(e => e.name + (e.signature ? \`(\${e.signature})\` : "")) ?? [],
      })) ?? [],
      entry_points: mapData.entry_points ?? [],
      symbols: mapData.symbols?.map(s => ({
        name: s.name,
        kind: s.kind,
        file: s.file,
        signature: s.signature?.slice(0, 120),
      })) ?? [],
    }
  }

  // L2: return full map
  return { level: "L2", ...mapData }
}

// Role to map level mapping
const MAP_LEVEL_BY_ROLE = {
  doc: "L0",
  split: "L0",
  planner: "L0",
  designer: "L1",
  reviewer: "L1",
  ssot_curator: "L1",
  engineer: "L2",
  integrator: "L2",
  DEFAULT: "L2",
}

export function getMapLevelForRole(role) {
  return MAP_LEVEL_BY_ROLE[role] ?? MAP_LEVEL_BY_ROLE.DEFAULT
}
\`\`\`

### 2. 在 gateway.mjs 中调用

在 context pack 构建时（~line 7437-7547），当需要注入 map 数据时：

\`\`\`javascript
// Before injecting map into context:
const mapLevel = getMapLevelForRole(task.role)
const mapSummary = summarizeMap(fullMapData, mapLevel)
const mapText = JSON.stringify(mapSummary)
\`\`\`

### 3. 在 job 对象上记录

\`\`\`javascript
job.mapLevel = mapLevel
job.mapBytes = Buffer.byteLength(mapText, "utf8")
\`\`\`

## 测试
- L0 输出 < 3KB（用当前仓库测试）
- L1 输出 < 15KB
- doc 角色任务使用 L0
- engineer 角色任务使用 L2（完整版）

## 验收标准
- summarizeMap 函数存在于 map_v1.mjs
- 3 个级别都能正确输出
- gateway.mjs 在 context pack 中使用角色对应的 map level`,
      kind: "atomic",
      parentId,
      role: "gateway_engineer",
      lane: "mainlane",
      status: "ready",
      files: ["oc-scc-local/src/map_v1.mjs", "oc-scc-local/src/gateway.mjs"],
      pins: { allowed_paths: ["oc-scc-local/src/map_v1.mjs", "oc-scc-local/src/gateway.mjs"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli", "codex"],
      allowedModels: ["claude-sonnet", "gpt-4o", "glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "grep -q 'summarizeMap' oc-scc-local/src/map_v1.mjs",
        "grep -q 'MAP_LEVEL_BY_ROLE' oc-scc-local/src/map_v1.mjs",
        "grep -q 'mapLevel' oc-scc-local/src/gateway.mjs",
      ],
      assumptions: [
        "Add summarizeMap function to map_v1.mjs",
        "Integrate into gateway.mjs context pack builder",
        "Keep full L2 as default for unknown roles",
      ],
    },

    // ═══════════════════════════════════════════════════════════════
    // TOK-06: Deduplicate Static Block Injection (LOW)
    // ═══════════════════════════════════════════════════════════════
    {
      title: "TOK-06: Deduplicate Static Block Injection",
      goal: `# 任务：去重静态 Block 注入

## 影响：LOW — 每任务节省 ~200 tokens，batch 场景下累积效果

## 背景
每个 prompt 都注入相同的静态 blocks：
- CI Handbook (~200 tokens) — gateway.mjs:10736
- Header 3-pointers (~20 tokens)
这些内容对同一 role 的 batch 任务是完全相同的。

## 具体修改

### 1. 为静态 block 计算 hash

\`\`\`javascript
const crypto = require("crypto")

// Cache for rendered static blocks
const staticBlockCache = new Map()

function getStaticBlockHash(role) {
  const key = \`static_\${role}\`
  if (staticBlockCache.has(key)) return staticBlockCache.get(key)

  const parts = []
  const ciHandbook = getCiHandbookText()
  if (ciHandbook) parts.push(ciHandbook)

  const hash = crypto.createHash("md5").update(parts.join("\\n")).digest("hex").slice(0, 8)
  const result = { hash, text: parts.join("\\n"), byteSize: Buffer.byteLength(parts.join("\\n"), "utf8") }
  staticBlockCache.set(key, result)
  return result
}
\`\`\`

### 2. 在 prompt_ref 中记录 block hash

\`\`\`javascript
job.prompt_ref = {
  ...job.prompt_ref,
  static_block_hash: getStaticBlockHash(task.role).hash,
  static_block_bytes: getStaticBlockHash(task.role).byteSize,
}
\`\`\`

### 3. 在 Token CFO 中追踪 block 重复率

Token CFO snapshot 新增指标：
\`\`\`javascript
const blockHashes = jobs.map(j => j.prompt_ref?.static_block_hash).filter(Boolean)
const uniqueHashes = new Set(blockHashes).size
snapshot.block_dedup_ratio = blockHashes.length > 0
  ? 1 - (uniqueHashes / blockHashes.length)
  : 0
// block_dedup_ratio 接近 1.0 说明大量重复
\`\`\`

这个指标不直接省 token（那是 TOK-01 的工作），但提供数据支撑让我们知道
缓存友好前缀的效果。

## 测试
- 创建 10 个同 role 的任务
- 验证所有 prompt_ref.static_block_hash 相同
- Token CFO 的 block_dedup_ratio > 0.8

## 验收标准
- staticBlockCache 存在
- prompt_ref 包含 static_block_hash
- Token CFO snapshot 包含 block_dedup_ratio`,
      kind: "atomic",
      parentId,
      role: "gateway_engineer",
      lane: "batchlane",
      status: "ready",
      files: ["oc-scc-local/src/gateway.mjs"],
      pins: { allowed_paths: ["oc-scc-local/src/gateway.mjs"], forbidden_paths: [] },
      allowedExecutors: ["opencodecli", "codex"],
      allowedModels: ["claude-sonnet", "gpt-4o", "glm-4.7", "kimi-k2.5"],
      allowedTests: [
        "grep -q 'staticBlockCache' oc-scc-local/src/gateway.mjs",
        "grep -q 'static_block_hash' oc-scc-local/src/gateway.mjs",
        "grep -q 'block_dedup_ratio' oc-scc-local/src/gateway.mjs",
      ],
      assumptions: [
        "Add static block caching with hash tracking",
        "Record in prompt_ref for audit",
        "Add dedup ratio metric to Token CFO",
      ],
    },
  ];
}

// ─── Main ────────────────────────────────────────────────────────────

async function main() {
  const dryRun = process.argv.includes("--dry-run");

  console.log("╔══════════════════════════════════════════════════════════╗");
  console.log("║   Token Optimization — Batch Task Submission             ║");
  console.log("╚══════════════════════════════════════════════════════════╝");
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Mode: ${dryRun ? "DRY RUN" : "LIVE"}\n`);
  console.log("⚠️  Note: All tasks require oc-scc-local/** write access.");
  console.log("   Current engineer role denies this path.");
  console.log("   → Create gateway_engineer role or use admin override.\n");

  let parentId = null;

  console.log("━━━ Step 1: Creating parent task ━━━");
  if (dryRun) {
    parentId = "dry-run-parent";
    console.log("[DRY] Parent:", PARENT_TASK.title);
  } else {
    try {
      const parent = await post("/board/tasks", PARENT_TASK);
      parentId = parent.id;
      console.log(`✓ Parent: ${parentId} — ${parent.title}`);
    } catch (err) {
      console.error(`✗ Parent failed: ${err.message}`);
      process.exit(1);
    }
  }

  console.log("\n━━━ Step 2: Creating 6 child tasks ━━━");
  const children = childTasks(parentId);
  const results = [];

  for (let i = 0; i < children.length; i++) {
    const task = children[i];
    const label = `TOK-${String(i + 1).padStart(2, "0")}`;

    if (dryRun) {
      console.log(`[DRY] ${label}: ${task.title}`);
      console.log(`      Files: ${task.files.join(", ")}`);
      results.push({ label, title: task.title, status: "dry-run" });
    } else {
      try {
        const created = await post("/board/tasks", task);
        console.log(`✓ ${label}: ${created.title} → ${created.id}`);
        results.push({ label, title: created.title, id: created.id, status: "created" });
      } catch (err) {
        console.error(`✗ ${label}: ${task.title} → ${err.message}`);
        results.push({ label, title: task.title, status: "failed", error: err.message });
      }
      await sleep(200);
    }
  }

  console.log("\n━━━ Summary ━━━");
  console.log(`Parent: ${parentId}`);
  const ok = results.filter(r => r.status === "created" || r.status === "dry-run").length;
  console.log(`Children: ${ok}/${results.length} successful\n`);

  console.log("┌────────┬──────────────────────────────────────────────────────┬──────────┐");
  console.log("│ ID     │ Title                                                │ Status   │");
  console.log("├────────┼──────────────────────────────────────────────────────┼──────────┤");
  for (const r of results) {
    const t = r.title.substring(0, 52).padEnd(52);
    const s = r.status.padEnd(8);
    console.log(`│ ${r.label} │ ${t} │ ${s} │`);
  }
  console.log("└────────┴──────────────────────────────────────────────────────┴──────────┘");

  if (dryRun) {
    const allTasks = { parent: PARENT_TASK, children };
    const { writeFileSync, mkdirSync } = await import("fs");
    mkdirSync("artifacts", { recursive: true });
    writeFileSync("artifacts/token_optimize_tasks.json", JSON.stringify(allTasks, null, 2));
    console.log("\nTask definitions written to: artifacts/token_optimize_tasks.json");
  }
}

main().catch(err => { console.error("Fatal:", err); process.exit(1); });
