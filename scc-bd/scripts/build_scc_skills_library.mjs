#!/usr/bin/env node
/**
 * 建立 SCC 专属 Skills 库
 * 
 * 设计原则：
 * 1. 分层架构：L1-L14 每层都有对应的 skills
 * 2. 角色对齐：skills 与 SCC 角色系统对齐
 * 3. 可组合：skills 可以组合使用
 * 4. 可扩展：易于添加新的 skills
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const SKILLS_DIR = path.join(REPO_ROOT, 'L4_prompt_layer', 'skills');
const REGISTRY_FILE = path.join(SKILLS_DIR, 'registry.json');
const MATRIX_FILE = path.join(REPO_ROOT, 'L4_prompt_layer', 'roles', 'role_skill_matrix.json');

// SCC 专属 Skills 分类体系
const SCC_SKILL_CATEGORIES = {
  // L1: 代码层 Skills
  'scc.l1_code': {
    description: 'L1 代码层相关技能',
    skills: [
      { id: 'code.reading', name: '代码阅读', summary: '快速理解和分析代码结构和逻辑' },
      { id: 'code.refactoring', name: '代码重构', summary: '安全地重构代码，保持行为不变' },
      { id: 'code.optimization', name: '代码优化', summary: '优化代码性能和可读性' },
      { id: 'code.review', name: '代码审查', summary: '系统性代码审查，发现潜在问题' },
      { id: 'code.documentation', name: '代码文档', summary: '生成和维护代码文档' },
      { id: 'code.testing', name: '代码测试', summary: '编写单元测试和集成测试' },
      { id: 'code.debugging', name: '代码调试', summary: '系统性调试和故障排除' },
      { id: 'code.patterns', name: '设计模式', summary: '应用设计模式解决常见问题' },
    ]
  },

  // L2: 工具链层 Skills
  'scc.l2_toolchain': {
    description: 'L2 工具链层相关技能',
    skills: [
      { id: 'toolchain.build', name: '构建系统', summary: '配置和优化构建系统' },
      { id: 'toolchain.ci', name: 'CI/CD', summary: '设置和维护持续集成/部署' },
      { id: 'toolchain.lint', name: '代码检查', summary: '配置代码检查工具' },
      { id: 'toolchain.test', name: '测试框架', summary: '配置测试框架和覆盖率' },
      { id: 'toolchain.package', name: '包管理', summary: '管理依赖和包版本' },
      { id: 'toolchain.container', name: '容器化', summary: 'Docker 和容器编排' },
    ]
  },

  // L3: 框架层 Skills
  'scc.l3_framework': {
    description: 'L3 框架层相关技能',
    skills: [
      { id: 'framework.frontend', name: '前端框架', summary: 'React, Vue, Angular 等前端框架' },
      { id: 'framework.backend', name: '后端框架', summary: 'Express, Django, Spring 等后端框架' },
      { id: 'framework.fullstack', name: '全栈框架', summary: 'Next.js, Nuxt 等全栈框架' },
      { id: 'framework.mobile', name: '移动框架', summary: 'React Native, Flutter 等移动框架' },
      { id: 'framework.desktop', name: '桌面框架', summary: 'Electron, Tauri 等桌面框架' },
    ]
  },

  // L4: 提示词层 Skills (核心)
  'scc.l4_prompt': {
    description: 'L4 提示词层核心技能',
    skills: [
      { id: 'prompt.engineering', name: '提示工程', summary: '编写高效的 LLM 提示词' },
      { id: 'prompt.chaining', name: '提示链', summary: '构建提示词链处理复杂任务' },
      { id: 'prompt.templating', name: '提示模板', summary: '创建可复用的提示词模板' },
      { id: 'prompt.optimization', name: '提示优化', summary: '优化提示词提高输出质量' },
      { id: 'role.management', name: '角色管理', summary: '管理和切换不同角色上下文' },
      { id: 'skill.orchestration', name: '技能编排', summary: '编排多个技能协同工作' },
      { id: 'context.management', name: '上下文管理', summary: '管理对话上下文和状态' },
    ]
  },

  // L5: 运行时层 Skills
  'scc.l5_runtime': {
    description: 'L5 运行时层相关技能',
    skills: [
      { id: 'runtime.nodejs', name: 'Node.js 运行时', summary: 'Node.js 运行时优化和调试' },
      { id: 'runtime.browser', name: '浏览器运行时', summary: '浏览器运行时优化' },
      { id: 'runtime.serverless', name: 'Serverless', summary: 'Serverless 运行时管理' },
      { id: 'runtime.edge', name: 'Edge 运行时', summary: 'Edge 计算运行时优化' },
    ]
  },

  // L6: 服务层 Skills
  'scc.l6_service': {
    description: 'L6 服务层相关技能',
    skills: [
      { id: 'service.api', name: 'API 设计', summary: 'RESTful 和 GraphQL API 设计' },
      { id: 'service.microservice', name: '微服务', summary: '微服务架构设计和实现' },
      { id: 'service.gateway', name: '网关服务', summary: 'API 网关配置和管理' },
      { id: 'service.message', name: '消息服务', summary: '消息队列和事件驱动架构' },
    ]
  },

  // L7: 数据层 Skills
  'scc.l7_data': {
    description: 'L7 数据层相关技能',
    skills: [
      { id: 'data.database', name: '数据库', summary: 'SQL 和 NoSQL 数据库设计' },
      { id: 'data.orm', name: 'ORM', summary: '对象关系映射和数据访问' },
      { id: 'data.caching', name: '缓存', summary: '缓存策略和实现' },
      { id: 'data.migration', name: '数据迁移', summary: '数据库迁移和版本控制' },
      { id: 'data.analytics', name: '数据分析', summary: '数据分析和报表生成' },
    ]
  },

  // L8: 集成层 Skills
  'scc.l8_integration': {
    description: 'L8 集成层相关技能',
    skills: [
      { id: 'integration.third_party', name: '第三方集成', summary: '集成第三方 API 和服务' },
      { id: 'integration.webhook', name: 'Webhook', summary: 'Webhook 设计和实现' },
      { id: 'integration.sync', name: '数据同步', summary: '跨系统数据同步' },
      { id: 'integration.adapter', name: '适配器模式', summary: '构建系统适配器' },
    ]
  },

  // L9: 质量层 Skills
  'scc.l9_quality': {
    description: 'L9 质量层相关技能',
    skills: [
      { id: 'quality.testing', name: '质量测试', summary: '全面的质量测试策略' },
      { id: 'quality.monitoring', name: '质量监控', summary: '代码质量和性能监控' },
      { id: 'quality.security', name: '安全测试', summary: '安全漏洞扫描和修复' },
      { id: 'quality.performance', name: '性能测试', summary: '负载测试和性能优化' },
    ]
  },

  // L10: 工作流层 Skills
  'scc.l10_workflow': {
    description: 'L10 工作流层相关技能',
    skills: [
      { id: 'workflow.orchestration', name: '工作流编排', summary: '复杂工作流设计和编排' },
      { id: 'workflow.automation', name: '工作流自动化', summary: '自动化重复性工作流程' },
      { id: 'workflow.state', name: '状态管理', summary: '工作流状态管理和持久化' },
      { id: 'workflow.error_handling', name: '错误处理', summary: '工作流错误处理和恢复' },
    ]
  },

  // L11: 智能体层 Skills
  'scc.l11_agent': {
    description: 'L11 智能体层相关技能',
    skills: [
      { id: 'agent.planning', name: '智能体规划', summary: 'AI 智能体任务规划' },
      { id: 'agent.reasoning', name: '智能体推理', summary: '智能体推理和决策' },
      { id: 'agent.memory', name: '智能体记忆', summary: '智能体长期记忆管理' },
      { id: 'agent.tools', name: '工具使用', summary: '智能体工具调用和管理' },
      { id: 'agent.multi_agent', name: '多智能体', summary: '多智能体协作和通信' },
    ]
  },

  // L12: 协作层 Skills
  'scc.l12_collaboration': {
    description: 'L12 协作层相关技能',
    skills: [
      { id: 'collaboration.git', name: 'Git 协作', summary: 'Git 工作流和协作最佳实践' },
      { id: 'collaboration.code_review', name: '代码审查', summary: '有效的代码审查流程' },
      { id: 'collaboration.documentation', name: '文档协作', summary: '团队文档协作和维护' },
      { id: 'collaboration.communication', name: '团队沟通', summary: '技术团队沟通技巧' },
    ]
  },

  // L13: 安全层 Skills
  'scc.l13_security': {
    description: 'L13 安全层相关技能',
    skills: [
      { id: 'security.authentication', name: '身份认证', summary: '用户认证和授权' },
      { id: 'security.encryption', name: '加密', summary: '数据加密和安全传输' },
      { id: 'security.audit', name: '安全审计', summary: '安全审计和合规检查' },
      { id: 'security.vulnerability', name: '漏洞管理', summary: '漏洞扫描和修复' },
      { id: 'security.privacy', name: '隐私保护', summary: '数据隐私和 GDPR 合规' },
    ]
  },

  // L14: 治理层 Skills
  'scc.l14_governance': {
    description: 'L14 治理层相关技能',
    skills: [
      { id: 'governance.architecture', name: '架构治理', summary: '架构决策和治理' },
      { id: 'governance.standards', name: '标准规范', summary: '编码标准和最佳实践' },
      { id: 'governance.compliance', name: '合规管理', summary: '法规和合规要求' },
      { id: 'governance.risk', name: '风险管理', summary: '技术风险评估和管理' },
    ]
  },

  // 跨领域 Skills
  'scc.cross_cutting': {
    description: '跨领域通用技能',
    skills: [
      { id: 'cross.logging', name: '日志管理', summary: '统一日志记录和分析' },
      { id: 'cross.monitoring', name: '系统监控', summary: '系统健康和性能监控' },
      { id: 'cross.tracing', name: '分布式追踪', summary: '分布式系统追踪' },
      { id: 'cross.metrics', name: '指标收集', summary: '业务和技术指标收集' },
      { id: 'cross.config', name: '配置管理', summary: '应用配置和环境管理' },
      { id: 'cross.feature_flags', name: '功能开关', summary: '功能开关和灰度发布' },
    ]
  },

  // SCC 核心工作流 Skills
  'scc.core': {
    description: 'SCC 核心工作流技能',
    skills: [
      { id: 'core.task_analysis', name: '任务分析', summary: '分析用户需求并分解任务' },
      { id: 'core.planning', name: '任务规划', summary: '制定详细的执行计划' },
      { id: 'core.implementation', name: '任务实现', summary: '执行实现并生成代码' },
      { id: 'core.testing', name: '任务测试', summary: '验证实现正确性' },
      { id: 'core.review', name: '任务审查', summary: '审查输出质量' },
      { id: 'core.documentation', name: '任务文档', summary: '生成任务文档' },
      { id: 'core.evidence', name: '证据收集', summary: '收集执行证据' },
      { id: 'core.submission', name: '任务提交', summary: '准备和提交任务结果' },
    ]
  },
};

// 创建 SCC Skill 定义
function createSccSkill(category, skillInfo) {
  const skillId = `${category}.${skillInfo.id}`;
  
  return {
    schema_version: "scc.skill.v1",
    skill_id: skillId,
    version: "1.0.0",
    owner_role: "workbench_dev",
    summary: skillInfo.summary,
    applies_to: {
      task_class: ["*"],
      tags: [category, skillInfo.id, "scc", "core"]
    },
    contracts: {
      input_schema: "contracts/child_task/child_task.schema.json",
      output_schema: "contracts/submit/submit.schema.json"
    },
    budgets: {
      max_loc: 1500,
      max_files: 30
    },
    quality_gates: {
      must_run_allowedTests: true,
      must_keep_diff_minimal: false
    },
    enablement: {
      status: "active",
      rollout: {
        mode: "all",
        percent: 100
      }
    },
    metadata: {
      category: category,
      subcategory: skillInfo.id,
      display_name: skillInfo.name,
      tags: [category, skillInfo.id, "scc", "core", "scc_library"],
      complexity: "intermediate",
      created_at: new Date().toISOString(),
      source: "scc_library"
    }
  };
}

// 保存 skill 到文件系统
function saveSkill(skillId, skillData) {
  const skillDir = path.join(SKILLS_DIR, skillId);
  const skillFile = path.join(skillDir, 'skill.json');
  
  // 创建目录
  if (!fs.existsSync(skillDir)) {
    fs.mkdirSync(skillDir, { recursive: true });
  }
  
  // 保存 skill.json
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
  
  // 读取现有 registry
  if (fs.existsSync(REGISTRY_FILE)) {
    try {
      registry = JSON.parse(fs.readFileSync(REGISTRY_FILE, 'utf8'));
    } catch (e) {
      console.warn('Warning: Could not parse existing registry, creating new one');
    }
  }
  
  // 添加新 skills
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

// 更新 role_skill_matrix
function updateMatrix(newSkills) {
  let matrix = {
    schema_version: "scc.role_skill_matrix.v1",
    updated_at: new Date().toISOString().split('T')[0],
    roles: {}
  };
  
  // 读取现有 matrix
  if (fs.existsSync(MATRIX_FILE)) {
    try {
      matrix = JSON.parse(fs.readFileSync(MATRIX_FILE, 'utf8'));
    } catch (e) {
      console.warn('Warning: Could not parse existing matrix, creating new one');
    }
  }
  
  // 添加到 workbench_dev 角色
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
  console.log('SCC 专属 Skills 库构建工具');
  console.log('='.repeat(80));
  console.log();
  
  const allSkills = [];
  
  // 生成所有 skills
  console.log('生成 SCC Skills...');
  for (const [category, categoryInfo] of Object.entries(SCC_SKILL_CATEGORIES)) {
    console.log(`\n[${category}] ${categoryInfo.description}`);
    
    for (const skillInfo of categoryInfo.skills) {
      const skillData = createSccSkill(category, skillInfo);
      allSkills.push(skillData);
      console.log(`  ✓ ${skillData.skill_id} - ${skillInfo.name}`);
    }
  }
  
  console.log(`\n总共生成 ${allSkills.length} 个 SCC Skills`);
  console.log();
  
  // 保存 skills
  console.log('='.repeat(80));
  console.log('保存 Skills');
  console.log('='.repeat(80));
  
  let savedCount = 0;
  for (const skill of allSkills) {
    try {
      saveSkill(skill.skill_id, skill);
      savedCount++;
    } catch (error) {
      console.error(`  ✗ 保存失败 ${skill.skill_id}: ${error.message}`);
    }
  }
  
  console.log(`✓ 已保存 ${savedCount} 个 skills`);
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
  
  // 统计信息
  console.log('='.repeat(80));
  console.log('SCC Skills 库统计');
  console.log('='.repeat(80));
  
  const categoryCount = {};
  for (const skill of allSkills) {
    const cat = skill.metadata?.category || 'unknown';
    categoryCount[cat] = (categoryCount[cat] || 0) + 1;
  }
  
  console.log('按类别分布:');
  for (const [cat, count] of Object.entries(categoryCount).sort()) {
    console.log(`  ${cat}: ${count} skills`);
  }
  
  console.log();
  console.log('='.repeat(80));
  console.log('SCC Skills 库构建完成!');
  console.log('='.repeat(80));
  console.log();
  console.log('这些 skills:');
  console.log('  - 覆盖 SCC L1-L14 全架构层次');
  console.log('  - 与 SCC 角色系统对齐');
  console.log('  - 支持跨层次组合使用');
  console.log('  - 所有角色均可访问');
}

main().catch(console.error);
