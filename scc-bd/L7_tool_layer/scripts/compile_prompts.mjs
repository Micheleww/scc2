#!/usr/bin/env node
/**
 * SCC Prompt Compiler
 * 
 * 将源文档编译为运行时提示词片段
 * 输入: docs/prompt_os/ 下的源文档
 * 输出: docs/prompt_os/compiler/ 下的编译产物
 * 
 * @version v1.0.0
 * @author architect
 */

import fs from 'fs/promises';
import path from 'path';
import crypto from 'crypto';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT_DIR = path.resolve(__dirname, '../..');
const SOURCE_DIR = path.join(ROOT_DIR, 'docs/prompt_os');
const OUTPUT_DIR = path.join(SOURCE_DIR, 'compiler');

// 配置
const CONFIG = {
  version: 'v1.0.0',
  maxLegalPrefixLines: 50,
  maxRefs: 100,
  hashAlgorithm: 'sha256'
};

/**
 * 主函数
 */
async function main() {
  console.log('🚀 SCC Prompt Compiler v' + CONFIG.version);
  console.log('');

  try {
    // 确保输出目录存在
    await fs.mkdir(OUTPUT_DIR, { recursive: true });

    // 编译各个产物
    await compileLegalPrefix();
    await compileRefsIndex();
    await compileIODigest();
    await compileToolDigest();
    await compileFailDigest();

    console.log('');
    console.log('✅ 编译完成！');
    console.log('📁 输出目录: ' + OUTPUT_DIR);

  } catch (error) {
    console.error('❌ 编译失败:', error.message);
    process.exit(1);
  }
}

/**
 * 编译 Legal Prefix
 * 提取 Constitution、Hard Policies、Conflict Order 的核心内容
 */
async function compileLegalPrefix() {
  console.log('📄 编译 Legal Prefix...');

  const constitution = await readDoc('constitution.md');
  const hardPolicies = await readDoc('policies/hard.md');
  const conflictOrder = await readDoc('conflict_order.md');

  const legalPrefix = `# SCC Legal Prefix ${CONFIG.version}
# 效力声明 - 必须遵守

## 存在性声明
以下引用文档为权威条款，具有约束力：
${extractRefs(constitution, hardPolicies, conflictOrder)}

## 优先级声明（冲突时按此顺序）
${extractPriorityOrder(conflictOrder)}

## 违规后果
${extractConsequences(constitution, hardPolicies)}

## 核心原则（必须遵守）
${extractCorePrinciples(constitution)}

## 输出要求
${extractOutputRequirements(constitution)}

## 引用索引
完整引用列表见: refs_index_${CONFIG.version.replace(/\./g, '_')}.json
`;

  const outputPath = path.join(OUTPUT_DIR, `legal_prefix_${CONFIG.version.replace(/\./g, '_')}.txt`);
  await fs.writeFile(outputPath, legalPrefix, 'utf-8');
  
  const hash = computeHash(legalPrefix);
  console.log(`   ✓ ${outputPath.replace(ROOT_DIR + '/', '')}`);
  console.log(`   哈希: ${hash.substring(0, 16)}...`);
}

/**
 * 编译引用索引
 */
async function compileRefsIndex() {
  console.log('📚 编译 References Index...');

  const refs = [];
  
  // 扫描所有源文档
  const sourceFiles = await scanSourceFiles();
  
  for (const file of sourceFiles) {
    const content = await readDoc(file);
    const metadata = extractMetadata(content, file);
    
    refs.push({
      id: metadata.id || path.basename(file, path.extname(file)),
      path: file,
      version: metadata.version || CONFIG.version,
      hash: computeHash(content),
      scope: metadata.scope || ['*'],
      priority: metadata.priority || 'L6',
      always_include: metadata.always_include || false,
      description: metadata.description || ''
    });
  }

  const refsIndex = {
    $schema: 'http://json-schema.org/draft-07/schema#',
    schema_version: `scc.refs_index.${CONFIG.version}`,
    updated_at: new Date().toISOString(),
    description: 'SCC 权威引用索引',
    refs: refs,
    metadata: {
      total_refs: refs.length,
      always_on_count: refs.filter(r => r.always_include).length,
      conditional_count: refs.filter(r => !r.always_include).length,
      compiler_version: CONFIG.version
    }
  };

  const outputPath = path.join(OUTPUT_DIR, `refs_index_${CONFIG.version.replace(/\./g, '_')}.json`);
  await fs.writeFile(outputPath, JSON.stringify(refsIndex, null, 2), 'utf-8');
  
  console.log(`   ✓ ${outputPath.replace(ROOT_DIR + '/', '')}`);
  console.log(`   引用数: ${refs.length}`);
}

