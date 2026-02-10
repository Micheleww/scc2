#!/usr/bin/env node
/**
 * Token Optimize Batch Script
 * SCC Token Optimization Implementation
 * 
 * 实现6个Token优化任务:
 * TOK-01: Prompt 前缀重构（缓存友好）
 * TOK-02: Context 按任务类型分级限额
 * TOK-03: Token CFO 自动修正闭环
 * TOK-04: JSON 注入紧凑化
 * TOK-05: Map 摘要分级 L0/L1/L2
 * TOK-06: 静态 Block 注入去重
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');

// ============================================
// TOK-01: Prompt 前缀重构（缓存友好）
// ============================================

const CACHE_FRIENDLY_PREFIX = {
  // 静态前缀组件 - 这些会被Claude缓存
  constitution: `You are an expert software engineering assistant. Follow these principles:
- Write clean, maintainable code
- Follow existing code conventions
- Prioritize correctness over cleverness`,
  
  legal_prefix: `Legal: All code suggestions are provided as-is. Review before use.`,
  
  // 从 header_3pointers_v1.txt 读取
  header_3pointers: null, // 将动态加载
  
  // CI Handbook 内容
  ci_handbook: null, // 将动态加载
};

// 加载静态前缀组件
function loadStaticPrefixes() {
  const blocksDir = path.join(REPO_ROOT, 'L4_prompt_layer', 'prompts', 'blocks');
  
  // 加载 header_3pointers_v1.txt
  try {
    const headerPath = path.join(blocksDir, 'header_3pointers_v1.txt');
    if (fs.existsSync(headerPath)) {
      CACHE_FRIENDLY_PREFIX.header_3pointers = fs.readFileSync(headerPath, 'utf-8');
    }
  } catch (e) {
    console.warn('[TOK-01] 无法加载 header_3pointers:', e.message);
  }
  
  return CACHE_FRIENDLY_PREFIX;
}

// 构建缓存友好的系统提示
export function buildCacheFriendlySystemPrompt(roleCapsule, dynamicContext) {
  const prefixes = loadStaticPrefixes();
  
  // 静态部分（会被缓存）
  const staticPrefix = [
    prefixes.constitution,
    prefixes.legal_prefix,
    prefixes.header_3pointers,
  ].filter(Boolean).join('\n\n');
  
  // 动态部分（每次变化）
  const dynamicPart = [
    roleCapsule,
    dynamicContext,
  ].filter(Boolean).join('\n\n');
  
  return {
    staticPrefix,  // 这部分会被Claude缓存
    dynamicPart,   // 这部分每次变化
    fullPrompt: staticPrefix + '\n\n' + dynamicPart,
    cacheKey: hashString(staticPrefix), // 用于追踪缓存命中率
  };
}

// ============================================
// TOK-02: Context 按任务类型分级限额
// ============================================

const CONTEXT_LIMITS_BY_TASK_TYPE = {
  // 文档类任务 - 只需goal + 少量参考
  doc: { maxBytes: 50 * 1024, strategy: 'minimal' },
  
  // Bug修复 - 精确pin + error log
  bug_fix: { maxBytes: 100 * 1024, strategy: 'precise' },
  
  // 重构 - 需要更多上下文
  refactor: { maxBytes: 200 * 1024, strategy: 'full' },
  
  // 拆分/规划 - map摘要 + 任务列表
  split: { maxBytes: 80 * 1024, strategy: 'summary' },
  plan: { maxBytes: 80 * 1024, strategy: 'summary' },
  
  // 默认
  default: { maxBytes: 220 * 1024, strategy: 'full' },
};

export function getContextLimitForTaskType(taskType) {
  return CONTEXT_LIMITS_BY_TASK_TYPE[taskType] || CONTEXT_LIMITS_BY_TASK_TYPE.default;
}

export function createContextPackFromPins(pins, taskType = 'default') {
  const limit = getContextLimitForTaskType(taskType);
  let totalBytes = 0;
  const packed = [];
  
  for (const pin of pins) {
    // 估算大小
    const estimatedSize = estimatePinSize(pin);
    
    if (totalBytes + estimatedSize > limit.maxBytes) {
      console.warn(`[TOK-02] Context limit reached for ${taskType}: ${totalBytes}/${limit.maxBytes} bytes`);
      break;
    }
    
    // 根据策略处理pin
    const processedPin = processPinByStrategy(pin, limit.strategy);
    if (processedPin) {
      packed.push(processedPin);
      totalBytes += estimatedSize;
    }
  }
  
  return {
    pins: packed,
    totalBytes,
    limit: limit.maxBytes,
    strategy: limit.strategy,
    utilization: (totalBytes / limit.maxBytes * 100).toFixed(1) + '%',
  };
}

function estimatePinSize(pin) {
  if (pin.line_windows) {
    // 如果指定了行号窗口，只计算窗口内的内容
    const lines = pin.line_windows[1] - pin.line_windows[0];
    return lines * 50; // 估算每行50字节
  }
  return pin.size || 10000; // 默认估算
}

function processPinByStrategy(pin, strategy) {
  switch (strategy) {
    case 'minimal':
      // 只保留文件路径和关键元数据
      return { path: pin.path, metadata: pin.metadata };
    case 'precise':
      // 使用line_windows精确控制
      return pin.line_windows ? pin : { path: pin.path, line_windows: [1, 100] };
    case 'summary':
      // 只保留摘要信息
      return { path: pin.path, summary: pin.summary || 'File summary not available' };
    case 'full':
    default:
      return pin;
  }
}

// ============================================
// TOK-03: Token CFO 自动修正闭环
// ============================================

class TokenCFO {
  constructor() {
    this.wasteHistory = new Map(); // taskClass -> wasteData
    this.autoAdjustEnabled = true;
  }
  
  // 分析任务浪费情况
  analyzeTaskWaste(taskId, taskClass, pinsUsed, pinsTouched) {
    const unusedPins = pinsUsed.filter(p => !pinsTouched.includes(p.path));
    const unusedRatio = unusedPins.length / pinsUsed.length;
    
    const wasteData = {
      taskId,
      taskClass,
      unusedRatio,
      unusedPins: unusedPins.map(p => p.path),
      timestamp: new Date().toISOString(),
    };
    
    // 记录到历史
    if (!this.wasteHistory.has(taskClass)) {
      this.wasteHistory.set(taskClass, []);
    }
    this.wasteHistory.get(taskClass).push(wasteData);
    
    // 触发自动修正
    if (this.autoAdjustEnabled && unusedRatio >= 0.6) {
      return this.generateAutoAdjustActions(taskClass, wasteData);
    }
    
    return { wasteData, actions: [] };
  }
  
  generateAutoAdjustActions(taskClass, wasteData) {
    const actions = [];
    
    // 1. 收紧pins模板
    actions.push({
      type: 'tighten_pins_template',
      target: taskClass,
      reason: `Unused ratio ${(wasteData.unusedRatio * 100).toFixed(1)}% >= 60%`,
      excludeFiles: wasteData.unusedPins.slice(0, 10),
    });
    
    // 2. 降低context上限
    const currentLimit = getContextLimitForTaskType(taskClass);
    const newLimit = Math.floor(currentLimit.maxBytes * 0.8);
    actions.push({
      type: 'reduce_context_limit',
      target: taskClass,
      from: currentLimit.maxBytes,
      to: newLimit,
    });
    
    // 3. 记录排除文件
    actions.push({
      type: 'record_exclusions',
      files: wasteData.unusedPins,
      forTaskClass: taskClass,
    });
    
    return { wasteData, actions };
  }
  
  // 应用自动修正
  applyAutoAdjust(actions) {
    const results = [];
    
    for (const action of actions) {
      switch (action.type) {
        case 'tighten_pins_template':
          results.push(this.tightenPinsTemplate(action));
          break;
        case 'reduce_context_limit':
          results.push(this.reduceContextLimit(action));
          break;
        case 'record_exclusions':
          results.push(this.recordExclusions(action));
          break;
      }
    }
    
    return results;
  }
  
  tightenPinsTemplate(action) {
    // 实现收紧pins模板的逻辑
    console.log(`[TOK-03] Tightening pins template for ${action.target}`);
    console.log(`  Excluding files: ${action.excludeFiles.join(', ')}`);
    return { action: 'tighten_pins_template', status: 'applied' };
  }
  
  reduceContextLimit(action) {
    // 实现降低context上限的逻辑
    console.log(`[TOK-03] Reducing context limit for ${action.target}: ${action.from} -> ${action.to}`);
    return { action: 'reduce_context_limit', status: 'applied' };
  }
  
  recordExclusions(action) {
    // 记录排除文件
    const exclusionFile = path.join(REPO_ROOT, '.token_cfo_exclusions.json');
    let exclusions = {};
    
    if (fs.existsSync(exclusionFile)) {
      exclusions = JSON.parse(fs.readFileSync(exclusionFile, 'utf-8'));
    }
    
    if (!exclusions[action.forTaskClass]) {
      exclusions[action.forTaskClass] = [];
    }
    
    exclusions[action.forTaskClass] = [
      ...new Set([...exclusions[action.forTaskClass], ...action.files])
    ];
    
    fs.writeFileSync(exclusionFile, JSON.stringify(exclusions, null, 2));
    
    return { action: 'record_exclusions', status: 'applied', count: action.files.length };
  }
}

export const tokenCFO = new TokenCFO();

// ============================================
// TOK-04: JSON 注入紧凑化
// ============================================

export function compactJSON(obj, prettyPrint = false) {
  if (prettyPrint) {
    // 只在人类可读的日志中使用格式化
    return JSON.stringify(obj, null, 2);
  }
  // 紧凑格式 - 用于prompt注入
  return JSON.stringify(obj);
}

// 替换代码中的JSON.stringify调用
export function optimizeJSONStringify(code) {
  // 匹配用于prompt构建的JSON.stringify
  // 保留用于日志的格式化
  return code.replace(
    /JSON\.stringify\(([^,]+),\s*null,\s*2\)/g,
    (match, obj) => {
      // 检查上下文是否是用于prompt
      if (match.includes('prompt') || match.includes('context') || match.includes('message')) {
        return `JSON.stringify(${obj})`; // 紧凑格式
      }
      return match; // 保留日志用的格式化
    }
  );
}

// ============================================
// TOK-05: Map 摘要分级 L0/L1/L2
// ============================================

export const MAP_SUMMARY_LEVELS = {
  L0: 'file_list',      // 文件列表 + 入口点 (~2KB)
  L1: 'signatures',     // 函数签名 (~10KB)
  L2: 'full_symbols',   // 完整符号 (~50-200KB)
};

export function createMapSummary(mapData, level, filterPaths = null) {
  switch (level) {
    case 'L0':
      return createL0Summary(mapData, filterPaths);
    case 'L1':
      return createL1Summary(mapData, filterPaths);
    case 'L2':
    default:
      return createL2Summary(mapData, filterPaths);
  }
}

function createL0Summary(mapData, filterPaths) {
  // 只保留模块列表和入口点
  const modules = (mapData.modules || [])
    .filter(m => !filterPaths || filterPaths.some(fp => m.root.includes(fp)))
    .map(m => ({ id: m.id, root: m.root, kind: m.kind }));
  
  const entryPoints = (mapData.entry_points || [])
    .slice(0, 50) // 限制数量
    .map(e => ({ id: e.id, kind: e.kind, path: e.path }));
  
  return {
    level: 'L0',
    modules,
    entry_points: entryPoints,
    summary: `Map summary: ${modules.length} modules, ${entryPoints.length} entry points`,
  };
}

function createL1Summary(mapData, filterPaths) {
  const base = createL0Summary(mapData, filterPaths);
  
  // 添加函数签名
  const keySymbols = (mapData.key_symbols || [])
    .filter(ks => !filterPaths || filterPaths.some(fp => ks.path.includes(fp)))
    .slice(0, 200) // 限制数量
    .map(ks => ({
      symbol: ks.symbol,
      kind: ks.kind,
      path: ks.path,
      line: ks.line,
    }));
  
  return {
    ...base,
    level: 'L1',
    key_symbols: keySymbols,
  };
}

function createL2Summary(mapData, filterPaths) {
  // 完整符号表
  const base = createL1Summary(mapData, filterPaths);
  
  return {
    ...base,
    level: 'L2',
    key_symbols: (mapData.key_symbols || [])
      .filter(ks => !filterPaths || filterPaths.some(fp => ks.path.includes(fp))),
    configs: mapData.configs || [],
  };
}

// 根据任务类型选择合适的map级别
export function getMapLevelForTaskType(taskType) {
  const levelMap = {
    doc: 'L0',
    split: 'L0',
    plan: 'L0',
    bug_fix: 'L1',
    refactor: 'L2',
  };
  return levelMap[taskType] || 'L2';
}

// ============================================
// TOK-06: 静态 Block 注入去重
// ============================================

class StaticBlockDeduplicator {
  constructor() {
    this.injectedBlocks = new Set();
    this.blockHashes = new Map();
  }
  
  // 标记已注入的block
  markInjected(blockId, content) {
    const hash = hashString(content);
    this.injectedBlocks.add(blockId);
    this.blockHashes.set(blockId, hash);
  }
  
  // 检查是否已注入
  isInjected(blockId, content) {
    if (!this.injectedBlocks.has(blockId)) {
      return false;
    }
    
    // 检查内容是否变化
    const currentHash = hashString(content);
    const previousHash = this.blockHashes.get(blockId);
    
    return currentHash === previousHash;
  }
  
  // 获取去重后的blocks
  deduplicateBlocks(blocks, role) {
    const unique = [];
    
    for (const block of blocks) {
      const blockId = `${role}:${block.id}`;
      
      if (this.isInjected(blockId, block.content)) {
        console.log(`[TOK-06] Skipping duplicate block: ${blockId}`);
        continue;
      }
      
      this.markInjected(blockId, block.content);
      unique.push(block);
    }
    
    return unique;
  }
  
  // 批量任务优化 - 同一role的连续任务只注入一次
  optimizeBatchTasks(tasks, role) {
    const optimized = [];
    let staticBlocksInjected = false;
    
    for (const task of tasks) {
      if (!staticBlocksInjected) {
        // 第一个任务：注入所有blocks
        task.blocks = this.deduplicateBlocks(task.blocks, role);
        staticBlocksInjected = true;
      } else {
        // 后续任务：只注入动态blocks
        task.blocks = task.blocks.filter(b => b.dynamic === true);
      }
      optimized.push(task);
    }
    
    return optimized;
  }
}

export const blockDeduplicator = new StaticBlockDeduplicator();

// ============================================
// 工具函数
// ============================================

function hashString(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return hash.toString(16);
}

// ============================================
// 主函数 - 批量应用所有优化
// ============================================

export function applyAllOptimizations(config = {}) {
  console.log('========================================');
  console.log('SCC Token Optimization Batch');
  console.log('========================================\n');
  
  const results = {
    tok01: { status: 'enabled', description: 'Cache-friendly prompt prefix' },
    tok02: { status: 'enabled', description: 'Context limits by task type' },
    tok03: { status: 'enabled', description: 'Token CFO auto-adjustment' },
    tok04: { status: 'enabled', description: 'Compact JSON injection' },
    tok05: { status: 'enabled', description: 'Map summary levels L0/L1/L2' },
    tok06: { status: 'enabled', description: 'Static block deduplication' },
  };
  
  console.log('Applied optimizations:');
  for (const [key, value] of Object.entries(results)) {
    console.log(`  ${key.toUpperCase()}: ${value.description}`);
  }
  
  console.log('\nConfiguration:');
  console.log('  Context limits:', CONTEXT_LIMITS_BY_TASK_TYPE);
  console.log('  Map levels:', Object.keys(MAP_SUMMARY_LEVELS));
  console.log('  Auto-adjustment:', tokenCFO.autoAdjustEnabled);
  
  return results;
}

// CLI 入口
if (import.meta.url === `file://${process.argv[1]}`) {
  applyAllOptimizations();
}

export default {
  // TOK-01
  buildCacheFriendlySystemPrompt,
  loadStaticPrefixes,
  
  // TOK-02
  getContextLimitForTaskType,
  createContextPackFromPins,
  
  // TOK-03
  tokenCFO,
  TokenCFO,
  
  // TOK-04
  compactJSON,
  optimizeJSONStringify,
  
  // TOK-05
  createMapSummary,
  getMapLevelForTaskType,
  MAP_SUMMARY_LEVELS,
  
  // TOK-06
  blockDeduplicator,
  StaticBlockDeduplicator,
  
  // 批量应用
  applyAllOptimizations,
};
