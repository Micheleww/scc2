#!/usr/bin/env node
/**
 * 初始化前端项目
 * 
 * 实际执行前端项目初始化
 */

import { execSync } from 'child_process';
import { existsSync, mkdirSync, writeFileSync } from 'fs';
import { join } from 'path';

const REPO_ROOT = process.cwd();
const FRONTEND_DIR = join(REPO_ROOT, 'ui', 'frontend');

console.log('╔══════════════════════════════════════════════════╗');
console.log('║     SCC 前端项目初始化                           ║');
console.log('╚══════════════════════════════════════════════════╝\n');

// 检查目录
if (existsSync(FRONTEND_DIR)) {
  console.log('✓ 前端目录已存在:', FRONTEND_DIR);
} else {
  console.log('创建前端目录...');
  mkdirSync(FRONTEND_DIR, { recursive: true });
  console.log('✓ 目录创建成功');
}

// 创建 package.json
const packageJson = {
  "name": "scc-frontend",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "zustand": "^4.4.7",
    "@headlessui/react": "^1.7.17",
    "@radix-ui/react-dialog": "^1.0.5",
    "lucide-react": "^0.294.0",
    "clsx": "^2.0.0",
    "tailwind-merge": "^2.1.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.43",
    "@types/react-dom": "^