/**
 * 编译 IO Digest
 */
async function compileIODigest() {
  console.log('📥 编译 IO Digest...');

  const schemas = await readDoc('io/schemas.md');
  const failCodes = await readDoc('io/fail_codes.md');
  const evidenceSpec = await readDoc('io/evidence_spec.md');

  const ioDigest = `# SCC IO Digest ${CONFIG.version}
# 输入输出规范摘要

## 输入格式
${extractInputFormat(schemas)}

## 输出格式
${extractOutputFormat(schemas)}

## 错误码速查
${extractFailCodesQuickRef(failCodes)}

## 证据要求
${extractEvidenceRequirements(evidenceSpec)}

## 完整规范
- schemas.md: 完整Schema定义
- fail_codes.md: 错误码详细说明
- evidence_spec.md: 证据规范
`;

  const outputPath = path.join(OUTPUT_DIR, `io_digest_${CONFIG.version.replace(/\./g, '_')}.txt`);
  await fs.writeFile(outputPath, ioDigest, 'utf-8');
  
  console.log(`   ✓ ${outputPath.replace(ROOT_DIR + '/', '')}`);
}

/**
 * 编译 Tool Digest
 */
async function compileToolDigest() {
  console.log('🛠️  编译 Tool Digest...');

  const toolCatalog = await readDoc('../L7_tool/catalog.md');

  const toolDigest = `# SCC Tool Digest ${CONFIG.version}
# 工具使用摘要

## 允许工具
${extractAllowedTools(toolCatalog)}

## 禁止工具
${extractForbiddenTools(toolCatalog)}

## 工具成本
${extractToolCosts(toolCatalog)}

## 触发条件
${extractToolTriggers(toolCatalog)}

## 完整目录
见: docs/L7_tool/catalog.md
`;

  const outputPath = path.join(OUTPUT_DIR, `tool_digest_${CONFIG.version.replace(/\./g, '_')}.txt`);
  await fs.writeFile(outputPath, toolDigest, 'utf-8');
  
  console.log(`   ✓ ${outputPath.replace(ROOT_DIR + '/', '')}`);
}

/**
 * 编译 Fail Digest
 */
async function compileFailDigest() {
  console.log('⚠️  编译 Fail Digest...');

  const failCodes = await readDoc('io/fail_codes.md');

  const failDigest = `# SCC Fail Digest ${CONFIG.version}
# 错误码与处理摘要

## 致命错误（不可重试）
${extractFatalErrors(failCodes)}

## 可重试错误
${extractRetryableErrors(failCodes)}

## 需要审查
${extractReviewRequiredErrors(failCodes)}

## 升级路径
${extractEscalationPaths(failCodes)}

## 完整错误码
见: docs/prompt_os/io/fail_codes.md
`;

  const outputPath = path.join(OUTPUT_DIR, `fail_digest_${CONFIG.version.replace(/\./g, '_')}.txt`);
  await fs.writeFile(outputPath, failDigest, 'utf-8');
  
  console.log(`   ✓ ${outputPath.replace(ROOT_DIR + '/', '')}`);
}

// ==================== 辅助函数 ====================

/**
 * 读取文档
 */
async function readDoc(relativePath) {
  try {
    const fullPath = path.join(SOURCE_DIR, relativePath);
    return await fs.readFile(fullPath, 'utf-8');
  } catch (error) {
    console.warn(`   ⚠️  无法读取 ${relativePath}: ${error.message}`);
    return '';
  }
}

/**
 * 扫描源文件
 */
async function scanSourceFiles() {
  const files = [];
  
  async function scanDir(dir, basePath = '') {
    const entries = await fs.readdir(dir, { withFileTypes: true });
    
    for (const entry of entries) {
      const relativePath = path.join(basePath, entry.name);
      const fullPath = path.join(dir, entry.name);
      
      if (entry.isDirectory() && entry.name !== 'compiler') {
        await scanDir(fullPath, relativePath);
      } else if (entry.isFile() && (entry.name.endsWith('.md') || entry.name.endsWith('.json'))) {
        files.push(relativePath);
      }
    }
  }
  
  await scanDir(SOURCE_DIR);
  return files;
}

