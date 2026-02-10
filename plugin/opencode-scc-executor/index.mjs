/**
 * SCC Executors Index
 * 
 * 统一导出所有执行器模块
 */

// OpenCode 执行器
export { OpenCodeExecutor, createExecutor, loadExecutorFromConfig } from './opencode_executor.mjs';

// OpenCode 包装器（当 Go 二进制不可用时使用）
export { OpenCodeWrapper, createWrapper } from './opencode_wrapper.mjs';

// 执行器注册表
export { ExecutorRegistry, getRegistry, resetRegistry } from './registry.mjs';

// 默认导出注册表
export { getRegistry as default } from './registry.mjs';
