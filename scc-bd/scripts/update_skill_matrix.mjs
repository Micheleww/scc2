#!/usr/bin/env node
/**
 * 更新 role_skill_matrix.json，将新导入的 skills 添加到 workbench_dev 角色
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');
const MATRIX_FILE = path.join(REPO_ROOT, 'L4_prompt_layer', 'roles', 'role_skill_matrix.json');
const REGISTRY_FILE = path.join(REPO_ROOT, 'L4_prompt_layer', 'skills', 'registry.json');

// 读取 registry 获取所有 skills
const registry = JSON.parse(fs.readFileSync(REGISTRY_FILE, 'utf8'));
const allSkillIds = registry.skills.map(s => s.skill_id);

console.log(`Registry 中共有 ${allSkillIds.length} 个 skills`);

// 读取现有的 matrix
const matrix = JSON.parse(fs.readFileSync(MATRIX_FILE, 'utf8'));

// 获取 workbench_dev 现有的 skills
const existingSkills = new Set(matrix.roles.workbench_dev || []);
console.log(`workbench_dev 角色现有 ${existingSkills.size} 个 skills`);

// 找出需要添加的新 skills（以 imported 标记的）
const skillsToAdd = [];
for (const skillId of allSkillIds) {
  if (!existingSkills.has(skillId)) {
    skillsToAdd.push(skillId);
  }
}

console.log(`需要添加 ${skillsToAdd.length} 个新 skills 到 workbench_dev 角色`);

// 添加到 workbench_dev 角色
if (!matrix.roles.workbench_dev) {
  matrix.roles.workbench_dev = [];
}
matrix.roles.workbench_dev.push(...skillsToAdd);

// 更新日期
matrix.updated_at = new Date().toISOString().split('T')[0];

// 保存 matrix
fs.writeFileSync(MATRIX_FILE, JSON.stringify(matrix, null, 2) + '\n', 'utf8');

console.log(`✓ 已更新 role_skill_matrix.json`);
console.log(`  workbench_dev 角色现在有 ${matrix.roles.workbench_dev.length} 个 skills`);
