#!/usr/bin/env node
/**
 * 创建元 Skills - 动态加载和自迭代技能
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const SKILLS_DIR = path.join(REPO_ROOT, 'L4_prompt_layer', 'skills');
const REGISTRY_FILE = path.join(SKILLS_DIR, 'registry.json');
const MATRIX_FILE = path.join(REPO_ROOT, 'L4_prompt_layer', 'roles', 'role_skill_matrix.json');

// 元 Skills 定义
const META_SKILLS = [
  // 动态加载 Skills
  {
    id: 'meta.dynamic_loader',
    name: '动态技能加载器',
    summary: '运行时动态发现和加载 skills，支持热更新和按需加载',
    description: `
## 功能
- 运行时扫描 skills 目录
- 按需加载技能到内存
- 支持技能热更新
- 技能版本管理
- 依赖解析和加载

## 使用场景
- 大型 skills 库的性能优化
- 插件化架构
- 技能市场动态安装
    `,
    capabilities: [
      'scan_skills_directory',
      'load_skill_on_demand',
      'hot_reload_skill',
      'resolve_dependencies',
      'cache_skill_definitions'
    ]
  },
  {
    id: 'meta.lazy_loader',
    name: '延迟加载器',
    summary: '智能延迟加载 skills，仅在需要时加载，优化启动性能',
    description: `
## 功能
- 智能预测技能使用
- 按需加载策略
- 内存管理
- 加载优先级队列
- 预加载热门技能

## 使用场景
- 启动性能优化
- 内存受限环境
- 大型 skills 库
    `,
    capabilities: [
      'predict_skill_usage',
      'lazy_load_skill',
      'manage_memory_pool',
      'priority_load_queue',
      'preload_hot_skills'
    ]
  },
  {
    id: 'meta.remote_loader',
    name: '远程技能加载器',
    summary: '从远程源（GitHub、CDN、Registry）动态加载 skills',
    description: `
## 功能
- 从 GitHub 加载 skills
- CDN 加速加载
- Registry 查询和下载
- 版本控制和回滚
- 离线缓存管理

## 使用场景
- 技能市场
- 分布式 skills 库
- 团队协作
    `,
    capabilities: [
      'fetch_from_github',
      'fetch_from_cdn',
      'query_registry',
      'version_control',
      'offline_cache'
    ]
  },

  // 自迭代 Skills
  {
    id: 'meta.self_improve',
    name: '技能自改进',
    summary: '分析技能使用效果并自动优化技能定义',
    description: `
## 功能
- 收集技能使用指标
- 分析成功/失败率
- 自动调整参数
- A/B 测试技能变体
- 生成改进建议

## 使用场景
- 技能性能优化
- 持续改进
- 自适应系统
    `,
    capabilities: [
      'collect_metrics',
      'analyze_performance',
      'auto_tune_params',
      'ab_test_variants',
      'generate_suggestions'
    ]
  },
  {
    id: 'meta.skill_evolution',
    name: '技能进化',
    summary: '基于使用模式自动进化技能，创建新版本',
    description: `
## 功能
- 检测使用模式
- 生成技能变体
- 自然选择最优版本
- 版本血统追踪
- 回滚机制

## 使用场景
- 长期运行的系统
- 自适应技能库
- 进化算法
    `,
    capabilities: [
      'detect_patterns',
      'generate_variants',
      'natural_selection',
      'track_lineage',
      'rollback_version'
    ]
  },
  {
    id: 'meta.auto_generate',
    name: '技能自动生成',
    summary: '基于需求自动生成新的 skills',
    description: `
## 功能
- 分析任务需求
- 生成技能定义
- 创建技能模板
- 验证技能有效性
- 发布到 registry

## 使用场景
- 快速原型开发
- 技能市场扩展
- 自动化工具
    `,
    capabilities: [
      'analyze_requirements',
      'generate_skill_def',
      'create_templates',
      'validate_skill',
      'publish_to_registry'
    ]
  },
  {
    id: 'meta.skill_composition',
    name: '技能组合器',
    summary: '自动发现和创建技能组合，解决复杂问题',
    description: `
## 功能
- 分析复杂任务
- 发现技能组合
- 优化执行顺序
- 处理依赖关系
- 生成工作流

## 使用场景
- 复杂任务分解
- 工作流自动化
- 智能编排
    `,
    capabilities: [
      'decompose_task',
      'discover_combinations',
      'optimize_sequence',
      'resolve_deps',
      'generate_workflow'
    ]
  },

  // 智能管理 Skills
  {
    id: 'meta.skill_recommender',
    name: '技能推荐器',
    summary: '基于上下文智能推荐相关 skills',
    description: `
## 功能
- 分析当前上下文
- 匹配相关技能
- 学习用户偏好
- 个性化推荐
- 协同过滤

## 使用场景
- 智能助手
- 代码补全
- 任务建议
    `,
    capabilities: [
      'analyze_context',
      'match_skills',
      'learn_preferences',
      'personalize',
      'collaborative_filter'
    ]
  },
  {
    id: 'meta.skill_optimizer',
    name: '技能优化器',
    summary: '全局优化技能库性能和效果',
    description: `
## 功能
- 分析技能使用频率
- 识别冗余技能
- 合并相似技能
- 优化加载顺序
- 压缩技能定义

## 使用场景
- 性能优化
- 库维护
- 资源管理
    `,
    capabilities: [
      'analyze_frequency',
      'detect_redundancy',
      'merge_similar',
      'optimize_load_order',
      'compress_defs'
    ]
  },
  {
    id: 'meta.skill_validator',
    name: '技能验证器',
    summary: '自动验证 skills 的正确性和安全性',
    description: `
## 功能
- 验证 JSON Schema
- 检查依赖完整性
- 安全扫描
- 性能测试
- 兼容性检查

## 使用场景
- CI/CD 流程
- 技能市场审核
- 质量保证
    `,
    capabilities: [
      'validate_schema',
      'check_dependencies',
      'security_scan',
      'performance_test',
      'compatibility_check'
    ]
  },

  // 高级功能 Skills
  {
    id: 'meta.skill_marketplace',
    name: '技能市场',
    summary: '管理和分发 skills 的完整市场功能',
    description: `
## 功能
- 技能发布和订阅
- 版本管理
- 评分和评论
- 搜索和发现
- 支付和授权

## 使用场景
- 商业 skills 平台
- 团队协作
- 开源社区
    `,
    capabilities: [
      'publish_skill',
      'subscribe_skill',
      'version_management',
      'rate_and_review',
      'search_discover'
    ]
  },
  {
    id: 'meta.distributed_skills',
    name: '分布式技能库',
    summary: '支持分布式 skills 存储和同步',
    description: `
## 功能
- 分布式存储
- 实时同步
- 冲突解决
- 离线优先
- 边缘缓存

## 使用场景
- 团队协作
- 边缘计算
- 高可用系统
    `,
    capabilities: [
      'distributed_storage',
      'realtime_sync',
      'conflict_resolution',
      'offline_first',
      'edge_caching'
    ]
  },
  {
    id: 'meta.skill_analytics',
    name: '技能分析',
    summary: '全面的 skills 使用分析和洞察',
    description: `
## 功能
- 使用统计
- 性能分析
- 趋势预测
- 异常检测
- 报告生成

## 使用场景
- 系统监控
- 决策支持
- 优化指导
    `,
    capabilities: [
      'usage_stats',
      'performance_analysis',
      'trend_prediction',
      'anomaly_detection',
      'report_generation'
    ]
  }
];

// 创建元 Skill 定义
function createMetaSkill(skillInfo) {
  return {
    schema_version: "scc.skill.v1",
    skill_id: skillInfo.id,
    version: "1.0.0",
    owner_role: "workbench_dev",
    summary: skillInfo.summary,
    description: skillInfo.description.trim(),
    applies_to: {
      task_class: ["*"],
      tags: ["meta", "dynamic", "self-improving", "advanced"]
    },
    contracts: {
      input_schema: "contracts/child_task/child_task.schema.json",
      output_schema: "contracts/submit/submit.schema.json"
    },
    budgets: {
      max_loc: 3000,
      max_files: 50
    },
    quality_gates: {
      must_run_allowedTests: true,
      must_keep_diff_minimal: false
    },
    enablement: {
      status: "active",
      rollout: { mode: "all", percent: 100 }
    },
    capabilities: skillInfo.capabilities,
    metadata: {
      category: "meta",
      subcategory: skillInfo.id.split('.')[1],
      display_name: skillInfo.name,
      tags: ["meta", "dynamic", "self-improving", "advanced", "core"],
      complexity: "advanced",
      created_at: new Date().toISOString(),
      source: "scc_meta_library",
      is_meta_skill: true
    }
  };
}

// 保存 skill
function saveSkill(skillId, skillData) {
  const skillDir = path.join(SKILLS_DIR, skillId);
  const skillFile = path.join(skillDir, 'skill.json');
  
  if (!fs.existsSync(skillDir)) {
    fs.mkdirSync(skillDir, { recursive: true });
  }
  
  fs.writeFileSync(skillFile, JSON.stringify(skillData, null, 2) + '\n', 'utf8');
  return { dir: skillDir, file: skillFile };
}

// 更新 registry
function updateRegistry(newSkills) {
  let registry = {
    schema_version: "scc.skills_registry.v1",
    updated_at: new Date().toISOString().split('T')[0],
    skills: []
  };
  
  if (fs.existsSync(REGISTRY_FILE)) {
    try {
      registry = JSON.parse(fs.readFileSync(REGISTRY_FILE, 'utf8'));
    } catch (e) {
      console.warn('Warning: Could not parse existing registry');
    }
  }
  
  for (const skill of newSkills) {
    const exists = registry.skills.some(s => s.skill_id === skill.skill_id);
    if (!exists) {
      registry.skills.push({
        skill_id: skill.skill_id,
        version: skill.version,
        owner_role: skill.owner_role,
        path: `skills/${skill.skill_id}/skill.json`,
        status: "active"
      });
    }
  }
  
  registry.updated_at = new Date().toISOString().split('T')[0];
  fs.writeFileSync(REGISTRY_FILE, JSON.stringify(registry, null, 2) + '\n', 'utf8');
  
  return registry.skills.length;
}

// 更新 matrix
function updateMatrix(newSkills) {
  let matrix = {
    schema_version: "scc.role_skill_matrix.v1",
    updated_at: new Date().toISOString().split('T')[0],
    roles: {}
  };
  
  if (fs.existsSync(MATRIX_FILE)) {
    try {
      matrix = JSON.parse(fs.readFileSync(MATRIX_FILE, 'utf8'));
    } catch (e) {
      console.warn('Warning: Could not parse existing matrix');
    }
  }
  
  if (!matrix.roles.workbench_dev) {
    matrix.roles.workbench_dev = [];
  }
  
  const existingSkills = new Set(matrix.roles.workbench_dev);
  for (const skill of newSkills) {
    if (!existingSkills.has(skill.skill_id)) {
      matrix.roles.workbench_dev.push(skill.skill_id);
    }
  }
  
  matrix.updated_at = new Date().toISOString().split('T')[0];
  fs.writeFileSync(MATRIX_FILE, JSON.stringify(matrix, null, 2) + '\n', 'utf8');
  
  return matrix.roles.workbench_dev.length;
}

// 主函数
async function main() {
  console.log('='.repeat(80));
  console.log('SCC 元 Skills 创建工具');
  console.log('='.repeat(80));
  console.log();
  
  const allSkills = [];
  
  console.log('创建元 Skills...');
  console.log();
  
  for (const skillInfo of META_SKILLS) {
    const skillData = createMetaSkill(skillInfo);
    allSkills.push(skillData);
    console.log(`  ✓ ${skillData.skill_id} - ${skillInfo.name}`);
  }
  
  console.log();
  console.log(`✓ 创建了 ${allSkills.length} 个元 Skills`);
  console.log();
  
  // 保存 skills
  console.log('='.repeat(80));
  console.log('保存元 Skills');
  console.log('='.repeat(80));
  
  let savedCount = 0;
  for (const skill of allSkills) {
    try {
      saveSkill(skill.skill_id, skill);
      savedCount++;
      console.log(`  ✓ ${skill.skill_id}`);
    } catch (error) {
      console.error(`  ✗ 保存失败 ${skill.skill_id}: ${error.message}`);
    }
  }
  
  console.log();
  console.log(`✓ 已保存 ${savedCount} 个元 skills`);
  console.log();
  
  // 更新 registry
  console.log('='.repeat(80));
  console.log('更新 Registry');
  console.log('='.repeat(80));
  
  const totalRegistrySkills = updateRegistry(allSkills);
  console.log(`✓ Registry 现在共有 ${totalRegistrySkills} 个 skills`);
  console.log();
  
  // 更新 matrix
  console.log('='.repeat(80));
  console.log('更新 Role Skill Matrix');
  console.log('='.repeat(80));
  
  const totalMatrixSkills = updateMatrix(allSkills);
  console.log(`✓ workbench_dev 角色现在有 ${totalMatrixSkills} 个 skills`);
  console.log();
  
  // 分类统计
  console.log('='.repeat(80));
  console.log('元 Skills 分类');
  console.log('='.repeat(80));
  
  const dynamicSkills = allSkills.filter(s => s.skill_id.includes('loader'));
  const selfImproveSkills = allSkills.filter(s => 
    s.skill_id.includes('self') || s.skill_id.includes('evolution') || 
    s.skill_id.includes('auto') || s.skill_id.includes('composition')
  );
  const managementSkills = allSkills.filter(s => 
    s.skill_id.includes('recommender') || s.skill_id.includes('optimizer') || 
    s.skill_id.includes('validator')
  );
  const advancedSkills = allSkills.filter(s => 
    s.skill_id.includes('marketplace') || s.skill_id.includes('distributed') || 
    s.skill_id.includes('analytics')
  );
  
  console.log(`动态加载: ${dynamicSkills.length} skills`);
  console.log(`  - ${dynamicSkills.map(s => s.skill_id).join(', ')}`);
  console.log();
  console.log(`自迭代: ${selfImproveSkills.length} skills`);
  console.log(`  - ${selfImproveSkills.map(s => s.skill_id).join(', ')}`);
  console.log();
  console.log(`智能管理: ${managementSkills.length} skills`);
  console.log(`  - ${managementSkills.map(s => s.skill_id).join(', ')}`);
  console.log();
  console.log(`高级功能: ${advancedSkills.length} skills`);
  console.log(`  - ${advancedSkills.map(s => s.skill_id).join(', ')}`);
  
  console.log();
  console.log('='.repeat(80));
  console.log('元 Skills 创建完成!');
  console.log('='.repeat(80));
  console.log();
  console.log('这些元 skills 提供了:');
  console.log('  ✓ 动态加载 - 运行时按需加载 skills');
  console.log('  ✓ 延迟加载 - 智能延迟加载优化性能');
  console.log('  ✓ 远程加载 - 从远程源获取 skills');
  console.log('  ✓ 自改进 - 自动优化技能效果');
  console.log('  ✓ 技能进化 - 基于使用模式进化技能');
  console.log('  ✓ 自动生成 - 基于需求生成新 skills');
  console.log('  ✓ 技能组合 - 自动发现和创建技能组合');
  console.log('  ✓ 智能推荐 - 上下文感知的技能推荐');
  console.log('  ✓ 全局优化 - 技能库性能优化');
  console.log('  ✓ 自动验证 - 技能和安全性验证');
  console.log('  ✓ 技能市场 - 完整的技能市场功能');
  console.log('  ✓ 分布式库 - 分布式 skills 存储同步');
  console.log('  ✓ 全面分析 - skills 使用分析和洞察');
}

main().catch(console.error);
