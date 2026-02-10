#!/usr/bin/env node
/**
 * SCC 文件索引系统
 * 基于17层架构的快速文件索引和搜索
 */

import fs from 'fs/promises';
import path from 'path';
import { createRequire } from 'module';

const require = createRequire(import.meta.url);

// 17层架构定义
const LAYERS = {
  L1: { name: 'code_layer', desc: '代码层', path: 'L1_code_layer' },
  L2: { name: 'task_layer', desc: '任务层', path: 'L2_task_layer' },
  L3: { name: 'documentation_layer', desc: '文档层', path: 'L3_documentation_layer' },
  L4: { name: 'prompt_layer', desc: '提示词层', path: 'L4_prompt_layer' },
  L5: { name: 'model_layer', desc: '模型层', path: 'L5_model_layer' },
  L6: { name: 'agent_layer', desc: 'Agent层', path: 'L6_agent_layer' },
  L7: { name: 'tool_layer', desc: '工具层', path: 'L7_tool_layer' },
  L8: { name: 'evidence_layer', desc: '证据层', path: 'L8_evidence_layer' },
  L9: { name: 'state_layer', desc: '状态层', path: 'L9_state_layer' },
  L10: { name: 'workflow_layer', desc: '工作流层', path: 'L10_workflow_layer' },
  L11: { name: 'routing_layer', desc: '路由层', path: 'L11_routing_layer' },
  L12: { name: 'collaboration_layer', desc: '协作层', path: 'L12_collaboration_layer' },
  L13: { name: 'security_layer', desc: '安全层', path: 'L13_security_layer' },
  L14: { name: 'quality_layer', desc: '质量层', path: 'L14_quality_layer' },
  L15: { name: 'change_layer', desc: '变更层', path: 'L15_change_layer' },
  L16: { name: 'observability_layer', desc: '观测层', path: 'L16_observability_layer' },
  L17: { name: 'ontology_layer', desc: '本体层', path: 'L17_ontology_layer' }
};

// 文件类型分类
const FILE_CATEGORIES = {
  gateway: ['gateway', 'router', 'server'],
  executor: ['executor', 'runner', 'worker'],
  orchestrator: ['orchestrator', 'scheduler', 'dispatcher'],
  state: ['state', 'store', 'board', 'jobs'],
  config: ['config', 'settings', 'env'],
  tool: ['tool', 'script', 'capability'],
  test: ['test', 'spec', 'verify'],
  doc: ['README', 'GUIDE', 'doc', 'md']
};

class FileIndexer {
  constructor(repoRoot) {
    this.repoRoot = repoRoot;
    this.index = {
      version: '1.0.0',
      created: new Date().toISOString(),
      layers: {},
      files: [],
      byType: {},
      byKeyword: {}
    };
  }

  async scan() {
    console.log('🔍 开始扫描文件...');
    
    for (const [layerId, layerInfo] of Object.entries(LAYERS)) {
      const layerPath = path.join(this.repoRoot, layerInfo.path);
      
      try {
        await this.scanLayer(layerId, layerInfo, layerPath);
      } catch (err) {
        // 层目录可能不存在，跳过
      }
    }
    
    // 扫描根目录文件
    await this.scanRoot();
    
    console.log(`✅ 扫描完成，共索引 ${this.index.files.length} 个文件`);
  }

  async scanLayer(layerId, layerInfo, layerPath) {
    const entries = await fs.readdir(layerPath, { withFileTypes: true });
    
    this.index.layers[layerId] = {
      ...layerInfo,
      modules: []
    };
    
    for (const entry of entries) {
      if (entry.isDirectory()) {
        const modulePath = path.join(layerPath, entry.name);
        await this.scanModule(layerId, entry.name, modulePath);
      }
    }
  }

  async scanModule(layerId, moduleName, modulePath) {
    this.index.layers[layerId].modules.push(moduleName);
    
    const files = await this.walkDir(modulePath);
    
    for (const file of files) {
      const relativePath = path.relative(this.repoRoot, file);
      const fileInfo = await this.analyzeFile(file, relativePath, layerId, moduleName);
      this.index.files.push(fileInfo);
      this.categorizeFile(fileInfo);
    }
  }

  async scanRoot() {
    const entries = await fs.readdir(this.repoRoot, { withFileTypes: true });
    
    for (const entry of entries) {
      if (entry.isFile()) {
        const filePath = path.join(this.repoRoot, entry.name);
        const fileInfo = await this.analyzeFile(filePath, entry.name, 'root', 'root');
        this.index.files.push(fileInfo);
        this.categorizeFile(fileInfo);
      }
    }
  }

  async walkDir(dir) {
    const files = [];
    
    try {
      const entries = await fs.readdir(dir, { withFileTypes: true, recursive: true });
      
      for (const entry of entries) {
        if (entry.isFile()) {
          files.push(path.join(dir, entry.name));
        }
      }
    } catch (err) {
      // 忽略错误
    }
    
    return files;
  }

  async analyzeFile(filePath, relativePath, layerId, moduleName) {
    const stats = await fs.stat(filePath);
    const ext = path.extname(filePath).toLowerCase();
    const basename = path.basename(filePath);
    
    // 提取关键词
    const keywords = this.extractKeywords(basename);
    
    return {
      path: relativePath,
      absolute: filePath,
      name: basename,
      ext: ext,
      layer: layerId,
      module: moduleName,
      size: stats.size,
      modified: stats.mtime.toISOString(),
      keywords: keywords,
      category: this.classifyFile(basename, keywords)
    };
  }

  extractKeywords(filename) {
    const keywords = [];
    const clean = filename
      .replace(/\.[a-zA-Z0-9]+$/, '')
      .replace(/[_-]/g, ' ')
      .toLowerCase();
    
    // 提取驼峰命名
    const camelWords = clean.match(/[a-z]+|[A-Z][a-z]*/g) || [];
    keywords.push(...camelWords.map(w => w.toLowerCase()));
    
    return [...new Set(keywords)];
  }

