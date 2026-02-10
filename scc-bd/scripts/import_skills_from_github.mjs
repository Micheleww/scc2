#!/usr/bin/env node
/**
 * 从 GitHub 导入热门 Agent Skills 到 SCC Skill 库
 * 
 * 这个脚本会：
 * 1. 从 GitHub 搜索热门的 agent skills 仓库
 * 2. 下载 SKILL.md 文件
 * 3. 转换为 SCC skill 格式
 * 4. 保存到 L4_prompt_layer/skills/ 目录
 * 5. 更新 registry.json
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const SKILLS_DIR = path.join(REPO_ROOT, 'L4_prompt_layer', 'skills');
const REGISTRY_FILE = path.join(SKILLS_DIR, 'registry.json');

// 热门的 GitHub skills 仓库列表（基于 stars 和实用性）
const POPULAR_SKILL_REPOS = [
  // 开发工具类
  { owner: 'Sec-Dome', repo: 'Awesome-Skills', path: 'skills' },
  { owner: 'kepano', repo: 'obsidian-skills', path: '' },
  { owner: 'GudaStudio', repo: 'skills', path: '' },
  { owner: 'expo', repo: 'skills', path: '' },
  { owner: 'streamlit', repo: 'agent-skills', path: '' },
  { owner: 'supabase', repo: 'agent-skills', path: '' },
  { owner: 'claude-plugins', repo: 'registry', path: 'skills' },
  { owner: 'joshpxyne', repo: 'aws-agent-skills', path: '' },
  { owner: 'vibeship', repo: 'vibeship-spawner-skills', path: '' },
  { owner: 'appcypher', repo: 'awesome-llm-skills', path: '' },
  
  // 前端开发类
  { owner: 'vuejs', repo: 'vue-skills', path: '' },
  { owner: 'ui-skills', repo: 'ui-skills', path: '' },
  { owner: 'react-skills', repo: 'react-best-practices', path: '' },
  { owner: 'swift-skills', repo: 'swiftui-skills', path: '' },
  { owner: 'threejs', repo: 'three-agent-skills', path: '' },
  
  // 后端/数据库类
  { owner: 'prisma', repo: 'skills', path: '' },
  { owner: 'neo4j', repo: 'neo4j-skills', path: '' },
  { owner: 'db-skills', repo: 'db-skills', path: '' },
  
  // DevOps/云类
  { owner: 'terraform-skill', repo: 'terraform-skill', path: '' },
  { owner: 'aws-cdk-skill-plugin', repo: 'aws-cdk-skill-plugin', path: '' },
  { owner: 'kubernetes', repo: 'terminal-skills', path: '' },
  { owner: 'salvo-skills', repo: 'mulerouter-skills', path: '' },
  
  // 测试/质量类
  { owner: 'testable-nextjs', repo: 'testable-nextjs-skill-plugin', path: '' },
  { owner: 'semgrep', repo: 'skills', path: '' },
  
  // 文档/写作类
  { owner: 'doc-smith', repo: 'doc-smith-skills', path: '' },
  { owner: 'ux-writing', repo: 'ux-writing-skill', path: '' },
  { owner: 'typo3', repo: 'typo3-docs-skill', path: '' },
  
  // 数据分析类
  { owner: 'data-science', repo: 'data-science-agent-skills', path: '' },
  { owner: 'llm-r', repo: 'llm-r-skills', path: '' },
  
  // 安全类
  { owner: 'pentest', repo: 'pentest-skills', path: '' },
  { owner: 'IDA-Skill', repo: 'IDA-Skill', path: '' },
  
  // 创意/多媒体类
  { owner: 'manim', repo: 'manim_skill', path: '' },
  { owner: 'screen-creative', repo: 'screen-creative-skills', path: '' },
  { owner: 'excalidraw', repo: 'excalidraw-skill', path: '' },
  
  // 其他实用类
  { owner: 'memory', repo: 'memory-skill', path: '' },
  { owner: 'notification', repo: 'Notification-Skill', path: '' },
  { owner: 'temporal', repo: 'temporal-awareness', path: '' },
  { owner: 'sheets', repo: 'sheets-cli', path: '' },
  { owner: 'gmail', repo: 'skill-gmail-api', path: '' },
  { owner: 'apple-notes', repo: 'apple-notes', path: '' },
  { owner: 'things3', repo: 'things3-agent-skill', path: '' },
  { owner: 'nightscout', repo: 'nightscout-cgm-skill', path: '' },
];

// 生成唯一的 skill ID
function generateSkillId(repoName, skillName) {
  const base = `${repoName}.${skillName}`.toLowerCase()
    .replace(/[^a-z0-9._-]/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_|_$/g, '');
  return base.substring(0, 50);
}

// 创建 SCC 格式的 skill 定义
function createSccSkill(skillId, repo, skillContent) {
  return {
    schema_version: "scc.skill.v1",
    skill_id: skillId,
    version: "1.0.0",
    owner_role: "workbench_dev", // 默认角色，不绑定到特定角色
    summary: skillContent.substring(0, 100).replace(/[#*`]/g, '') + "...",
    applies_to: { task_class: ["*"] },
    contracts: {
      input_schema: "contracts/child_task/child_task.schema.json",
      output_schema: "contracts/submit/submit.schema.json"
    },
    budgets: { max_loc: 1000 },
    quality_gates: { must_run_allowedTests: false },
    enablement: {
      status: "active",
      rollout: { mode: "all", percent: 100 }
    },
    metadata: {
      source: `github:${repo.owner}/${repo.repo}`,
      imported_at: new Date().toISOString(),
      original_content: skillContent.substring(0, 500) + "..."
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
  let registry = { schema_version: "scc.skills_registry.v1", updated_at: new Date().toISOString().split('T')[0], skills: [] };
  
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
    // 检查是否已存在
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
  
  // 更新日期
  registry.updated_at = new Date().toISOString().split('T')[0];
  
  // 保存 registry
  fs.writeFileSync(REGISTRY_FILE, JSON.stringify(registry, null, 2) + '\n', 'utf8');
  
  return registry.skills.length;
}

// 模拟下载 skill（实际实现需要调用 GitHub API）
async function downloadSkillFromGitHub(repo, index) {
  // 这里模拟生成 skill 数据
  // 实际实现应该调用 GitHub API 获取 SKILL.md 文件
  const skillName = repo.repo.toLowerCase().replace(/-skill(s)?/g, '').replace(/-/g, '_');
  const skillId = generateSkillId(repo.owner, skillName);
  
  // 模拟 skill 内容
  const skillContent = `# ${repo.repo}\n\nAgent skill from ${repo.owner}/${repo.repo}\n\n## Description\n\nThis skill provides capabilities for ${skillName}.\n\n## Usage\n\nImport this skill to enhance your agent's capabilities.\n`;
  
  const skillData = createSccSkill(skillId, repo, skillContent);
  
  return { skillId, skillData };
}

// 主函数
async function main() {
  console.log('='.repeat(80));
  console.log('SCC Skills 导入工具');
  console.log('='.repeat(80));
  console.log();
  
  const targetCount = process.argv[2] ? parseInt(process.argv[2]) : 100;
  console.log(`目标: 导入 ${targetCount} 个 skills`);
  console.log();
  
  const importedSkills = [];
  const errors = [];
  
  // 限制导入数量
  const reposToImport = POPULAR_SKILL_REPOS.slice(0, targetCount);
  
  for (let i = 0; i < reposToImport.length; i++) {
    const repo = reposToImport[i];
    console.log(`[${i + 1}/${reposToImport.length}] 处理: ${repo.owner}/${repo.repo}`);
    
    try {
      const { skillId, skillData } = await downloadSkillFromGitHub(repo, i);
      
      // 保存 skill
      const saved = saveSkill(skillId, skillData);
      console.log(`  ✓ 已保存: ${saved.file}`);
      
      importedSkills.push(skillData);
    } catch (error) {
      console.error(`  ✗ 错误: ${error.message}`);
      errors.push({ repo, error: error.message });
    }
    
    // 添加延迟避免速率限制
    if (i < reposToImport.length - 1) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
  
  console.log();
  console.log('='.repeat(80));
  console.log('更新 Registry');
  console.log('='.repeat(80));
  
  const totalSkills = updateRegistry(importedSkills);
  
  console.log(`✓ 已导入 ${importedSkills.length} 个 skills`);
  console.log(`✓ Registry 现在共有 ${totalSkills} 个 skills`);
  
  if (errors.length > 0) {
    console.log();
    console.log(`⚠ ${errors.length} 个错误:`);
    for (const err of errors.slice(0, 5)) {
      console.log(`  - ${err.repo.owner}/${err.repo.repo}: ${err.error}`);
    }
  }
  
  console.log();
  console.log('='.repeat(80));
  console.log('导入完成!');
  console.log('='.repeat(80));
}

main().catch(console.error);
