# SCC Token 优化指南

## 概述

本指南介绍 SCC 系统中的6个Token优化任务实现，可显著降低LLM调用的token消耗。

## 快速开始

```bash
# 运行所有优化测试
node tools/test_token_optimize.mjs

# 查看优化配置
node tools/token_optimize_batch.mjs
```

## 6个Token优化任务

### TOK-01: Prompt 前缀重构（缓存友好）

**目标**: 利用 Claude 的 prompt caching 能力，将静态前缀缓存，只传输变化部分。

**实现**: [buildCacheFriendlySystemPrompt](tools/token_optimize_batch.mjs#L60)

```javascript
import { buildCacheFriendlySystemPrompt } from './tools/token_optimize_batch.mjs';

const result = buildCacheFriendlySystemPrompt(
  'Role: ENGINEER\nGoal: Fix bug',
  'Context: Error on line 42'
);

// result.staticPrefix - 会被缓存的静态部分
// result.dynamicPart - 每次变化的部分
// result.fullPrompt - 完整提示词
// result.cacheKey - 用于追踪缓存命中率
```

**预期节省**: 30-50%（相同role的连续任务）

---

### TOK-02: Context 按任务类型分级限额

**目标**: 根据任务类型动态调整context上限，避免过度加载。

**实现**: [createContextPackFromPins](tools/token_optimize_batch.mjs#L110)

```javascript
import { createContextPackFromPins, getContextLimitForTaskType } from './tools/token_optimize_batch.mjs';

// 查看不同任务类型的限制
const limits = {
  doc: getContextLimitForTaskType('doc'),       // 50KB
  bug_fix: getContextLimitForTaskType('bug_fix'), // 100KB
  refactor: getContextLimitForTaskType('refactor'), // 200KB
  split: getContextLimitForTaskType('split'),    // 80KB
};

// 创建分级context pack
const pins = [
  { path: 'src/gateway.mjs', line_windows: [3500, 3700] },
  { path: 'src/utils.mjs', size: 20000 },
];

const contextPack = createContextPackFromPins(pins, 'doc');
// 结果: { pins, totalBytes, limit, strategy, utilization }
```

**分级策略**:

| 任务类型 | 上限 | 策略 |
|---------|------|------|
| doc | 50KB | minimal - 只保留元数据 |
| bug_fix | 100KB | precise - 使用line_windows |
| refactor | 200KB | full - 完整内容 |
| split/plan | 80KB | summary - 只保留摘要 |

**预期节省**: 50-75%（doc/split任务）

---

### TOK-03: Token CFO 自动修正闭环

**目标**: 自动检测和修正token浪费，形成闭环优化。

**实现**: [TokenCFO 类](tools/token_optimize_batch.mjs#L171)

```javascript
import { tokenCFO } from './tools/token_optimize_batch.mjs';

// 分析任务浪费情况
const pinsUsed = [
  { path: 'src/gateway.mjs' },
  { path: 'src/utils.mjs' },
  { path: 'src/config.mjs' },
];
const pinsTouched = ['src/gateway.mjs']; // 只有1/3被实际使用

const analysis = tokenCFO.analyzeTaskWaste(
  'task-001',
  'bug_fix',
  pinsUsed,
  pinsTouched
);

// 如果 unused_ratio >= 60%，自动生成修正actions
// analysis.actions: [
//   { type: 'tighten_pins_template', ... },
//   { type: 'reduce_context_limit', ... },
//   { type: 'record_exclusions', ... }
// ]

// 应用自动修正
const results = tokenCFO.applyAutoAdjust(analysis.actions);
```

**自动修正策略**:
1. 收紧pins模板（排除未使用的文件）
2. 降低该任务类型的context上限
3. 记录排除文件，下次自动过滤

**预期节省**: 15-20% waste reduction

---

### TOK-04: JSON 注入紧凑化

**目标**: 移除prompt中JSON的不必要缩进，减少token消耗。

**实现**: [compactJSON](tools/token_optimize_batch.mjs#L298)

```javascript
import { compactJSON } from './tools/token_optimize_batch.mjs';

// ❌ 浪费空间（用于日志）
JSON.stringify(obj, null, 2)

// ✅ 紧凑格式（用于prompt）
compactJSON(obj, false)  // 或 JSON.stringify(obj)

// 人类可读（用于日志）
compactJSON(obj, true)   // 等同于 JSON.stringify(obj, null, 2)
```

**预期节省**: ~33%（JSON部分）

---

### TOK-05: Map 摘要分级 L0/L1/L2

**目标**: 根据任务复杂度提供不同级别的map摘要。

**实现**: [createMapSummary](tools/token_optimize_batch.mjs#L333)

```javascript
import { createMapSummary, getMapLevelForTaskType } from './tools/token_optimize_batch.mjs';

// L0: 文件列表 + 入口点 (~2KB)
const l0 = createMapSummary(mapData, 'L0');

// L1: + 函数签名 (~10KB)
const l1 = createMapSummary(mapData, 'L1');

// L2: + 完整符号 (~50-200KB)
const l2 = createMapSummary(mapData, 'L2');

// 根据任务类型自动选择级别
const level = getMapLevelForTaskType('doc');     // 'L0'
const level = getMapLevelForTaskType('bug_fix'); // 'L1'
const level = getMapLevelForTaskType('refactor'); // 'L2'
```

**级别对比**:

| 级别 | 内容 | 大小 |
|-----|------|------|
| L0 | 模块列表 + 入口点 | ~2KB |
| L1 | + 函数签名 | ~10KB |
| L2 | + 完整符号表 | ~50-200KB |

**预期节省**: 90%+（doc任务使用L0 vs L2）

---

### TOK-06: 静态 Block 注入去重

**目标**: 避免在同一role的连续任务中重复注入静态block。

**实现**: [StaticBlockDeduplicator 类](tools/token_optimize_batch.mjs#L413)

```javascript
import { blockDeduplicator } from './tools/token_optimize_batch.mjs';

const blocks = [
  { id: 'constitution', content: '...', dynamic: false },
  { id: 'handbook', content: '...', dynamic: false },
  { id: 'context', content: '...', dynamic: true },
];

// 第一次注入 - 所有blocks
const first = blockDeduplicator.deduplicateBlocks(blocks, 'ENGINEER');
// 结果: 3 blocks

// 第二次注入 - 跳过已注入的静态blocks
const second = blockDeduplicator.deduplicateBlocks(blocks, 'ENGINEER');
// 结果: 0 blocks (已去重)

// 批量任务优化
const batchTasks = [
  { id: 1, blocks: [...blocks] },
  { id: 2, blocks: [...blocks] },
  { id: 3, blocks: [...blocks] },
];
const optimized = blockDeduplicator.optimizeBatchTasks(batchTasks, 'ENGINEER');
// Task 1: 所有blocks
// Task 2-3: 只包含 dynamic=true 的blocks
```

**预期节省**: ~200 tokens/重复block

---

## 集成指南

### 在 Gateway 中集成

```javascript
// L1_code_layer/gateway/gateway.mjs

import {
  buildCacheFriendlySystemPrompt,
  createContextPackFromPins,
  tokenCFO,
  compactJSON,
  createMapSummary,
  getMapLevelForTaskType,
  blockDeduplicator,
} from '../../tools/token_optimize_batch.mjs';

// 1. 构建缓存友好的prompt
function buildPrompt(role, context, taskType) {
  const roleCapsule = loadRoleCapsule(role);
  const { fullPrompt, cacheKey } = buildCacheFriendlySystemPrompt(roleCapsule, context);
  return { prompt: fullPrompt, cacheKey };
}

// 2. 创建分级context pack
function buildContextPack(pins, taskType) {
  return createContextPackFromPins(pins, taskType);
}

// 3. 使用紧凑JSON
function buildMessageContent(data) {
  return compactJSON(data, false); // 紧凑格式
}

// 4. 获取map摘要
function getMapForTask(mapData, taskType, filterPaths) {
  const level = getMapLevelForTaskType(taskType);
  return createMapSummary(mapData, level, filterPaths);
}

// 5. 去重静态blocks
function injectBlocks(blocks, role) {
  return blockDeduplicator.deduplicateBlocks(blocks, role);
}

// 6. Token CFO分析
function analyzeTask(taskId, taskClass, pinsUsed, pinsTouched) {
  const { wasteData, actions } = tokenCFO.analyzeTaskWaste(taskId, taskClass, pinsUsed, pinsTouched);
  if (actions.length > 0) {
    tokenCFO.applyAutoAdjust(actions);
  }
  return wasteData;
}
```

### 在 Executor 中集成

```javascript
// L6_execution_layer/executors/opencodecli_executor.mjs

import { compactJSON } from '../../tools/token_optimize_batch.mjs';

// 构建请求时使用紧凑JSON
function buildRequest(messages, model) {
  return {
    model,
    messages: messages.map(m => ({
      role: m.role,
      content: typeof m.content === 'object' 
        ? compactJSON(m.content, false)  // 紧凑格式
        : m.content
    })),
  };
}
```

---

## 预期效果

| 优化项 | 节省比例 | 适用场景 |
|-------|---------|---------|
| TOK-01 缓存友好前缀 | 30-50% | 相同role的连续任务 |
| TOK-02 Context分级 | 50-75% | doc/split/plan任务 |
| TOK-03 Token CFO | 15-20% | 自动检测和修正浪费 |
| TOK-04 紧凑JSON | ~33% | 所有JSON注入 |
| TOK-05 Map分级 | 90%+ | doc任务使用L0 |
| TOK-06 Block去重 | ~200tok/block | 批量任务 |

**综合效果**: 根据任务类型，可节省 **40-70%** 的token消耗。

---

## 监控和调优

### 追踪缓存命中率

```javascript
const { cacheKey } = buildCacheFriendlySystemPrompt(roleCapsule, context);
// 记录cacheKey到日志，分析缓存命中率
```

### 监控Token CFO报告

```javascript
// Token CFO会自动生成 .token_cfo_exclusions.json
// 包含被排除的文件列表
```

### 调整Context限制

编辑 [token_optimize_batch.mjs](tools/token_optimize_batch.mjs#L88) 中的 `CONTEXT_LIMITS_BY_TASK_TYPE`:

```javascript
const CONTEXT_LIMITS_BY_TASK_TYPE = {
  doc: { maxBytes: 50 * 1024, strategy: 'minimal' },
  bug_fix: { maxBytes: 100 * 1024, strategy: 'precise' },
  // 添加自定义任务类型...
  my_task: { maxBytes: 150 * 1024, strategy: 'summary' },
};
```

---

## 文件清单

- `tools/token_optimize_batch.mjs` - 主要实现文件
- `tools/test_token_optimize.mjs` - 测试脚本
- `tools/TOKEN_OPTIMIZATION_GUIDE.md` - 本指南
- `.token_cfo_exclusions.json` - Token CFO生成的排除文件列表（自动生成）