  classifyFile(filename, keywords) {
    for (const [category, patterns] of Object.entries(FILE_CATEGORIES)) {
      for (const pattern of patterns) {
        if (filename.toLowerCase().includes(pattern.toLowerCase())) {
          return category;
        }
      }
    }
    return 'other';
  }

  categorizeFile(fileInfo) {
    // 按类型分类
    if (!this.index.byType[fileInfo.ext]) {
      this.index.byType[fileInfo.ext] = [];
    }
    this.index.byType[fileInfo.ext].push(fileInfo.path);
    
    // 按关键词分类
    for (const keyword of fileInfo.keywords) {
      if (!this.index.byKeyword[keyword]) {
        this.index.byKeyword[keyword] = [];
      }
      this.index.byKeyword[keyword].push(fileInfo.path);
    }
  }

  search(query, options = {}) {
    const { layer, type, category } = options;
    const queryLower = query.toLowerCase();
    const results = [];
    
    for (const file of this.index.files) {
      // 层过滤
      if (layer && file.layer !== layer) continue;
      
      // 类型过滤
      if (type && file.ext !== type) continue;
      
      // 分类过滤
      if (category && file.category !== category) continue;
      
      // 搜索匹配
      const matchScore = this.calculateMatchScore(file, queryLower);
      if (matchScore > 0) {
        results.push({ ...file, score: matchScore });
      }
    }
    
    return results.sort((a, b) => b.score - a.score);
  }

  calculateMatchScore(file, query) {
    let score = 0;
    
    // 文件名匹配
    if (file.name.toLowerCase().includes(query)) {
      score += 10;
      if (file.name.toLowerCase().startsWith(query)) {
        score += 5;
      }
    }
    
    // 关键词匹配
    for (const keyword of file.keywords) {
      if (keyword.includes(query)) {
        score += 3;
      }
    }
    
    // 路径匹配
    if (file.path.toLowerCase().includes(query)) {
      score += 1;
    }
    
    return score;
  }

  async save(outputPath) {
    await fs.writeFile(outputPath, JSON.stringify(this.index, null, 2));
    console.log(`💾 索引已保存到: ${outputPath}`);
  }

  async load(indexPath) {
    const data = await fs.readFile(indexPath, 'utf-8');
    this.index = JSON.parse(data);
    console.log(`📂 已加载索引: ${indexPath}`);
  }

  printStats() {
    console.log('\n📊 索引统计:');
    console.log(`  总文件数: ${this.index.files.length}`);
    console.log(`  层数: ${Object.keys(this.index.layers).length}`);
    console.log(`  文件类型: ${Object.keys(this.index.byType).length}`);
    console.log(`  关键词: ${Object.keys(this.index.byKeyword).length}`);
    
    console.log('\n📁 各层文件分布:');
    for (const [layerId, layerInfo] of Object.entries(this.index.layers)) {
      const count = this.index.files.filter(f => f.layer === layerId).length;
      console.log(`  ${layerId}: ${count} 个文件`);
    }
  }
}

// CLI 接口
async function main() {
  const args = process.argv.slice(2);
  const command = args[0];
  
  const repoRoot = process.env.SCC_REPO || 'c:\\scc\\scc-bd';
  const indexPath = path.join(repoRoot, 'file_index.json');
  
  const indexer = new FileIndexer(repoRoot);
  
  switch (command) {
    case 'build':
      await indexer.scan();
      await indexer.save(indexPath);
      indexer.printStats();
      break;
      
    case 'search':
      const query = args[1];
      if (!query) {
        console.log('用法: node file_indexer.mjs search <关键词>');
        process.exit(1);
      }
      
      try {
        await indexer.load(indexPath);
        const results = indexer.search(query);
        
        console.log(`\n🔍 搜索 "${query}" 的结果 (${results.length} 个):\n`);
        
        for (let i = 0; i < Math.min(results.length, 20); i++) {
          const r = results[i];
          console.log(`  ${i + 1}. ${r.path}`);
          console.log(`     层: ${r.layer}, 模块: ${r.module}, 类型: ${r.category}`);
          console.log(`     匹配度: ${r.score}\n`);
        }
      } catch (err) {
        console.log('❌ 索引不存在，请先运行: node file_indexer.mjs build');
      }
      break;
      
    case 'layer':
      const layerId = args[1];
      if (!layerId) {
        console.log('用法: node file_indexer.mjs layer <层ID>');
        console.log('示例: node file_indexer.mjs layer L6');
        process.exit(1);
      }
      
      try {
        await indexer.load(indexPath);
        const results = indexer.search('', { layer: layerId });
        
        console.log(`\n📂 ${layerId} 层的文件 (${results.length} 个):\n`);
        
        for (const r of results) {
          console.log(`  - ${r.path} (${r.category})`);
        }
      } catch (err) {
        console.log('❌ 索引不存在，请先运行: node file_indexer.mjs build');
      }
      break;
      
    default:
      console.log('SCC 文件索引系统');
      console.log('');
      console.log('用法:');
      console.log('  node file_indexer.mjs build          构建索引');
      console.log('  node file_indexer.mjs search <词>    搜索文件');
      console.log('  node file_indexer.mjs layer <层>     查看层文件');
      console.log('');
      console.log('示例:');
      console.log('  node file_indexer.mjs build');
      console.log('  node file_indexer.mjs search parent_inbox');
      console.log('  node file_indexer.mjs search executor');
      console.log('  node file_indexer.mjs layer L6');
  }
}

main().catch(console.error);

export { FileIndexer, LAYERS };