/**
 * 计算哈希
 */
function computeHash(content) {
  return crypto.createHash(CONFIG.hashAlgorithm).update(content).digest('hex');
}

/**
 * 提取元数据（简化版）
 */
function extractMetadata(content, filePath) {
  const metadata = {};
  
  // 从文件内容提取版本
  const versionMatch = content.match(/version[:\s]+(v[\d.]+)/i);
  if (versionMatch) metadata.version = versionMatch[1];
  
  // 从文件内容提取优先级
  const priorityMatch = content.match(/priority[:\s]+(L\d)/i);
  if (priorityMatch) metadata.priority = priorityMatch[1];
  
  // 从文件路径推断ID
  metadata.id = path.basename(filePath, path.extname(filePath));
  
  // Constitution 和 Hard Policies 总是包含
  if (filePath.includes('constitution') || filePath.includes('hard.md')) {
    metadata.always_include = true;
    metadata.priority = filePath.includes('constitution') ? 'L0' : 'L1';
  }
  
  return metadata;
}

// ==================== 内容提取函数（简化版） ====================

function extractRefs(...docs) {
  return docs.map(doc => {
    const lines = doc.split('\n').slice(0, 5);
    return lines.filter(l => l.includes('.md') || l.includes('.json')).join('\n# ');
  }).filter(Boolean).join('\n# ');
}

function extractPriorityOrder(conflictOrder) {
  const match = conflictOrder.match(/L0.*L1.*L2.*L3.*L4.*L5/s);
  return match ? match[0].substring(0, 200) : '见 conflict_order.md';
}

function extractConsequences(constitution, hardPolicies) {
  return `
- 违反 L0-L1: 任务立即失败，记录安全事件
- 违反 L2: 操作被拒绝，可能角色降级
- 违反 L3: 任务重试或升级
- 违反 L4: 触发熔断或降级
- 违反 L5: 记录，无惩罚`;
}

function extractCorePrinciples(constitution) {
  const principles = constitution.match(/## 原则[\s\S]*?(?=##|$)/g);
  if (principles) {
    return principles[0].split('\n').filter(l => l.startsWith('1.') || l.startsWith('2.')).slice(0, 5).join('\n');
  }
  return `1. PINS-FIRST: 必须 pins-first
2. FAIL-CLOSED: 不确定时关闭
3. EVIDENCE-BASED: 必须有证据
4. VERSIONED-REFS: 引用带版本
5. MINIMAL-CONTEXT: 最小上下文`;
}

function extractOutputRequirements(constitution) {
  return `
- 必须输出 submit.json 符合 schema
- 必须提供证据（路径/行号/内容）
- 不确定时输出 NEEDS_REVIEW
- 失败时必须指明 fail_code`;
}

function extractInputFormat(schemas) {
  return `见 schemas.md - Task Input Schema`;
}

function extractOutputFormat(schemas) {
  return `见 schemas.md - Task Output Schema`;
}

function extractFailCodesQuickRef(failCodes) {
  return `见 fail_codes.md - 完整错误码列表`;
}

function extractEvidenceRequirements(evidenceSpec) {
  return `见 evidence_spec.md - 证据规范`;
}

function extractAllowedTools(toolCatalog) {
  return `read_file, write_file, run_lint, run_test, git_diff`;
}

function extractForbiddenTools(toolCatalog) {
  return `shell_exec, network_request, delete_file, modify_config`;
}

function extractToolCosts(toolCatalog) {
  return `read_file: ~10 tokens, run_lint: ~100 tokens, run_test: ~500+ tokens`;
}

function extractToolTriggers(toolCatalog) {
  return `根据任务阶段和角色自动触发`;
}

function extractFatalErrors(failCodes) {
  return `UNAUTHORIZED_SSOT_ACCESS, UNAUTHORIZED_SECRET_ACCESS, GATE_BYPASS_ATTEMPT`;
}

function extractRetryableErrors(failCodes) {
  return `PINS_INSUFFICIENT, EXECUTOR_ERROR, CI_FAILED`;
}

function extractReviewRequiredErrors(failCodes) {
  return `SCOPE_UNCLEAR, DESIGN_UNCERTAINTY`;
}

function extractEscalationPaths(failCodes) {
  return `自动重试 -> 角色升级 -> 人工介入`;
}

// 运行
main();
