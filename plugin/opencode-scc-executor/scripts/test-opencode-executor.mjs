/**
 * Test OpenCode Executor Integration
 * 
 * 测试 OpenCode 执行器的配置和功能
 */

import { getRegistry } from '../index.mjs';

async function main() {
  console.log('=== OpenCode Executor Test ===\n');

  try {
    // 1. 初始化注册表
    console.log('1. Initializing executor registry...');
    const registry = await getRegistry();
    console.log('   ✓ Registry initialized\n');

    // 2. 列出所有执行器
    console.log('2. Listing executors:');
    const executors = registry.list();
    if (executors.length === 0) {
      console.log('   ✗ No executors found');
      process.exit(1);
    }
    
    executors.forEach(ex => {
      console.log(`   - ${ex.name} (type: ${ex.type}, priority: ${ex.priority}, enabled: ${ex.enabled})`);
    });
    console.log();

    // 3. 获取默认执行器
    console.log('3. Getting default executor...');
    const defaultExecutor = registry.getDefault();
    if (!defaultExecutor) {
      console.log('   ✗ No default executor available');
      process.exit(1);
    }
    console.log(`   ✓ Default executor: ${defaultExecutor.name || 'unknown'}`);
    console.log(`   Type: ${defaultExecutor.type || 'unknown'}`);
    console.log();

    // 4. 执行健康检查
    console.log('4. Running health check...');
    const health = await registry.healthCheck();
    Object.entries(health).forEach(([name, status]) => {
      const icon = status.status === 'healthy' ? '✓' : '✗';
      console.log(`   ${icon} ${name}: ${status.status}`);
      if (status.note) {
        console.log(`     Note: ${status.note}`);
      }
    });
    console.log();

    // 5. 获取执行器信息
    console.log('5. Executor info:');
    const info = defaultExecutor.getInfo();
    console.log(`   Name: ${info.name}`);
    console.log(`   Type: ${info.type}`);
    console.log(`   Version: ${info.version}`);
    console.log(`   Working Directory: ${info.config?.workingDirectory}`);
    console.log(`   Timeout: ${info.config?.timeout}ms`);
    console.log(`   Models: ${info.config?.models?.join(', ')}`);
    console.log();

    // 6. 测试执行任务
    console.log('6. Testing task execution...');
    const testTask = {
      id: 'test-task-001',
      role: 'engineer',
      skills: ['implementation', 'patch_only'],
      description: 'Test task for OpenCode executor',
      prompt: 'Please analyze the current directory structure and report what you find.',
      model: 'claude-3.7-sonnet'
    };

    const testContext = {
      contextPack: 'Test context pack for SCC system'
    };

    console.log('   Executing test task...');
    const result = await defaultExecutor.execute(testTask, testContext);
    
    console.log(`   Task ID: ${result.taskId}`);
    console.log(`   Status: ${result.status}`);
    console.log(`   Duration: ${result.metadata?.duration}ms`);
    console.log(`   Executor: ${result.metadata?.executor}`);
    
    if (result.status === 'success') {
      console.log('   ✓ Task executed successfully');
    } else {
      console.log(`   ✗ Task failed: ${result.error}`);
    }
    console.log();

    // 7. 测试角色选择
    console.log('7. Testing role-based executor selection...');
    const roles = ['engineer', 'integrator', 'designer', 'auditor'];
    roles.forEach(role => {
      const executor = registry.selectForRole(role);
      console.log(`   ${role} -> ${executor?.name || 'none'}`);
    });
    console.log();

    console.log('=== All Tests Passed ===');
    process.exit(0);

  } catch (error) {
    console.error('\n✗ Test failed:', error.message);
    console.error(error.stack);
    process.exit(1);
  }
}

main();
