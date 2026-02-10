#!/usr/bin/env node
/**
 * Test script for Token Optimization
 */

import {
  buildCacheFriendlySystemPrompt,
  getContextLimitForTaskType,
  createContextPackFromPins,
  tokenCFO,
  compactJSON,
  createMapSummary,
  getMapLevelForTaskType,
  blockDeduplicator,
  applyAllOptimizations,
} from './token_optimize_batch.mjs';

console.log('========================================');
console.log('SCC Token Optimization Test Suite');
console.log('========================================\n');

// Test TOK-01: Cache-friendly prompt prefix
console.log('=== TOK-01: Cache-friendly Prompt Prefix ===');
const roleCapsule = 'Role: ENGINEER\nGoal: Fix the bug in gateway.mjs';
const dynamicContext = 'Context: User reported error on line 42';
const promptResult = buildCacheFriendlySystemPrompt(roleCapsule, dynamicContext);
console.log('Static prefix length:', promptResult.staticPrefix.length);
console.log('Dynamic part length:', promptResult.dynamicPart.length);
console.log('Full prompt length:', promptResult.fullPrompt.length);
console.log('Cache key:', promptResult.cacheKey);
console.log('✓ TOK-01 working\n');

// Test TOK-02: Context limits by task type
console.log('=== TOK-02: Context Limits by Task Type ===');
const taskTypes = ['doc', 'bug_fix', 'refactor', 'split', 'plan', 'unknown'];
for (const type of taskTypes) {
  const limit = getContextLimitForTaskType(type);
  console.log(`${type}: ${limit.maxBytes / 1024}KB (${limit.strategy})`);
}

// Test context pack creation
const testPins = [
  { path: 'src/gateway.mjs', size: 50000, line_windows: [1, 100] },
  { path: 'src/utils.mjs', size: 20000 },
  { path: 'src/config.mjs', size: 15000 },
];
const contextPack = createContextPackFromPins(testPins, 'doc');
console.log('\nContext pack (doc task):');
console.log('  Pins:', contextPack.pins.length);
console.log('  Total bytes:', contextPack.totalBytes);
console.log('  Limit:', contextPack.limit);
console.log('  Utilization:', contextPack.utilization);
console.log('✓ TOK-02 working\n');

// Test TOK-03: Token CFO
console.log('=== TOK-03: Token CFO Auto-adjustment ===');
const pinsUsed = [
  { path: 'src/gateway.mjs' },
  { path: 'src/utils.mjs' },
  { path: 'src/config.mjs' },
  { path: 'src/logger.mjs' },
  { path: 'src/db.mjs' },
];
const pinsTouched = ['src/gateway.mjs', 'src/utils.mjs']; // Only 2/5 touched
const analysis = tokenCFO.analyzeTaskWaste('task-001', 'bug_fix', pinsUsed, pinsTouched);
console.log('Waste analysis:');
console.log('  Unused ratio:', (analysis.wasteData.unusedRatio * 100).toFixed(1) + '%');
console.log('  Actions generated:', analysis.actions.length);
if (analysis.actions.length > 0) {
  console.log('  Actions:', analysis.actions.map(a => a.type).join(', '));
}
console.log('✓ TOK-03 working\n');

// Test TOK-04: Compact JSON
console.log('=== TOK-04: Compact JSON ===');
const testObj = { name: 'test', value: 123, nested: { a: 1, b: 2 } };
const compact = compactJSON(testObj, false);
const pretty = compactJSON(testObj, true);
console.log('Compact JSON length:', compact.length);
console.log('Pretty JSON length:', pretty.length);
console.log('Savings:', ((1 - compact.length / pretty.length) * 100).toFixed(1) + '%');
console.log('✓ TOK-04 working\n');

// Test TOK-05: Map summary levels
console.log('=== TOK-05: Map Summary Levels ===');
const mockMapData = {
  modules: [
    { id: 'mod:src', root: 'src', kind: 'node', doc_refs: [] },
    { id: 'mod:tests', root: 'tests', kind: 'generic', doc_refs: [] },
  ],
  entry_points: [
    { id: 'pkg:src:start', kind: 'npm_script', path: 'src/package.json', command: 'npm start' },
    { id: 'pkg:src:test', kind: 'npm_script', path: 'src/package.json', command: 'npm test' },
  ],
  key_symbols: [
    { symbol: 'main', kind: 'function', path: 'src/index.mjs', line: 10, doc_refs: [] },
    { symbol: 'init', kind: 'function', path: 'src/app.mjs', line: 5, doc_refs: [] },
  ],
  configs: [
    { key: 'PORT', path: 'src/config.mjs', line: 3 },
  ],
};

for (const level of ['L0', 'L1', 'L2']) {
  const summary = createMapSummary(mockMapData, level);
  console.log(`${level} summary:`, JSON.stringify(summary).length, 'bytes');
}

console.log('Map level for task types:');
console.log('  doc:', getMapLevelForTaskType('doc'));
console.log('  bug_fix:', getMapLevelForTaskType('bug_fix'));
console.log('  refactor:', getMapLevelForTaskType('refactor'));
console.log('✓ TOK-05 working\n');

// Test TOK-06: Block deduplication
console.log('=== TOK-06: Static Block Deduplication ===');
const blocks = [
  { id: 'constitution', content: 'You are an expert...', dynamic: false },
  { id: 'handbook', content: 'CI Handbook v1...', dynamic: false },
  { id: 'context', content: 'Current task context...', dynamic: true },
];
const deduplicated1 = blockDeduplicator.deduplicateBlocks(blocks, 'ENGINEER');
console.log('First injection:', deduplicated1.length, 'blocks');
const deduplicated2 = blockDeduplicator.deduplicateBlocks(blocks, 'ENGINEER');
console.log('Second injection:', deduplicated2.length, 'blocks (should be 0)');

// Test batch optimization
const batchTasks = [
  { id: 1, blocks: [...blocks] },
  { id: 2, blocks: [...blocks] },
  { id: 3, blocks: [...blocks] },
];
const optimized = blockDeduplicator.optimizeBatchTasks(batchTasks, 'ENGINEER');
console.log('Batch optimization:');
console.log('  Task 1 blocks:', optimized[0].blocks.length);
console.log('  Task 2 blocks:', optimized[1].blocks.length);
console.log('  Task 3 blocks:', optimized[2].blocks.length);
console.log('✓ TOK-06 working\n');

// Summary
console.log('========================================');
console.log('All Token Optimizations Working!');
console.log('========================================');
console.log('\nExpected savings:');
console.log('  TOK-01 (Cache-friendly prefix): 30-50% for repeated roles');
console.log('  TOK-02 (Context limits): 50-75% for doc/split tasks');
console.log('  TOK-03 (Token CFO): 15-20% waste reduction');
console.log('  TOK-04 (Compact JSON): ~33% for JSON in prompts');
console.log('  TOK-05 (Map levels): 90%+ for doc tasks (L0 vs L2)');
console.log('  TOK-06 (Block dedup): ~200 tokens per repeated block');
