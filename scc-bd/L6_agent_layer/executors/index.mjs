/**
 * SCC Executors Index
 * 
 * 统一导出所有执行器模块
 * 
 * 注意：实际执行器实现已移动到 plugin/opencode-scc-executor 目录
 * 此文件作为 SCC 内部的引用入口
 */

// 从 plugin 目录重新导出 OpenCode 执行器
export { 
  OpenCodeExecutor, 
  createExecutor, 
  loadExecutorFromConfig,
  OpenCodeWrapper,
  createWrapper,
  ExecutorRegistry,
  getRegistry,
  resetRegistry
} from '../../../plugin/opencode-scc-executor/index.mjs';

// WebGPT 执行器
export { 
  WebGPTExecutor, 
  createWebGPTExecutor, 
  loadWebGPTExecutorFromConfig 
} from './webgpt_executor.mjs';

// OpenClaw 执行器
export { 
  OpenClawExecutor, 
  createOpenClawExecutor, 
  loadOpenClawExecutorFromConfig 
} from './openclaw_executor.mjs';

// 默认导出注册表
export { getRegistry as default } from '../../../plugin/opencode-scc-executor/index.mjs';
