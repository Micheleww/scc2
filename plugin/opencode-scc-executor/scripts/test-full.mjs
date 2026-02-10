/**
 * Full OpenCode CLI Test
 * 
 * 测试 OpenCode CLI 的完整功能
 */

import { existsSync } from 'fs';
import { resolve } from 'path';
import { spawn } from 'child_process';

// 颜色输出
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m'
};

function log(type, message) {
  const color = colors[type] || colors.reset;
  console.log(`${color}[${type.toUpperCase()}]${colors.reset} ${message}`);
}

async function runTest(name, testFn) {
  try {
    await testFn();
    log('green', `✓ ${name}`);
    return true;
  } catch (error) {
    log('red', `✗ ${name}: ${error.message}`);
    return false;
  }
